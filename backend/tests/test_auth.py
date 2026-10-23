import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.api.auth import COOKIE_NAME, Auth
from app.api.main import create_app
from app.demo import SEED_PATH, reset_demo
from app.models import Application, Match, Vacancy
from app.profile import save_profile
from tests.conftest import make_vacancy

PASSWORD = "correct horse battery staple"
SECRET = "s" * 40


def memory_engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


# --- Auth ---------------------------------------------------------------------------------------


def test_token_roundtrip_and_tampering():
    auth = Auth(PASSWORD, SECRET)
    token = auth.issue()
    assert auth.verify(token)
    expires, sig = token.split(".")
    assert not auth.verify(f"{int(expires) + 1000}.{sig}")  # продлить срок подделкой нельзя
    assert not auth.verify(token[:-1] + ("0" if token[-1] != "0" else "1"))
    assert not auth.verify(None)
    assert not auth.verify("garbage")


def test_token_expired_and_password_change_logs_out(monkeypatch):
    auth = Auth(PASSWORD, SECRET)
    token = auth.issue()
    assert not Auth("new password", SECRET).verify(token)

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 31 * 86400)
    assert not auth.verify(token)


def test_disabled_auth_and_weak_secret():
    assert Auth("", "").verify(None)  # без пароля — локальный режим, все владельцы
    with pytest.raises(ValueError):
        Auth(PASSWORD, "short")


def test_reset_demo_seeds_everything(tmp_path):
    engine = memory_engine()
    reset_demo(engine, tmp_path / "demo_profile.json")
    seed = json.loads(SEED_PATH.read_text("utf-8"))

    with Session(engine) as s:
        assert len(s.exec(select(Vacancy)).all()) == len(seed["vacancies"])
        assert len(s.exec(select(Match)).all()) == len(seed["vacancies"])
        assert len(s.exec(select(Application)).all()) == len(seed["applications"])
        assert all(v.url.startswith("https://example.com/") for v in s.exec(select(Vacancy)))


# --- API: владелец и демо ------------------------------------------------------------------------


@pytest.fixture
def site(tmp_path, profile):
    owner_engine = memory_engine()
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)
    app = create_app(
        owner_engine,
        profile_path,
        serve_frontend=False,
        auth=Auth(PASSWORD, SECRET),
        demo_engine=memory_engine(),
        demo_profile_path=tmp_path / "demo_profile.json",
        llm_factory=lambda: pytest.fail("LLM must not be called"),
    )
    with Session(owner_engine) as s:
        s.add(make_vacancy(1, "Секретная вакансия владельца"))
        s.add(Match(vacancy_id="test:1", profile_fingerprint=profile.fingerprint(),
                    content_hash="x", score=90, similarity=0.9))  # fmt: skip
        s.add(Application(vacancy_id="test:1", stage="applied", notes="личная заметка"))
        s.commit()
    return app


def login(client: TestClient, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"password": password})


def test_guest_sees_only_demo(site):
    guest = TestClient(site)

    assert guest.get("/api/auth/me").json() == {
        "role": "demo",
        "auth_enabled": True,
        "demo_available": True,
        "internals": True,
    }
    titles = [i["title"] for i in guest.get("/api/feed").json()["items"]]
    assert titles and "Секретная вакансия владельца" not in titles
    tracker = guest.get("/api/applications").json()
    assert all("личная" not in i["application"]["notes"] for i in tracker)
    assert guest.get("/api/vacancies/test:1").status_code == 404
    assert "Продуктовый" in guest.get("/api/profile").json()["headline"]


def test_guest_cannot_call_paid_or_owner_actions(site):
    guest = TestClient(site)
    assert guest.post("/api/refresh", json={"sources": []}).status_code == 403
    assert guest.post("/api/profile/rebuild").status_code == 403
    assert guest.post("/api/applications/demo:1/cover-letter", json={}).status_code == 403
    assert guest.get("/api/refresh").json()["log"] == []
    demo_profile = guest.get("/api/profile").json()
    assert guest.put("/api/profile", json=demo_profile).status_code == 403


def test_guest_sandbox_writes_do_not_touch_owner(site):
    guest = TestClient(site)
    assert guest.put("/api/applications/demo:3", json={"stage": "offer"}).status_code == 200

    owner = TestClient(site)
    login(owner)
    owner_tracker = owner.get("/api/applications").json()
    assert [(i["id"], i["application"]["stage"]) for i in owner_tracker] == [("test:1", "applied")]


def test_login_logout_flow(site):
    client = TestClient(site)
    assert login(client, "wrong").status_code == 401

    response = login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert COOKIE_NAME in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/auth/me").json()["role"] == "owner"
    assert [i["title"] for i in client.get("/api/feed").json()["items"]] == [
        "Секретная вакансия владельца"
    ]

    client.post("/api/auth/logout")
    client.cookies.clear()  # браузер удалит cookie по ответу logout
    assert client.get("/api/auth/me").json()["role"] == "demo"


def test_login_rate_limit(site):
    client = TestClient(site)
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    assert login(client).status_code == 429  # даже верный пароль — после 5 ошибок ждать


def test_forged_cookie_gets_demo(site):
    client = TestClient(site)
    client.cookies.set(COOKIE_NAME, "9999999999.deadbeef")
    assert client.get("/api/auth/me").json()["role"] == "demo"


def test_without_demo_guest_must_log_in(tmp_path, profile):
    app = create_app(
        memory_engine(), tmp_path / "p.json", serve_frontend=False, auth=Auth(PASSWORD, SECRET)
    )
    guest = TestClient(app)
    assert guest.get("/api/health").json() == {"status": "ok"}  # без входа — для docker
    assert guest.get("/api/feed").status_code == 401
    assert guest.get("/api/auth/me").status_code == 401
    assert login(guest).status_code == 200
    assert guest.get("/api/auth/me").json()["role"] == "owner"


def test_public_mode_hides_internals(tmp_path, profile):
    path = tmp_path / "p.json"
    save_profile(profile, path)
    app = create_app(memory_engine(), path, serve_frontend=False, public_mode=True)
    app.state.refresh.state.cost_dollars = 0.71
    client = TestClient(app)
    assert client.get("/api/auth/me").json()["internals"] is False
    assert client.get("/api/refresh").json()["cost_dollars"] == 0  # стоимость клиентам не видна
