"""Exa (exa.ai) — neural web search. Finds vacancies where there is no open API:
hh.ru (API closed since 2026), Хабр Карьера and companies' own career pages.

Exa extracts structured fields itself (`contents.summary.schema`), so no extra LLM call is needed.
Cost: ~$0.007 per search + $0.001 per summary → ~$0.02 per query and site with 10 results.
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

# Агрегаторы и соцсети: в режиме «web» нужны страницы самих компаний, а не их копии.
AGGREGATORS = [
    "hh.ru", "career.habr.com", "trudvsem.ru", "superjob.ru", "rabota.ru", "zarplata.ru",
    "avito.ru", "gorodrabot.ru", "jooble.org", "rabota.yandex.ru", "finder.work",
    "linkedin.com", "indeed.com", "vk.com", "geekjob.ru", "careerspace.app",
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
    ) -> None:
        api_key = get_settings().exa_api_key
        if client is None and not api_key:
            raise RuntimeError("EXA_API_KEY не задан в .env")
        self._client = client or httpx.Client(timeout=120, headers={"x-api-key": api_key})
        self._sites = [SITES[s] for s in (sites or list(SITES))]
        self._results_per_site = results_per_site
        self._max_age_days = max_age_days
        self.cost_dollars = 0.0
        self.skipped = 0

    def fetch(self, query: SearchQuery) -> Iterator[Vacancy]:
        if not query.text:
            raise ValueError("Exa ищет по смыслу — нужен текст запроса")
        yielded = 0
        for site in self._sites:
            for result in self._search(site, query):
                vacancy = parse_result(result, site)
                if vacancy is None or (query.remote_only and not vacancy.is_remote):
                    self.skipped += 1
                    continue
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
            "contents": {
                "text": {"maxCharacters": 4000},
                "summary": {"schema": SUMMARY_SCHEMA},
            },
        }
        if site.include_domains:
            body["includeDomains"] = list(site.include_domains)
        else:
            body["excludeDomains"] = AGGREGATORS

        response = self._client.post(API_URL, json=body)
        response.raise_for_status()
        data = response.json()
        self.cost_dollars += (data.get("costDollars") or {}).get("total") or 0.0
        return data.get("results") or []


def parse_result(result: dict[str, Any], site: Site) -> Vacancy | None:
    """Exa result → Vacancy, or None for listings, articles and closed vacancies."""
    url = result.get("url") or ""
    parsed = urlparse(url)
    if site.url_pattern:
        match = site.url_pattern.search(parsed.netloc + parsed.path)
        if not match:
            return None
        external_id = match.group(1)
        url = site.canonical_url.format(id=external_id) if site.canonical_url else url
        source = site.name
    else:
        external_id = hashlib.sha1(url.encode()).hexdigest()[:16]
        source = parsed.netloc.removeprefix("www.") or site.name

    summary = _parse_summary(result.get("summary"))
    if not summary.get("is_open_vacancy") or not _clean(summary.get("title")):
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
    if text and _ARCHIVED.search(text):
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
    value = re.sub(r"\s+", " ", value).strip()
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
