from collections.abc import Iterator

from sqlmodel import Session, select

from app import collecting
from app.collectors.base import Collector, SearchQuery
from app.models import Vacancy
from tests.conftest import make_vacancy
from tests.test_auth import memory_engine


class FakeCollector(Collector):
    name = "fake"

    def fetch(self, query: SearchQuery) -> Iterator[Vacancy]:
        yield make_vacancy(1, f"Вакансия по запросу {query.text}")


def test_collect_saves_into_given_engine_and_passes_known_ids(monkeypatch):
    seen: dict = {}

    def fake_make_collector(source, sites=None, known_ids=None):
        seen["known"] = known_ids
        return FakeCollector()

    monkeypatch.setattr(collecting, "make_collector", fake_make_collector)
    user_db = memory_engine()
    with Session(user_db) as s:  # одна вакансия уже есть в базе пользователя
        collecting.init_db(user_db)
        s.add(make_vacancy(9, "Старая"))
        s.commit()

    result = collecting.collect(
        "fake", ["аналитик"], remote_only=True, region_code=None, limit=5, engine=user_db
    )

    assert seen["known"] == {"test:9"}  # Exa не будет платить за уже известные вакансии
    assert result.created == 1
    with Session(user_db) as s:
        assert {v.id for v in s.exec(select(Vacancy))} == {"test:1", "test:9"}
