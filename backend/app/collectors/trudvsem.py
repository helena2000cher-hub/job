"""«Работа России» (trudvsem.ru) — open government API, no key required.

Docs: https://trudvsem.ru/opendata/api
- GET /vacancies               — по всей России
- GET /vacancies/region/{code} — по региону (код КЛАДР, например 5900000000000 — Пермский край)
- params: text, limit (<= 100), offset (номер страницы, с 0)
"""

import logging
import re
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import httpx

from app.collectors.base import Collector, SearchQuery
from app.collectors.remote import detect_remote
from app.models import Vacancy

log = logging.getLogger(__name__)

BASE_URL = "https://opendata.trudvsem.ru/api/v1"
PAGE_SIZE = 100
MAX_PAGES = 50  # страховка от бесконечного цикла

# Фильтра «удалёнка» в API нет, а страница по всей России грузится ~15 с и удалённых в ней ~1%.
# Поэтому сужаем выдачу на стороне API: слова в text работают как «И».
REMOTE_KEYWORDS = ("удаленная", "дистанционная")


class TrudvsemCollector(Collector):
    name = "trudvsem"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=BASE_URL, timeout=60, headers={"User-Agent": "job-matcher/0.1"}
        )

    def fetch(self, query: SearchQuery) -> Iterator[Vacancy]:
        if query.remote_only:
            texts = [" ".join(filter(None, [query.text, kw])) for kw in REMOTE_KEYWORDS]
        else:
            texts = [query.text]

        seen: set[str] = set()
        for text in texts:
            for vacancy in self._fetch_pages(query.region_code, text):
                if vacancy.id in seen or (query.remote_only and not vacancy.is_remote):
                    continue
                seen.add(vacancy.id)
                yield vacancy
                if len(seen) >= query.limit:
                    return

    def _fetch_pages(self, region_code: str | None, text: str | None) -> Iterator[Vacancy]:
        path = f"/vacancies/region/{region_code}" if region_code else "/vacancies"
        params: dict[str, Any] = {"limit": PAGE_SIZE}
        if text:
            params["text"] = text

        for page in range(MAX_PAGES):
            params["offset"] = page
            response = self._client.get(path, params=params)
            response.raise_for_status()
            items = response.json().get("results", {}).get("vacancies", [])

            for item in items:
                try:
                    yield parse_vacancy(item["vacancy"])
                except (KeyError, ValueError) as exc:
                    log.warning("trudvsem: skipped malformed vacancy: %s", exc)

            if len(items) < PAGE_SIZE:
                return


def parse_vacancy(data: dict[str, Any]) -> Vacancy:
    salary_from, salary_to = _parse_salary(data)
    addresses = (data.get("addresses") or {}).get("address") or []

    vacancy = Vacancy(
        id=f"trudvsem:{data['id']}",
        source="trudvsem",
        external_id=data["id"],
        title=data["job-name"].strip(),
        company=(data.get("company") or {}).get("name"),
        region=(data.get("region") or {}).get("name"),
        address=addresses[0].get("location") if addresses else None,
        salary_from=salary_from,
        salary_to=salary_to,
        employment=data.get("employment"),
        schedule=data.get("schedule"),
        requirements=_clean(data.get("requirements")),
        duties=_clean(data.get("duty")),
        conditions=_clean(data.get("conditions")),
        skills=_parse_skills(data.get("skills")),
        experience_years=(data.get("requirement") or {}).get("experience"),
        education=(data.get("requirement") or {}).get("education"),
        category=(data.get("category") or {}).get("specialisation"),
        url=data["vac_url"],
        published_at=_parse_date(data.get("creation-date")),
        source_updated_at=_parse_datetime(data.get("date_modify")),
        raw=data,
    )
    vacancy.is_remote = detect_remote(vacancy.employment, vacancy.text)
    return vacancy


def _parse_salary(data: dict[str, Any]) -> tuple[int | None, int | None]:
    low = data.get("salary_min") or None
    high = data.get("salary_max") or None
    text = (data.get("salary") or "").strip().lower()
    # API дублирует одно число в min и max: «от 35000» → min=max=35000. Восстанавливаем смысл.
    if low == high:
        if text.startswith("от"):
            high = None
        elif text.startswith("до"):
            low = None
    return low, high


def _parse_skills(skills: Any) -> list[str]:
    result = []
    for skill in skills or []:
        name = skill.get("name") if isinstance(skill, dict) else skill
        if isinstance(name, str) and name.strip():
            result.append(name.strip())
    return result


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)  # в некоторых карточках встречается HTML
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z") if value else None
    except ValueError:
        return None
