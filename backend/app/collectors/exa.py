"""Exa (exa.ai) — neural web search. Finds vacancies where there is no open API:
hh.ru (API closed since 2026), Хабр Карьера and companies' own career pages.

Exa extracts structured fields itself (`contents.summary.schema`), so no extra LLM call is needed.
Two steps to save money: a search without contents (~$0.007), then /contents with the summary
(~$0.001 per page) only for links that are not in the database yet.
Docs: https://exa.ai/docs/reference/search
"""

import hashlib
import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx

from app.collectors.base import Collector, SearchQuery
from app.collectors.remote import detect_remote
from app.config import get_settings
from app.llm import extract_json
from app.models import Vacancy

log = logging.getLogger(__name__)

API_URL = "https://api.exa.ai/search"
CONTENTS_URL = "https://api.exa.ai/contents"


@dataclass(frozen=True)
class Site:
    name: str  # становится Vacancy.source
    include_domains: tuple[str, ...] = ()
    url_pattern: re.Pattern[str] | None = None  # группа 1 — id вакансии; None — любой URL
    canonical_url: str | None = None  # шаблон с {id}


HH = Site(
    "hh.ru",
    ("hh.ru",),
    re.compile(r"(?:^|\.)hh\.ru/vacancy/(\d+)"),  # также perm.hh.ru/vacancy/...
    "https://hh.ru/vacancy/{id}",
)
HABR = Site(
    "career.habr.com",
    ("career.habr.com",),
    re.compile(r"career\.habr\.com/vacancies/(\d+)"),  # не списки вида /vacancies/biznes_analitik
    "https://career.habr.com/vacancies/{id}",
)
WEB = Site("web")  # карьерные страницы компаний и нишевые сайты
SITES = {s.name: s for s in (HH, HABR, WEB)}

# Агрегаторы, доски объявлений и соцсети: в режиме «web» нужны страницы самих компаний,
# а не перепосты (часто без названия компании и ссылки на первоисточник). Список — первый
# фильтр; второй — поле is_employer_page в разборе страницы, он ловит неизвестные агрегаторы.
AGGREGATORS = [
    # крупные сайты вакансий
    "hh.ru", "*.hh.ru", "hh.kz", "*.hh.kz", "career.habr.com", "trudvsem.ru", "superjob.ru",
    "rabota.ru", "zarplata.ru", "avito.ru", "rabota.yandex.ru", "rabota.by", "jobs.dou.ua",
    "linkedin.com", "indeed.com", "vk.com", "t.me",
    # агрегаторы и перепосты вакансий (найдены в выдаче)
    "gorodrabot.ru", "jooble.org", "finder.work", "geekjob.ru", "careerspace.app",
    "jabka.work", "joba.work", "hirehi.ru", "sobes.tech", "quick-offer.ru", "talent-move.ru",
    "taylor.kz", "nesiditsa.ru", "pawetta.com", "dreamjob.ru", "deffic.ru", "hitit.one",
    "vakradar.ru", "remote-job.ru", "rabix.ru", "careerholo.com", "mindpal.co",
    "jobs.ita.am", "okjobs.co.za", "morocco24x7.com", "is-great.net",
]  # fmt: skip

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_open_vacancy": {
            "type": "boolean",
            "description": "true, если страница — ОДНА конкретная актуальная вакансия "
            "(не список вакансий, не статья, не архивная/закрытая вакансия)",
        },
        "title": {"type": "string", "description": "название должности"},
        "company": {"type": "string"},
        "salary_from": {"type": "integer", "description": "в месяц, 0 если нет"},
        "salary_to": {"type": "integer", "description": "в месяц, 0 если нет"},
        "currency": {"type": "string", "description": "код валюты зарплаты: RUB, KZT, USD, EUR"},
        "remote": {"type": "boolean", "description": "можно работать полностью удалённо"},
        "city": {"type": "string", "description": "город офиса, пусто если нет"},
        "employment": {"type": "string", "description": "тип занятости"},
        "experience": {"type": "string", "description": "требуемый опыт"},
        "requirements": {"type": "string", "description": "требования, кратко"},
        "duties": {"type": "string", "description": "обязанности, кратко"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "is_employer_page": {
            "type": "boolean",
            "description": "true, если вакансию опубликовал сам работодатель: сайт компании, её "
            "карьерная страница или ATS компании. false для агрегаторов, досок объявлений, "
            "перепостов и сайтов, где компания не указана",
        },
    },
    "required": ["is_open_vacancy", "title"],
}


