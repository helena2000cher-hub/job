from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.api.main import create_app
from app.cover_letter import generate_cover_letter
from app.models import Application, Match, VacancyMark
from app.profile import save_profile
from tests.conftest import FakeLLM, make_vacancy

LETTER = {"subject": "Отклик: бизнес-аналитик", "letter": "Здравствуйте! Я бизнес-аналитик…"}


@pytest.fixture
def setup(tmp_path, profile):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)
    resume = tmp_path / "resume.txt"
    resume.write_text("Опыт: BPMN, 3 проекта. Тел. +7 912 345-67-89", encoding="utf-8")

    llm = FakeLLM()
    app = create_app(
        engine, profile_path, serve_frontend=False, llm_factory=lambda: llm, resume_path=resume
    )
    with Session(engine) as s:
        s.add_all([make_vacancy(1, "Бизнес-аналитик"), make_vacancy(2, "Системный аналитик")])
        s.add(
            Match(vacancy_id="test:1", profile_fingerprint=profile.fingerprint(),
                  content_hash="x", score=80, similarity=0.7, matched_skills=["BPMN"],
                  missing_skills=["SQL"])
        )  # fmt: skip
        s.commit()
    return TestClient(app), llm, engine


def test_save_from_feed_adds_to_tracker(setup):
    client, _, _ = setup
    client.put("/api/vacancies/test:1/mark", json={"status": "saved"})

    items = client.get("/api/applications").json()
    assert [(i["id"], i["application"]["stage"], i["score"]) for i in items] == [
        ("test:1", "interesting", 80)
    ]
    feed_item = client.get("/api/feed").json()["items"][0]
    assert (feed_item["mark"], feed_item["stage"]) == ("saved", "interesting")


def test_unsave_keeps_application_with_history(setup):
    client, _, _ = setup
    client.put("/api/vacancies/test:1/mark", json={"status": "saved"})
    client.put("/api/vacancies/test:1/mark", json={"status": None})
    assert client.get("/api/applications").json() == []  # нетронутая запись удаляется

    client.put("/api/applications/test:1", json={"stage": "applied"})
    client.put("/api/vacancies/test:1/mark", json={"status": None})
    assert len(client.get("/api/applications").json()) == 1  # отклик уже был — не теряем


def test_move_stage_sets_applied_date_and_keeps_other_fields(setup):
    client, _, _ = setup
    client.put("/api/applications/test:2", json={"notes": "HR Анна", "contact": "@anna"})

    moved = client.put("/api/applications/test:2", json={"stage": "applied"}).json()

    assert moved["stage"] == "applied"
    assert moved["applied_at"] == date.today().isoformat()
    assert (moved["notes"], moved["contact"]) == ("HR Анна", "@anna")

    cleared = client.put(
        "/api/applications/test:2", json={"stage": "interview", "applied_at": None}
    )
    assert cleared.json()["applied_at"] is None  # явный null — очистить дату


def test_invalid_stage_and_unknown_vacancy(setup):
    client, _, _ = setup
    assert client.put("/api/applications/test:1", json={"stage": "hired"}).status_code == 422
    assert client.put("/api/applications/nope", json={"stage": "applied"}).status_code == 404


def test_delete_application(setup):
    client, _, _ = setup
    client.put("/api/applications/test:1", json={"stage": "offer"})
    assert client.delete("/api/applications/test:1").status_code == 204
    assert client.get("/api/applications").json() == []
    assert client.delete("/api/applications/test:1").status_code == 204  # идемпотентно


def test_hide_does_not_remove_from_tracker(setup):
    client, _, _ = setup
    client.put("/api/applications/test:1", json={"stage": "applied"})
    client.put("/api/vacancies/test:1/mark", json={"status": "hidden"})

    assert client.get("/api/feed").json()["items"] == []
    assert len(client.get("/api/applications").json()) == 1


def test_cover_letter_endpoint_saves_into_application(setup):
    client, llm, _ = setup
    llm.answers.append(LETTER)

    result = client.post(
        "/api/applications/test:1/cover-letter", json={"tone": "friendly", "wishes": "коротко"}
    ).json()

    assert result["cover_letter"] == LETTER["letter"]
    assert result["cover_letter_subject"] == LETTER["subject"]
    assert result["stage"] == "interesting"  # вакансия попала в трекер
    system, user, smart = llm.chat_calls[0]
    assert smart is False  # письма пишет быстрая (дешёвая) модель
    assert "живой" in user and "коротко" in user
    assert "Не хватает: SQL" in user
    assert "345-67-89" not in user  # контакты из резюме вычищены


def test_cover_letter_errors(setup):
    client, llm, _ = setup
    assert client.post("/api/applications/nope/cover-letter", json={}).status_code == 404
    assert (
        client.post("/api/applications/test:1/cover-letter", json={"tone": "x"}).status_code == 422
    )


def test_generate_cover_letter_rejects_empty(profile, tmp_path):
    with pytest.raises(ValueError):
        generate_cover_letter(
            profile,
            make_vacancy(1, "А"),
            None,
            FakeLLM([{"letter": " "}]),
            resume_path=tmp_path / "no.pdf",
        )


def test_old_saved_marks_migrate_to_tracker(tmp_path, profile):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_app(engine, tmp_path / "p.json", serve_frontend=False)  # создаёт таблицы
    with Session(engine) as s:
        s.add(make_vacancy(1, "А"))
        s.add(VacancyMark(vacancy_id="test:1", status="saved"))
        s.commit()

    create_app(engine, tmp_path / "p.json", serve_frontend=False)

    with Session(engine) as s:
        assert s.get(VacancyMark, "test:1") is None
        assert s.get(Application, "test:1").stage == "interesting"
