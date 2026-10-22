import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from app.api.main import create_app
from app.careers import suggest_careers
from app.profile import load_profile, save_profile
from tests.conftest import FakeLLM

ANSWER = {
    "options": [
        {"title": "Маркетолог-аналитик", "field": "Маркетинг", "kind": "new_field", "fit": 55,
         "why": "Аналитика воронок", "transferable": ["SQL"], "gaps": ["Яндекс Директ"],
         "queries": ["маркетинг аналитик"]},
        {"title": "Бизнес-аналитик", "field": "IT", "kind": "core", "fit": 90,
         "transferable": ["BPMN", "SQL"], "queries": ["бизнес-аналитик", "аналитик BPMN"]},
        {"title": "бизнес-аналитик ", "kind": "core", "fit": 80},  # дубль другим регистром
        {"title": "Продакт-менеджер", "kind": "adjacent", "fit": "70", "gaps": "не список"},
        {"title": "", "kind": "core"},  # без названия — отбрасываем
        {"title": "Системный аналитик", "kind": "странный", "fit": 140},
    ]
}  # fmt: skip


def test_suggest_careers_normalizes_and_sorts():
    llm = FakeLLM([ANSWER])
    result = suggest_careers(["BPMN", "SQL"], "Make — курс", 5, ["Финтех"], llm)

    titles = [(o.title, o.kind, o.fit) for o in result.options]
    assert titles == [
        ("Бизнес-аналитик", "core", 90),
        ("Системный аналитик", "adjacent", 100),  # неизвестный вид → смежная, балл обрезан
        ("Продакт-менеджер", "adjacent", 70),
        ("Маркетолог-аналитик", "new_field", 55),
    ]
    assert result.options[2].gaps == []
    assert result.skills_snapshot == ["BPMN", "SQL"]
    _, user, _ = llm.chat_calls[0]
    assert "НАВЫКИ: BPMN, SQL" in user and "Make — курс" in user and "5 лет" in user


def test_suggest_careers_needs_skills():
    with pytest.raises(ValueError):
        suggest_careers([], " ", None, [], FakeLLM())


def test_careers_endpoint_saves_without_touching_scores(tmp_path, profile):
    path = tmp_path / "profile.json"
    save_profile(profile, path)
    fingerprint = profile.fingerprint()
    llm = FakeLLM([ANSWER])
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    client = TestClient(
        create_app(engine, path, serve_frontend=False, llm_factory=lambda: llm,
                   resume_path=tmp_path / "none.pdf")
    )  # fmt: skip

    data = client.post("/api/profile/careers").json()

    assert data["careers"]["options"][0]["title"] == "Бизнес-аналитик"
    saved = load_profile(path)
    assert saved.careers is not None and len(saved.careers.options) == 4
    assert saved.fingerprint() == fingerprint  # подсказки профессий не сбрасывают оценки
    # прошлая должность в подбор не передаётся — подсказки идут от навыков
    _, user, _ = llm.chat_calls[0]
    assert profile.headline not in user
