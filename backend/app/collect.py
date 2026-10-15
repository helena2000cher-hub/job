"""Collect vacancies from a source into the local database.

python -m app.collect --query "аналитик"
python -m app.collect --query "аналитик" --all-regions --remote-only --limit 300
"""

import argparse
import logging
import sys

from sqlmodel import Session

from app.collectors import COLLECTORS, SearchQuery
from app.config import get_settings
from app.db import get_engine, init_db
from app.storage import save_vacancies


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Собрать вакансии в локальную базу")
    parser.add_argument("--source", choices=COLLECTORS, default="trudvsem")
    parser.add_argument("--query", "-q", help="поисковый запрос, например «аналитик»")
    parser.add_argument("--region", default=settings.default_region_code, help="код региона")
    parser.add_argument("--all-regions", action="store_true", help="искать по всей России")
    parser.add_argument("--remote-only", action="store_true", help="только удалённые вакансии")
    parser.add_argument("--limit", type=int, default=200, help="максимум вакансий")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Консоль Windows по умолчанию не в UTF-8 — без этого кириллица превращается в «?».
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    query = SearchQuery(
        text=args.query,
        region_code=None if args.all_regions else args.region,
        remote_only=args.remote_only,
        limit=args.limit,
    )
    vacancies = list(COLLECTORS[args.source]().fetch(query))

    engine = get_engine()
    init_db(engine)
    # expire_on_commit=False — чтобы печатать сводку по объектам уже после сохранения
    with Session(engine, expire_on_commit=False) as session:
        stats = save_vacancies(session, vacancies)

    remote = sum(v.is_remote for v in vacancies)
    print(
        f"{args.source}: найдено {len(vacancies)} (удалённых: {remote}), "
        f"новых {stats.created}, обновлено {stats.updated}"
    )
    for v in vacancies[:10]:
        salary = _format_salary(v.salary_from, v.salary_to)
        flag = "🏠" if v.is_remote else "  "
        print(f"  {flag} {v.title} — {v.company or '?'} · {salary}")
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
