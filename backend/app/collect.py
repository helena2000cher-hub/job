"""Collect vacancies from a source into the local database.

python -m app.collect --query "аналитик"
python -m app.collect --query "аналитик" --all-regions --remote-only --limit 300
python -m app.collect --source exa --from-profile             # hh.ru, Хабр, сайты компаний
python -m app.collect --source exa --sites hh.ru --query "системный аналитик" --remote-only
"""

import argparse
import logging
import sys

from app.collecting import collect
from app.collectors import COLLECTORS
from app.collectors.exa import SITES
from app.config import get_settings
from app.profile import load_profile


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
        queries += profile.effective_queries()  # запросы отмеченных профессий
        remote_only = remote_only or profile.preferences.remote_only
    if not queries:
        parser.error("нужен --query или --from-profile")

    # Удалёнка ищется по всей стране, офис — в своём регионе.
    region = None if args.all_regions or remote_only else args.region
    result = collect(
        args.source,
        queries,
        remote_only=remote_only,
        region_code=region,
        limit=args.limit,
        sites=args.sites,
        on_progress=lambda msg: print(f"  {msg}"),
    )
    vacancies = {v.id: v for v in result.vacancies}

    remote = sum(v.is_remote for v in vacancies.values())
    print(
        f"{args.source}: найдено {len(vacancies)} (удалённых: {remote}), "
        f"новых в базе {result.created}, обновлено {result.updated}"
    )
    if args.source == "exa":
        print(
            f"  отброшено (списки, статьи, закрытые, не удалённые): {result.skipped}; "
            f"стоимость Exa: ${result.cost_dollars:.3f}"
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
