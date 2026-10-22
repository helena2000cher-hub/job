"""SuperJob (superjob.ru) — official API. Employers post vacancies there themselves.

Needs a free app key: register at https://api.superjob.ru/register/, copy «Secret key» from
https://api.superjob.ru/info/ into .env as SUPERJOB_API_KEY. Searching vacancies needs no OAuth.
Docs: https://api.superjob.ru/  (limit: 120 requests/min per IP, ≤ 500 results per query)

Exa can't be used here: superjob.ru answers crawlers with a captcha.
"""

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.collectors.base import Collector, SearchQuery
from app.collectors.remote import detect_remote
from app.config import get_settings
from app.models import Vacancy

log = logging.getLogger(__name__)

BASE_URL = "https://api.superjob.ru/2.0"
PAGE_SIZE = 100
MAX_PAGES = 5
PLACE_AT_HOME = 2  # place_of_work: 1 — у работодателя, 2 — на дому (удалённо), 3 — разъездная
# experience.id → минимальный опыт в годах
EXPERIENCE_YEARS = {1: 0, 2: 1, 3: 3, 4: 6}


class SuperJobCollector(Collector):
    name = "superjob"

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        if client is None and not settings.superjob_api_key:
            raise RuntimeError(
                "SUPERJOB_API_KEY не задан в .env — получите бесплатный ключ на "
                "https://api.superjob.ru/register/"
            )
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=30,
            headers={"X-Api-App-Id": settings.superjob_api_key},
        )
        self._town = settings.default_town

    def fetch(self, query: SearchQuery) -> Iterator[Vacancy]:
        params: dict[str, Any] = {"count": min(PAGE_SIZE, query.limit), "period": 0}
        if query.text:
            params["keyword"] = query.text
        if query.remote_only:
            params["place_of_work"] = PLACE_AT_HOME
        elif query.region_code:
            params["town"] = self._town  # офис — в своём городе

        yielded = 0
        for page in range(MAX_PAGES):
            params["page"] = page
            response = self._client.get("/vacancies/", params=params)
            response.raise_for_status()
            data = response.json()
            for item in data.get("objects") or []:
                try:
                    vacancy = parse_vacancy(item)
                except (KeyError, TypeError, ValueError) as exc:
                    log.warning("superjob: skipped malformed vacancy: %s", exc)
                    continue
                if query.remote_only and not vacancy.is_remote:
                    continue
                yield vacancy
                yielded += 1
                if yielded >= query.limit:
                    return
            if not data.get("more"):
                return


def parse_vacancy(data: dict[str, Any]) -> Vacancy:
    vid = str(data["id"])
    place = (data.get("place_of_work") or {}).get("id")
    experience = (data.get("experience") or {}).get("id")
    vacancy = Vacancy(
        id=f"superjob.ru:{vid}",
        source="superjob.ru",
        external_id=vid,
        title=_text(data.get("profession")) or "Без названия",
        company=_text(data.get("firm_name")) or _text((data.get("client") or {}).get("title")),
        region=_text((data.get("town") or {}).get("title")),
        address=_text(data.get("address")),
        salary_from=data.get("payment_from") or None,
        salary_to=data.get("payment_to") or None,
        currency=(data.get("currency") or "rub").upper(),
        employment=_text((data.get("type_of_work") or {}).get("title")),
        requirements=_text(data.get("candidat")),
        duties=_text(data.get("work")),
        conditions=_text(data.get("compensation")),
        experience_years=EXPERIENCE_YEARS.get(experience),
        education=_text((data.get("education") or {}).get("title")),
        category=_catalogue(data.get("catalogues")),
        url=data.get("link") or f"https://www.superjob.ru/vakansii/{vid}.html",
        published_at=_date(data.get("date_published")),
        raw=data,
    )
    vacancy.is_remote = place == PLACE_AT_HOME or detect_remote(vacancy.employment, vacancy.text)
    return vacancy


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _catalogue(value: Any) -> str | None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return _text(value[0].get("title"))
    return None


def _date(value: Any):
    try:
        return datetime.fromtimestamp(int(value), UTC).date() if value else None
    except (TypeError, ValueError, OSError):
        return None
