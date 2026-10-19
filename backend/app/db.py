import logging
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import String, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.sql.sqltypes import AutoString

from app.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    connect_args = {}
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        # веб-сервер и фоновое обновление работают с базой из разных потоков
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args)


def init_db(engine: Engine | None = None) -> None:
    import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata

    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)


def add_missing_columns(engine: Engine) -> None:
    """Lightweight migration: new model fields become nullable columns in existing tables.

    create_all() creates only missing tables, so without this an old data/jobs.db would break
    every time a field is added. Renames and type changes are not handled — not needed so far.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl_type = column.type.compile(dialect=engine.dialect)
                default = _default_sql(column)
                conn.execute(
                    text(
                        f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}{default}'
                    )
                )
                log.info("db: added column %s.%s", table.name, column.name)


def _default_sql(column) -> str:
    # Умолчания вида `str = ""` SQLModel хранит в Python, а не в схеме. Старые строки иначе
    # получили бы NULL в поле, которое модель считает обязательной строкой.
    if not column.nullable and isinstance(column.type, String | AutoString):
        return " DEFAULT ''"
    return ""


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
