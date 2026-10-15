from typing import Any

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import Vacancy
from app.profile import Preferences, Profile


class FakeLLM:
    """Deterministic stand-in for PolzaLLM: no network, records calls."""

    def __init__(self, answers: list[dict[str, Any]] | None = None) -> None:
        self.answers = answers or []
        self.chat_calls: list[tuple[str, str, bool]] = []
        self.embed_calls: list[list[str]] = []

    def chat_json(self, system: str, user: str, *, smart: bool = False) -> dict[str, Any]:
        self.chat_calls.append((system, user, smart))
        if self.answers:
            return self.answers.pop(0)
        # по умолчанию: балл тем выше, чем больше в вакансии слова «аналитик»
        return {"score": 85 if "аналитик" in user.split("ВАКАНСИЯ")[1].lower() else 30}

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        return [[float("аналитик" in t.lower()), float("python" in t.lower()), 1.0] for t in texts]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def profile() -> Profile:
    return Profile(
        headline="Бизнес-аналитик",
        target_roles=["Бизнес-аналитик"],
        skills=["BPMN", "Python"],
        summary="аналитик",
        preferences=Preferences(remote_only=True, salary_min=100_000),
    )


def make_vacancy(n: int, title: str, **kwargs: Any) -> Vacancy:
    defaults: dict[str, Any] = {
        "id": f"test:{n}",
        "source": "test",
        "external_id": str(n),
        "title": title,
        "url": f"https://example.org/{n}",
        "is_remote": True,
    }
    return Vacancy(**(defaults | kwargs))