class ExaCollector(Collector):
    name = "exa"

    def __init__(
        self,
        sites: list[str] | None = None,
        *,
        results_per_site: int = 10,
        max_age_days: int = 30,
        client: httpx.Client | None = None,
        known_ids: set[str] | None = None,
    ) -> None:
        api_key = get_settings().exa_api_key
        if client is None and not api_key:
            raise RuntimeError("EXA_API_KEY не задан в .env")
        self._client = client or httpx.Client(timeout=120, headers={"x-api-key": api_key})
        self._sites = [SITES[s] for s in (sites or list(SITES))]
        self._results_per_site = results_per_site
        self._max_age_days = max_age_days
        # Вакансии, которые уже есть в базе: за их выжимку повторно не платим
        self._known = known_ids if known_ids is not None else set()
        self.cost_dollars = 0.0
        self.skipped = 0
        self.already_known = 0

    def fetch(self, query: SearchQuery) -> Iterator[Vacancy]:
        if not query.text:
            raise ValueError("Exa ищет по смыслу — нужен текст запроса")
        yielded = 0
        for site in self._sites:
            new: dict[str, str] = {}  # id вакансии → ссылка из выдачи
            for result in self._search(site, query):
                ident = identify(result.get("url") or "", site)
                if ident is None:  # списки вакансий, статьи — не карточка вакансии
                    self.skipped += 1
                elif ident.id in self._known:
                    self.already_known += 1
                else:
                    new.setdefault(ident.id, result["url"])
            for result in self._contents(site, new):
                vacancy = parse_result(result, site)
                if vacancy is None or (query.remote_only and not vacancy.is_remote):
                    self.skipped += 1
                    continue
                self._known.add(vacancy.id)  # следующий запрос эту вакансию уже не оплачивает
                yield vacancy
                yielded += 1
                if yielded >= query.limit:
                    return

    def _search(self, site: Site, query: SearchQuery) -> list[dict[str, Any]]:
        words = ["вакансия", query.text]
        if query.remote_only:
            words.append("удаленная работа")
        since = datetime.now(UTC) - timedelta(days=self._max_age_days)
        body: dict[str, Any] = {
            "query": " ".join(words),
            "type": "auto",
            "numResults": min(self._results_per_site, query.limit),
            "userLocation": "RU",
            "startPublishedDate": since.strftime("%Y-%m-%dT00:00:00Z"),
            "contents": {"text": False},  # только ссылки; текст и выжимка — в _contents
        }
        if site.include_domains:
            body["includeDomains"] = list(site.include_domains)
        else:
            body["excludeDomains"] = AGGREGATORS
        return self._post(API_URL, body)

    def _contents(self, site: Site, new: dict[str, str]) -> list[dict[str, Any]]:
        """Text and structured summary for new links only, in one request."""
        if not new:
            return []
        results = self._post(
            CONTENTS_URL,
            {
                "urls": list(new.values()),
                "text": {"maxCharacters": 4000},
                "summary": {"schema": SUMMARY_SCHEMA},
            },
        )
        # Exa может вернуть адрес в другом виде (без меток, с поддоменом) — берём ссылку из выдачи
        for result in results:
            ident = identify(result.get("url") or "", site)
            if ident and ident.id in new:
                result["url"] = new[ident.id]
        return results

    def _post(self, url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._client.post(url, json=body)
        response.raise_for_status()
        data = response.json()
        self.cost_dollars += (data.get("costDollars") or {}).get("total") or 0.0
        return data.get("results") or []


@dataclass(frozen=True)
class Identity:
    id: str
    source: str
    external_id: str
    url: str


def identify(url: str, site: Site | None = None) -> Identity | None:
    """Stable id for a vacancy URL: hh/habr links of any form map to one canonical id."""
    site = site or site_for_url(url)
    parsed = urlparse(url)
    if site.url_pattern:
        match = site.url_pattern.search(parsed.netloc + parsed.path)
        if not match:
            return None
        external_id = match.group(1)
        canonical = site.canonical_url.format(id=external_id) if site.canonical_url else url
        return Identity(f"{site.name}:{external_id}", site.name, external_id, canonical)
    external_id = hashlib.sha1(url.encode()).hexdigest()[:16]
    source = parsed.netloc.removeprefix("www.") or site.name
    return Identity(f"{source}:{external_id}", source, external_id, url)


def site_for_url(url: str) -> Site:
    parsed = urlparse(url)
    for site in (HH, HABR):
        if site.url_pattern and site.url_pattern.search(parsed.netloc + parsed.path):
            return site
    return WEB


def parse_result(
    result: dict[str, Any], site: Site, *, allow_closed: bool = False
) -> Vacancy | None:
    """Exa result → Vacancy, or None for listings, articles and closed vacancies.

    allow_closed — для вакансий, добавленных вручную: после отклика их часто уже закрыли.
    """
    ident = identify(result.get("url") or "", site)
    if ident is None:
        return None
    url, source, external_id = ident.url, ident.source, ident.external_id

    summary = _parse_summary(result.get("summary"))
    if not _clean(summary.get("title")):
        return None
    if not allow_closed and not summary.get("is_open_vacancy"):
        return None
    # «Сайты компаний»: только страницы самого работодателя с названием компании.
    # Для вакансий, добавленных вручную (allow_closed), не проверяем — пользователь решил сам.
    not_employer = summary.get("is_employer_page") is False or not _clean(summary.get("company"))
    if site is WEB and not allow_closed and not_employer:
        return None

    title = re.sub(r"\s+[—-]\s+Хабр Карьера$", "", _clean(summary["title"]))
    title = re.sub(r"^Вакансия\s+[«\"]?(.*?)[»\"]?$", r"\1", title)
    text = _clean(result.get("text"))
    vacancy = Vacancy(
        id=f"{source}:{external_id}",
        source=source,
        external_id=external_id,
        title=title,
        company=_clean(summary.get("company")),
        region=_clean(summary.get("city")),
        salary_from=_positive(summary.get("salary_from")),
        salary_to=_positive(summary.get("salary_to")),
        currency=(_clean(summary.get("currency")) or "RUB").upper()[:3],
        employment=_clean(summary.get("employment")),
        requirements=_join(_clean(summary.get("experience")), _clean(summary.get("requirements"))),
        duties=_clean(summary.get("duties")),
        skills=[s for s in (summary.get("skills") or []) if isinstance(s, str) and s.strip()],
        url=url,
        published_at=_parse_date(result.get("publishedDate")),
        raw={"summary": summary, "text": text, "exa_url": result.get("url")},
    )
    if not allow_closed and text and _ARCHIVED.search(text):
        return None  # модель иногда пропускает плашку «Вакансия в архиве»
    vacancy.is_remote = _is_remote(summary, vacancy, text)
    return vacancy


_ARCHIVED = re.compile(
    r"вакансия (?:в архиве|закрыта|больше не активна)|вакансия перенесена в архив"
    r"|больше не принимает отклики|vacancy (?:is )?closed",
    re.IGNORECASE,
)
# Короткие пометки об удалёнке на карточках сайтов: «Можно удаленно», «Формат: удалённо», DOU.
_REMOTE_MARK = re.compile(r"удал[её]нно|удал[её]нка|віддалено|\bremote\b", re.IGNORECASE)
SHORT_TEXT = 500  # текст обрезан или пустой — тогда верим модели


def _is_remote(summary: dict[str, Any], vacancy: Vacancy, text: str | None) -> bool:
    """Trust the page text over the model: it sometimes marks Moscow office jobs as remote."""
    page = f"{vacancy.title}\n{text or ''}"
    if detect_remote(vacancy.employment, page) or _REMOTE_MARK.search(page):
        return True
    return bool(summary.get("remote")) and len(text or "") < SHORT_TEXT


def _parse_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        try:
            return extract_json(value)
        except ValueError:
            return {}


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    # Exa иногда отдаёт переносы строк экранированными («кратко:\n- собирать…») — делаем
    # из них настоящие; списки обязанностей так и остаются списками, а не сплошной строкой.
    lines = (re.sub(r"\s+", " ", line).strip() for line in value.replace("\\n", "\n").split("\n"))
    value = "\n".join(line for line in lines if line)
    return None if value.lower() in ("", "null", "none", "не указан", "не указано") else value


def _positive(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _join(*parts: str | None) -> str | None:
    return "; ".join(p for p in parts if p) or None


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def fetch_vacancy(url: str, client: httpx.Client | None = None) -> Vacancy | None:
    """Load one vacancy page by URL via Exa /contents (hh.ru blocks direct requests).

    Returns None if Exa can't read the page or it isn't a vacancy. Cost ≈ $0.002.
    """
    api_key = get_settings().exa_api_key
    if client is None:
        if not api_key:
            return None
        client = httpx.Client(timeout=60, headers={"x-api-key": api_key})
    response = client.post(
        CONTENTS_URL,
        json={
            "urls": [url],
            "text": {"maxCharacters": 4000},
            "summary": {"schema": SUMMARY_SCHEMA},
        },
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None
    result = {**results[0], "url": url}  # Exa может вернуть адрес без меток — сохраняем исходный
    return parse_result(result, site_for_url(url), allow_closed=True)
