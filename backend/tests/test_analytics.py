import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.advice import generate_advice
from app.api.main import create_app
from app.db import init_db
from app.models import Application, Match
from app.profile import save_profile
from app.tracker import compute_analytics, mark_no_response
from tests.conftest import FakeLLM, make_vacancy

TODAY = date(2026, 10, 19)


def memory_engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


# --- миграция старой базы --------------------------------------------------------------------


def test_init_db_adds_new_columns_to_old_table(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    # схема application до появления тона и даты смены этапа
    con.execute(
        "CREATE TABLE application (vacancy_id VARCHAR PRIMARY KEY, stage VARCHAR NOT NULL, "
        "notes VARCHAR NOT NULL, contact VARCHAR NOT NULL, applied_at DATE, "
        "cover_letter VARCHAR NOT NULL, cover_letter_subject VARCHAR NOT NULL, "
        "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
    )
    con.execute(
        "INSERT INTO application VALUES ('x', 'applied', '', '', NULL, 'текст', '', "
        "'2026-10-01', '2026-10-01')"
    )
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    init_db(engine)  # повторно — без ошибок

    with Session(engine) as s:
        a = s.get(Application, "x")
        assert a.cover_letter == "текст"  # данные не потеряны
        assert a.cover_letter_tone == ""  # старые строки получили пустую строку, не NULL
        assert a.stage_changed_at is None
    engine.dispose()


# --- авто «Без ответа» -----------------------------------------------------------------------


@pytest.fixture
def session():
    engine = memory_engine()
    init_db(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s


def add_app(s, n, stage, applied_days_ago=None, changed_days_ago=None, **kw):
    s.add(make_vacancy(n, f"Вакансия {n}", source=kw.pop("source", "hh.ru")))
    s.add(
        Application(
            vacancy_id=f"test:{n}",
            stage=stage,
            applied_at=TODAY - timedelta(days=applied_days_ago)
            if applied_days_ago is not None
            else None,
            stage_changed_at=(
                datetime.combine(TODAY - timedelta(days=changed_days_ago), datetime.min.time(), UTC)
                if changed_days_ago is not None
                else None
            ),
            **kw,
        )
    )
    s.commit()


def test_mark_no_response_after_10_days(session):
    add_app(session, 1, "applied", applied_days_ago=11)
    add_app(session, 2, "applied", applied_days_ago=9)  # ещё рано
    add_app(session, 3, "applied", applied_days_ago=20, changed_days_ago=3)  # недавно трогали
    add_app(session, 4, "interview", applied_days_ago=30)  # уже ответили
    add_app(session, 5, "applied")  # без даты отклика

    assert mark_no_response(session, TODAY) == 1

    stages = {i: session.get(Application, f"test:{i}").stage for i in range(1, 6)}
    assert stages == {
        1: "no_response",
        2: "applied",
        3: "applied",
        4: "interview",
        5: "applied",
    }
    assert mark_no_response(session, TODAY) == 0  # повторно ничего не меняет


def test_compute_analytics(session):
    fp = "profile-fp"
    add_app(session, 1, "interview", 5, cover_letter="п", cover_letter_tone="friendly")
    add_app(session, 2, "rejected", 5, cover_letter="п", cover_letter_tone="business")
    add_app(session, 3, "no_response", 15, cover_letter="п", cover_letter_tone="business")
    add_app(session, 4, "applied", 2, source="career.habr.com")
    add_app(session, 5, "interesting")  # не отправлено — в статистику откликов не входит
    for n, score, missing in [(1, 85, ["SQL"]), (2, 70, ["sql", "Kafka"]), (3, 50, ["UML"])]:
        session.add(
            Match(vacancy_id=f"test:{n}", profile_fingerprint=fp, content_hash="x",
                  score=score, similarity=0.5, missing_skills=missing)
        )  # fmt: skip
    session.commit()

    stats = compute_analytics(session, fp, TODAY)

    assert (stats["sent"], stats["positive"], stats["rejected"]) == (4, 1, 1)
    assert (stats["no_response"], stats["waiting"]) == (1, 1)
    assert stats["response_rate"] == 0.25
    assert stats["sent_last_7_days"] == 3
    letters = {r["label"]: (r["sent"], r["positive"]) for r in stats["by_letter"]}
    assert letters == {"Деловой тон": (2, 0), "Дружелюбный тон": (1, 1), "Без письма": (1, 0)}
    scores = {r["label"]: r["sent"] for r in stats["by_score"]}
    assert scores == {"80+": 1, "60–79": 1, "до 60": 1, "без оценки": 1}
    # пробелы берутся только из вакансий с баллом 60+, регистр не важен
    assert stats["top_gaps"] == [{"skill": "SQL", "count": 2}, {"skill": "Kafka", "count": 1}]


def test_analytics_empty(session):
    stats = compute_analytics(session, None, TODAY)
    assert stats["sent"] == 0 and stats["response_rate"] is None and stats["top_gaps"] == []


def test_generate_advice_prompt_and_parsing(profile, session):
    add_app(session, 1, "no_response", 15, cover_letter="п", cover_letter_tone="business")
    stats = compute_analytics(session, None, TODAY)
    llm = FakeLLM(
        [{"summary": "Мало откликов", "resume": ["Добавьте SQL", " "], "letters": "не список"}]
    )

    advice = generate_advice(profile, stats, llm)

    assert advice.summary == "Мало откликов"
    assert advice.resume == ["Добавьте SQL"]
    assert advice.letters == [] and advice.search == []
    assert advice.based_on_sent == 1
    _, user, _ = llm.chat_calls[0]
    assert "статистика предварительная" in user
    assert "Деловой тон: 0 из 1" in user


# --- API ---------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, profile):
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)
    llm = FakeLLM()
    app = create_app(
        memory_engine(), profile_path, serve_frontend=False, llm_factory=lambda: llm,
        resume_path=tmp_path / "none.pdf",
    )  # fmt: skip
    c = TestClient(app)
    c.llm = llm
    return c


def test_stage_change_time_and_letter_tone(client):
    engine = client.app.state.refresh._engine
    with Session(engine) as s:
        s.add(make_vacancy(1, "Аналитик"))
        s.commit()

    first = client.put("/api/applications/test:1", json={"stage": "interesting"}).json()
    assert first["stage_changed_at"] is not None
    same = client.put("/api/applications/test:1", json={"notes": "x"}).json()
    assert same["stage_changed_at"] == first["stage_changed_at"]  # этап не менялся
    moved = client.put("/api/applications/test:1", json={"stage": "applied"}).json()
    assert moved["stage_changed_at"] != first["stage_changed_at"]

    client.llm.answers.append({"subject": "Т", "letter": "Письмо"})
    letter = client.post("/api/applications/test:1/cover-letter", json={"tone": "friendly"}).json()
    assert letter["cover_letter_tone"] == "friendly"

    assert client.put("/api/applications/test:1", json={"stage": "no_response"}).status_code == 200


def test_analytics_and_advice_endpoints(client):
    engine = client.app.state.refresh._engine
    with Session(engine) as s:
        s.add(make_vacancy(1, "Аналитик"))
        s.add(Application(vacancy_id="test:1", stage="interview", applied_at=date.today()))
        s.commit()

    stats = client.get("/api/analytics").json()
    assert stats["sent"] == 1 and stats["positive"] == 1
    assert stats["advice"] is None

    client.llm.answers.append(
        {"summary": "Хорошо", "resume": ["Совет"], "letters": [], "search": []}
    )
    advice = client.post("/api/analytics/advice").json()
    assert advice["summary"] == "Хорошо"
    # совет сохранён и отдаётся вместе с аналитикой
    assert client.get("/api/analytics").json()["advice"]["resume"] == ["Совет"]


def test_sent_list_and_test_task_counts_as_response(session):
    add_app(session, 1, "applied", 3, notes="ждём")
    add_app(session, 2, "test_task", 6, cover_letter="п")
    add_app(session, 3, "interesting")  # не отправлено — в списке не нужно

    stats = compute_analytics(session, None, TODAY)

    assert [r["id"] for r in stats["sent_list"]] == ["test:1", "test:2"]  # свежие сверху
    first = stats["sent_list"][0]
    assert (first["stage"], first["days_since"], first["notes"]) == ("applied", 3, "ждём")
    assert stats["sent_list"][1]["has_letter"] is True
    assert stats["positive"] == 1  # тестовое задание — это ответ работодателя
    assert stats["response_rate"] == 0.5


def test_test_task_stage_accepted_by_api(client):
    engine = client.app.state.refresh._engine
    with Session(engine) as s:
        s.add(make_vacancy(1, "Аналитик"))
        s.commit()
    r = client.put("/api/applications/test:1", json={"stage": "test_task"})
    assert r.status_code == 200 and r.json()["stage"] == "test_task"
