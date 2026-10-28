"""Collect vacancies for a list of queries and save them — shared by the CLI and the web API."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.collectors import COLLECTORS, ExaCollector, SearchQuery
from app.collectors.base import Collector
from app.db import get_engine, init_db
from app.models import Vacancy
from app.storage import save_vacancies

log = logging.getLogger(__name__)

# Как источник называется для пользователя: Exa — внутренний поисковик, его не показываем
SOURCE_TITLES = {"exa": "hh.ru и Хабр Карьера", "trudvsem": "Работа России", "superjob": "SuperJob"}


@dataclass
class CollectResult:
    source: str
    vacancies: list[Vacancy] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    failed_queries: list[str] = field(default_factory=list)
    skipped: int = 0
    already_known: int = 0  # Exa: найдены, но уже в базе — выжимку не заказывали
    cost_dollars: float = 0.0


def make_collector(
    source: str, sites: list[str] | None = None, known_ids: set[str] | None = None
) -> Collector:
    if source == "exa":
        return ExaCollector(sites, known_ids=known_ids)
    return COLLECTORS[source]()


def collect(
    source: str,
    queries: list[str],
    *,
    remote_only: bool,
    region_code: str | None,
    limit: int,
    sites: list[str] | None = None,
    on_progress: Callable[[str], None] = lambda _: None,
    engine: Engine | None = None,
) -> CollectResult:
    # Своя база у каждого пользователя: сохраняем туда, откуда запущен поиск
    engine = engine or get_engine()
    init_db(engine)
    with Session(engine) as session:
        known_ids = set(session.exec(select(Vacancy.id)).all())
    collector = make_collector(source, sites, known_ids)
    result = CollectResult(source)
    vacancies: dict[str, Vacancy] = {}

    for text in queries:
        query = SearchQuery(
            text=text, region_code=region_code, remote_only=remote_only, limit=limit
        )
        try:
            found = list(collector.fetch(query))
        except httpx.HTTPError as exc:  # один упавший запрос не должен терять результаты остальных
            log.warning("%s: запрос «%s» не выполнен: %s", source, text, exc)
            result.failed_queries.append(text)
            on_progress(f"«{text}»: не удалось загрузить, пропускаю")
            continue
        new = sum(v.id not in vacancies for v in found)
        vacancies.update((v.id, v) for v in found)
        on_progress(f"«{text}»: найдено {len(found)}, новых {new}")

    with Session(engine, expire_on_commit=False) as session:
        stats = save_vacancies(session, vacancies.values())

    result.vacancies = list(vacancies.values())
    result.created, result.updated = stats.created, stats.updated
    if isinstance(collector, ExaCollector):
        result.skipped, result.cost_dollars = collector.skipped, collector.cost_dollars
        result.already_known = collector.already_known
        if collector.already_known:
            on_progress(f"Уже в базе, повторно не разбирали: {collector.already_known}")
    return result
