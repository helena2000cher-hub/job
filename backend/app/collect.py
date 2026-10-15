"""Collect vacancies from a source into the local database.

python -m app.collect --query "аналитик"
python -m app.collect --query "аналитик" --all-regions --remote-only --limit 300
python -m app.collect --source exa --from-profile             # hh.ru, Хабр, сайты компаний
python -m app.collect --source exa --sites hh.ru --query "системный аналитик" --remote-only
"""

import argparse
import logging
import sys

import httpx
from sqlmodel import Session

from app.collectors import COLLECTORS, ExaCollector, SearchQuery
from app.collectors.base import Collector
from app.collectors.exa import SITES
from app.config import get_settings
from app.db import get_engine, init_db
from app.models import Vacancy
from app.profile import load_profile
from app.storage import save_vacancies

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Собрать вакансии в локальную базу")
    parser.add_argument("--source", choices=COLLECTORS, default="trudvsem")
    parser.add_argument("--query", "-q", help="поисковый запрос, например «аналитик»")
    parser.add_argument(
        "--from-profile",
        action="store_true",
        help="взять запросы и формат работы из data/profile.json",
    )
    parser.add_argument("--region", default=settings.default_region_code, help="код региона")
    parser.add_argument("--all-regions", action="store_true", help="искать по всей России")
    parser.add_argument("--remote-only", action="store_true", help="только удалённые вакансии")
    parser.add_argument("--limit", type=int, default=200, help="максимум вакансий на запрос")
    parser.add_argument(
        "--sites", nargs="+", choices=SITES, help="для exa: где искать (по умолчанию везде)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    # Консоль Windows по умолчанию не в UTF-8 — без этого кириллица превращается в «?».
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    queries = [args.query] if args.query else []
    remote_only = args.remote_only
    if args.from_profile:
        profile = load_profile()
        queries += profile.search_queries
        remote_only = remote_only or profile.preferences.remote_only
    if not queries:
        parser.error("нужен --query или --from-profile")

    collector: Collector = (
        ExaCollector(args.sites) if args.source == "exa" else COLLECTORS[args.source]()
    )
    # Удалёнка ищется по всей стране, офис — в своём регионе.
    region = None if args.all_regions or remote_only else args.region

    vacancies: dict[str, Vacancy] = {}
    for text in queries:
        query = SearchQuery(
            text=text, region_code=region, remote_only=remote_only, limit=args.limit
        )
        try:
            found = list(collector.fetch(query))
        except httpx.HTTPError as exc:  # один упавший запрос не должен терять результаты остальных
            log.warning("%s: запрос «%s» не выполнен: %s", args.source, text, exc)
            continue
        new = sum(v.id not in vacancies for v in found)
        vacancies.update((v.id, v) for v in found)
        print(f"  «{text}»: {len(found)} (новых в этом прогоне: {new})")

    engine = get_engine()
    init_db(engine)
    # expire_on_commit=False — чтобы печатать сводку по объектам уже после сохранения
    with Session(engine, expire_on_commit=False) as session:
        stats = save_vacancies(session, vacancies.values())

    remote = sum(v.is_remote for v in vacancies.values())
    print(
        f"{args.source}: найдено {len(vacancies)} (удалённых: {remote}), "
        f"новых в базе {stats.created}, обновлено {stats.updated}"
    )
    if isinstance(collector, ExaCollector):
        print(
            f"  отброшено (списки, статьи, закрытые, не удалённые): {collector.skipped}; "
            f"стоимость Exa: ${collector.cost_dollars:.3f}"
        )
    for v in list(vacancies.values())[:10]:
        salary = _format_salary(v.salary_from, v.salary_to)
        flag = "🏠" if v.is_remote else "  "
        print(f"  {flag} [{v.source}] {v.title} — {v.company or '?'} · {salary}")
    return 0


def _format_salary(low: int | None, high: int | None) -> str:
    if low and high and low != high:
        return f"{low:,}–{high:,} ₽".replace(",", " ")
    if low:
        return f"от {low:,} ₽".replace(",", " ")
    if high:
        return f"до {high:,} ₽".replace(",", " ")
    return "з/п не указана"


if __name__ == "__main__":
    raise SystemExit(main())
