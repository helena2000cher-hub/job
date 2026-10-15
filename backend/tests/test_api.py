import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.api.main import create_app
from app.models import Match
from app.profile import save_profile
from tests.conftest import make_vacancy


@pytest.fixture
def engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


@pytest.fixture
def profile_path(tmp_path, profile):
    path = tmp_path / "profile.json"
    save_profile(profile, path)
    return path


def seed(engine, profile):
    fp = profile.fingerprint()
    with Session(engine) as s:
        s.add_all(
            [
                make_vacancy(1, "Бизнес-аналитик", company="А", salary_from=150_000),
                make_vacancy(2, "Системный аналитик", source="hh.ru"),
                make_vacancy(3, "Оператор"),
                make_vacancy(4, "Без оценки"),
            ]
        )
        s.add_all(
            [
                Match(vacancy_id="test:1", profile_fingerprint=fp, content_hash="x", score=85,
                      similarity=0.7, verdict="Подходит", matched_skills=["BPMN"]),
                Match(vacancy_id="test:2", profile_fingerprint=fp, content_hash="x", score=70,
                      similarity=0.6),
                Match(vacancy_id="test:3", profile_fingerprint="старый", content_hash="x",
                      score=99, similarity=0.9),
            ]
        )  # fmt: skip
        s.commit()


@pytest.fixture
def client(engine, profile_path, profile):
    calls = []

    def fake_runner(state, sources, engine, path):
        calls.append(sources)
        state.log.append("собрано")

    app = create_app(engine, profile_path, fake_runner, serve_frontend=False)
    seed(engine, profile)
    c = TestClient(app)
    c.runner_calls = calls
    return c


def test_feed_returns_current_profile_matches_sorted(client):
    data = client.get("/api/feed").json()

    assert [i["title"] for i in data["items"]] == ["Бизнес-аналитик", "Системный аналитик"]
    assert data["items"][0]["verdict"] == "Подходит"
    assert data["items"][0]["matched_skills"] == ["BPMN"]
    assert data["total_vacancies"] == 4
    assert data["scored"] == 2  # оценка под старый профиль не считается
    assert data["sources"] == {"test": 1, "hh.ru": 1}
    assert data["profile_ready"] is True


def test_feed_filters(client):
    assert len(client.get("/api/feed", params={"min_score": 80}).json()["items"]) == 1
    hh = client.get("/api/feed", params={"source": "hh.ru"}).json()["items"]
    assert [i["id"] for i in hh] == ["test:2"]


def test_mark_hide_and_save(client):
    assert client.put("/api/vacancies/test:1/mark", json={"status": "hidden"}).status_code == 200
    assert [i["id"] for i in client.get("/api/feed").json()["items"]] == ["test:2"]
    hidden = client.get("/api/feed", params={"view": "hidden"}).json()["items"]
    assert [i["id"] for i in hidden] == ["test:1"]

    client.put("/api/vacancies/test:2/mark", json={"status": "saved"})
    saved = client.get("/api/feed", params={"view": "saved"}).json()["items"]
    assert [(i["id"], i["mark"]) for i in saved] == [("test:2", "saved")]

    client.put("/api/vacancies/test:1/mark", json={"status": None})
    assert len(client.get("/api/feed").json()["items"]) == 2
    assert client.put("/api/vacancies/nope/mark", json={"status": "saved"}).status_code == 404


def test_vacancy_detail(client):
    data = client.get("/api/vacancies/test:1").json()
    assert data["title"] == "Бизнес-аналитик"
    assert data["score"] == 85
    assert "requirements" in data
    unscored = client.get("/api/vacancies/test:4").json()
    assert unscored["score"] is None
    assert client.get("/api/vacancies/nope").status_code == 404


def test_profile_get_and_update_invalidates_feed(client):
    profile = client.get("/api/profile").json()
    profile["skills"].append("SQL")

    saved = client.put("/api/profile", json=profile).json()

    assert "SQL" in saved["skills"]
    # профиль изменился — старые оценки больше не показываются, нужен пересчёт
    assert client.get("/api/feed").json()["items"] == []


def test_refresh_runs_in_background(client):
    response = client.post("/api/refresh", json={"sources": ["exa"]})
    assert response.status_code == 202

    for _ in range(50):
        state = client.get("/api/refresh").json()
        if not state["running"]:
            break
        time.sleep(0.02)
    assert state["log"] == ["собрано", "Готово"]
    assert state["error"] is None
    assert client.runner_calls == [["exa"]]


def test_refresh_validation(client):
    assert client.post("/api/refresh", json={"sources": ["vk"]}).status_code == 400
    # пустой список — только пересчёт оценок
    assert client.post("/api/refresh", json={"sources": []}).status_code == 202


def test_refresh_rejects_parallel_runs(engine, profile_path):
    import threading

    gate = threading.Event()
    app = create_app(engine, profile_path, lambda *a: gate.wait(2), serve_frontend=False)
    c = TestClient(app)
    assert c.post("/api/refresh", json={}).status_code == 202
    assert c.post("/api/refresh", json={}).status_code == 409
    gate.set()


def test_no_profile(engine, tmp_path):
    c = TestClient(create_app(engine, tmp_path / "none.json", serve_frontend=False))
    assert c.get("/api/profile").status_code == 404
    assert c.get("/api/feed").json()["profile_ready"] is False
    assert c.post("/api/refresh", json={}).status_code == 400
