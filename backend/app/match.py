"""Rank collected vacancies against the profile.

python -m app.match              # топ-30 по смыслу → оценка LLM
python -m app.match --top 50 --rescore
"""

import argparse
import logging
import sys

from sqlmodel import Session

from app.db import get_engine, init_db
from app.llm import PolzaLLM
from app.matching.pipeline import run_matching
from app.profile import load_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Подобрать вакансии под профиль")
    parser.add_argument(
        "--top", type=int, default=30, help="сколько лучших по смыслу оценивать LLM"
    )
    parser.add_argument("--rescore", action="store_true", help="переоценить даже уже оценённые")
    parser.add_argument("--min-score", type=int, default=0, help="не показывать ниже этого балла")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    profile = load_profile()
    engine = get_engine()
    init_db(engine)
    with Session(engine, expire_on_commit=False) as session:
        report = run_matching(session, profile, PolzaLLM(), top_n=args.top, rescore=args.rescore)

    rejected = ", ".join(f"{reason} — {n}" for reason, n in report.rejected.most_common())
    print(f"Вакансий в базе: {report.total}. Отсеяно фильтрами: {rejected or 'нет'}")
    if report.duplicates:
        print(f"Дубли (та же вакансия в других регионах): {report.duplicates}")
    print(
        f"Оценено LLM: {report.scored} новых, {report.reused} из кэша"
        + (f", ошибок: {report.failed}" if report.failed else "")
    )
    print()
    for vacancy, match in report.results:
        if match.score < args.min_score:
            continue
        mark = "🟢" if match.score >= 80 else "🟡" if match.score >= 60 else "⚪"
        print(f"{mark} {match.score:>3}  {vacancy.title} — {vacancy.company or '?'}")
        print(f"       {match.verdict}")
        if match.matched_skills:
            print(f"       ✓ {', '.join(match.matched_skills[:8])}")
        if match.missing_skills:
            print(f"       ✗ {', '.join(match.missing_skills[:6])}")
        if match.red_flags:
            print(f"       ⚠ {'; '.join(match.red_flags[:3])}")
        print(f"       {vacancy.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
