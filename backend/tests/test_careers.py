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


def _profile_with_cards():
    from app.careers import CareerOption, CareerSuggestions
    from app.profile import Profile

    cards = CareerSuggestions(
        options=[
            CareerOption(title="AI-инженер / LLM-разработчик", kind="core",
                         queries=["AI инженер", "LLM разработчик"]),
            CareerOption(title="Бизнес-аналитик", kind="adjacent",
                         queries=["бизнес-аналитик", "ai инженер"]),  # дубль другого регистра
        ]
    )  # fmt: skip
    return Profile(
        headline="x",
        target_roles=["Бизнес-аналитик", "ai-инженер / llm-разработчик", "Финансовый аналитик"],
        skills=["Python"],
        search_queries=["старый запрос из резюме"],
        careers=cards,
    )


def test_query_plan_groups_queries_by_profession():
    plan = _profile_with_cards().query_plan()
    assert plan == [
        ("Бизнес-аналитик", ["бизнес-аналитик", "ai инженер"]),
        ("ai-инженер / llm-разработчик", ["AI инженер", "LLM разработчик"]),  # регистр не важен
        ("Финансовый аналитик", ["Финансовый аналитик"]),  # без карточки — по названию
    ]


def test_effective_queries_only_selected_professions():
    profile = _profile_with_cards()
    assert profile.effective_queries() == [
        "бизнес-аналитик", "ai инженер", "LLM разработчик", "Финансовый аналитик"
    ]  # fmt: skip
    assert "старый запрос из резюме" not in profile.effective_queries()

    profile.target_roles = []
    assert profile.effective_queries() == ["старый запрос из резюме"]  # профессий нет — старое


def test_saving_profile_syncs_queries_with_professions(tmp_path, profile):
    path = tmp_path / "profile.json"
    save_profile(profile, path)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    client = TestClient(create_app(engine, path, serve_frontend=False))
    data = _profile_with_cards().model_dump(mode="json")

    saved = client.put("/api/profile", json=data).json()

    assert saved["search_queries"] == [
        "бизнес-аналитик", "ai инженер", "LLM разработчик", "Финансовый аналитик"
    ]  # fmt: skip
    assert load_profile(path).search_queries == saved["search_queries"]


def test_search_modes_professions_skills_both():
    profile = _profile_with_cards()
    profile.search_skills = ["n8n", "RAG", "бизнес-аналитик"]  # дубль с запросом профессии

    profile.search_mode = "professions"
    assert "n8n" not in profile.effective_queries()

    profile.search_mode = "skills"
    assert profile.effective_queries() == ["n8n", "RAG", "бизнес-аналитик"]

    profile.search_mode = "both"
    queries = profile.effective_queries()
    assert queries[:4] == [
        "бизнес-аналитик",
        "ai инженер",
        "LLM разработчик",
        "Финансовый аналитик",
    ]
    assert queries[4:] == ["n8n", "RAG"]  # без дублей


def test_search_settings_do_not_reset_scores():
    profile = _profile_with_cards()
    before = profile.fingerprint()
    profile.search_mode = "both"
    profile.search_skills = ["n8n"]
    profile.search_queries = ["что-то"]
    assert profile.fingerprint() == before  # поиск ≠ оценка: оценки не сбрасываются
    profile.skills.append("SQL")
    assert profile.fingerprint() != before  # а навыки на оценку влияют
