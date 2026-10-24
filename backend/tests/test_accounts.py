import re
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.accounts import Accounts, check_password, hash_password
from app.api.auth import COOKIE_NAME, Auth
from app.api.main import create_app
from app.models import Application
from app.oauth import VK, Yandex, challenge
from app.profile import save_profile
from tests.conftest import make_vacancy
from tests.test_auth import PASSWORD, SECRET, login, memory_engine

USER_PASSWORD = "user password 1"


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))

    def last_token(self) -> str:
        return re.search(r"token=([\w-]+)", self.sent[-1][2]).group(1)


def oauth_transport(requests: list[httpx.Request]) -> httpx.MockTransport:
    """Yandex ID and VK ID answers: token exchange and user info."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        if url.startswith("https://oauth.yandex.ru/token"):
            return httpx.Response(200, json={"access_token": "ya-token", "token_type": "bearer"})
        if url.startswith("https://login.yandex.ru/info"):
            assert request.headers["Authorization"] == "OAuth ya-token"
            return httpx.Response(
                200, json={"id": "777", "default_email": "Ya@Yandex.ru", "real_name": "Анна"}
            )
        if url.startswith("https://id.vk.ru/oauth2/auth"):
            return httpx.Response(200, json={"access_token": "vk-token", "user_id": 42})
        if url.startswith("https://id.vk.ru/oauth2/user_info"):
            return httpx.Response(
                200, json={"user": {"user_id": "42", "first_name": "Пётр", "last_name": "И."}}
            )
        return httpx.Response(404, json={"error": "unexpected"})

    return httpx.MockTransport(handler)


@pytest.fixture
def mailer():
    return FakeMailer()


@pytest.fixture
def oauth_requests():
    return []


@pytest.fixture
def site(tmp_path, profile, mailer, oauth_requests):
    owner_engine = memory_engine()
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)
    app = create_app(
        owner_engine,
        profile_path,
        runner=lambda *args: None,
        serve_frontend=False,
        auth=Auth(PASSWORD, SECRET),
        demo_engine=memory_engine(),
        demo_profile_path=tmp_path / "demo_profile.json",
        accounts=Accounts(memory_engine()),
        users_dir=tmp_path / "users",
        mailer=mailer,
        providers={"yandex": Yandex("ya-app"), "vk": VK("vk-app")},
        oauth_client=lambda: httpx.Client(transport=oauth_transport(oauth_requests)),
        llm_factory=lambda: pytest.fail("LLM must not be called"),
        limits={"refresh": 1, "letter": 5},
    )
    with Session(owner_engine) as s:
        s.add(make_vacancy(1, "Вакансия владельца"))
        s.add(Application(vacancy_id="test:1", stage="applied", notes="личное"))
        s.commit()
    return app


def register(client: TestClient, mailer: FakeMailer, email: str = "lena@example.ru"):
    response = client.post(
        "/api/auth/register", json={"email": email, "password": USER_PASSWORD, "consent": True}
    )
    assert response.status_code == 200, response.text
    return mailer.last_token()


def registered(site, mailer, email: str = "lena@example.ru") -> TestClient:
    client = TestClient(site)
    token = register(client, mailer, email)
    assert client.get(f"/api/auth/verify?token={token}", follow_redirects=False).status_code == 303
    return client


# --- пароли ---------------------------------------------------------------------------------------


def test_password_hash():
    stored = hash_password("secret 123")
    assert stored.startswith("scrypt$") and "secret" not in stored
    assert check_password("secret 123", stored)
    assert not check_password("secret 124", stored)
    assert not check_password("x", "garbage")
    assert hash_password("same") != hash_password("same")  # соль у каждого своя


# --- регистрация по почте ------------------------------------------------------------------------


def test_register_verify_and_login(site, mailer):
    client = TestClient(site)
    token = register(client, mailer)
    to, subject, text = mailer.sent[-1]
    assert to == "lena@example.ru" and "Подтвердите" in subject
    assert "http://localhost:8000/api/auth/verify?token=" in text

    # до подтверждения не войти — письмо уходит ещё раз
    response = client.post(
        "/api/auth/login", json={"email": "lena@example.ru", "password": USER_PASSWORD}
    )
    assert response.status_code == 403 and len(mailer.sent) == 2

    response = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
    assert response.headers["location"] == "/#/profile"
    me = client.get("/api/auth/me").json()
    assert me["role"] == "user" and me["email"] == "lena@example.ru"
    assert me["internals"] is False  # стоимость и сервисы пользователям не показываем

    other = TestClient(site)
    response = other.post(
        "/api/auth/login", json={"email": " LENA@example.ru ", "password": USER_PASSWORD}
    )
    assert response.status_code == 200 and response.json()["role"] == "user"
    assert login(other, "wrong").status_code == 401  # пароль владельца — отдельно


def test_register_validation(site, mailer):
    client = TestClient(site)

    def post(**body):
        return client.post("/api/auth/register", json={"consent": True} | body)

    assert post(email="lena@example.ru", password="12345678", consent=False).status_code == 400
    assert post(email="not-an-email", password=USER_PASSWORD).status_code == 400
    assert post(email="lena@example.ru", password="short").status_code == 400

    registered(site, mailer)
    assert post(email="lena@example.ru", password=USER_PASSWORD).status_code == 400  # уже есть


def test_verify_link_survives_prefetch_and_wrong_password(site, mailer):
    client = TestClient(site)
    token = register(client, mailer)
    TestClient(site).get(f"/api/auth/verify?token={token}")  # почтовик проверил ссылку
    response = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
    assert response.headers["location"] == "/#/profile"  # человек всё равно входит
    bad = TestClient(site).get("/api/auth/verify?token=forged", follow_redirects=False)
    assert bad.headers["location"] == "/#/login?error=link"

    response = TestClient(site).post(
        "/api/auth/login", json={"email": "lena@example.ru", "password": "wrong password"}
    )
    assert response.status_code == 401


def test_forgot_and_reset_logs_out_old_sessions(site, mailer):
    old = registered(site, mailer)
    stranger = TestClient(site)
    assert stranger.post("/api/auth/forgot", json={"email": "nobody@example.ru"}).status_code == 200
    sent = len(mailer.sent)

    assert stranger.post("/api/auth/forgot", json={"email": "lena@example.ru"}).status_code == 200
    assert len(mailer.sent) == sent + 1 and "#/reset?token=" in mailer.sent[-1][2]
    token = mailer.last_token()

    assert (
        stranger.post("/api/auth/reset", json={"token": token, "password": "x"}).status_code == 400
    )
    response = stranger.post("/api/auth/reset", json={"token": token, "password": "new password"})
    assert response.status_code == 200 and response.json()["role"] == "user"

    assert old.get("/api/auth/me").json()["role"] == "demo"  # старая сессия больше не действует
    assert (
        stranger.post(
            "/api/auth/reset", json={"token": token, "password": "again pass"}
        ).status_code
        == 400
    )


def test_mail_rate_limit(site, mailer):
    client = TestClient(site)
    for _ in range(5):
        register(client, mailer)
    response = client.post(
        "/api/auth/register",
        json={"email": "lena@example.ru", "password": USER_PASSWORD, "consent": True},
    )
    assert response.status_code == 429


def test_registration_off_without_accounts(tmp_path, profile):
    app = create_app(memory_engine(), tmp_path / "p.json", serve_frontend=False)
    client = TestClient(app)
    assert client.get("/api/auth/me").json()["registration"] is False
    response = client.post(
        "/api/auth/register", json={"email": "a@b.ru", "password": USER_PASSWORD, "consent": True}
    )
    assert response.status_code == 404


# --- данные пользователей ------------------------------------------------------------------------


def test_users_see_only_their_own_data(site, mailer, tmp_path):
    anna = registered(site, mailer, "anna@example.ru")
    boris = registered(site, mailer, "boris@example.ru")

    feed = anna.get("/api/feed").json()
    assert feed["items"] == [] and feed["profile_ready"] is False
    assert anna.get("/api/applications").json() == []
    assert anna.get("/api/vacancies/test:1").status_code == 404

    response = anna.post("/api/applications/manual", json={"title": "Аналитик", "company": "А"})
    assert response.status_code == 200
    assert [i["title"] for i in anna.get("/api/applications").json()] == ["Аналитик"]
    assert boris.get("/api/applications").json() == []

    owner = TestClient(site)
    login(owner)
    assert [i["title"] for i in owner.get("/api/applications").json()] == ["Вакансия владельца"]
    assert len(list((tmp_path / "users").iterdir())) == 2  # у каждого своя папка


def test_daily_limit_for_paid_actions(site, mailer, profile):
    client = registered(site, mailer)
    assert client.put("/api/profile", json=profile.model_dump(mode="json")).status_code == 200

    assert client.post("/api/refresh", json={"sources": []}).status_code == 202
    for _ in range(50):
        if not client.get("/api/refresh").json()["running"]:
            break
        time.sleep(0.02)
    response = client.post("/api/refresh", json={"sources": []})
    assert response.status_code == 429 and "Лимит" in response.json()["detail"]

    limits = client.get("/api/limits").json()
    assert limits["refresh"] == {"used": 1, "limit": 1}
    assert limits["letter"] == {"used": 0, "limit": 5}

    owner = TestClient(site)
    login(owner)
    assert owner.get("/api/limits").json() == {}  # у владельца лимитов нет


def test_delete_account(site, mailer, tmp_path):
    client = registered(site, mailer)
    client.post("/api/applications/manual", json={"title": "Аналитик"})
    assert client.delete("/api/auth/account").status_code == 204
    assert not any((tmp_path / "users").iterdir())
    client.cookies.clear()
    response = client.post(
        "/api/auth/login", json={"email": "lena@example.ru", "password": USER_PASSWORD}
    )
    assert response.status_code == 401

    owner = TestClient(site)
    login(owner)
    assert owner.delete("/api/auth/account").status_code == 403  # владельца так не удалить


# --- Яндекс ID и VK ID ----------------------------------------------------------------------------


def start_oauth(client: TestClient, provider: str) -> dict[str, list[str]]:
    response = client.get(f"/api/auth/oauth/{provider}/start", follow_redirects=False)
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)


def test_yandex_login_creates_and_reuses_user(site, oauth_requests):
    client = TestClient(site)
    assert client.get("/api/auth/me").json()["providers"] == {"yandex": "Яндекс ID", "vk": "VK ID"}

    query = start_oauth(client, "yandex")
    assert query["client_id"] == ["ya-app"] and query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://localhost:8000/api/auth/oauth/yandex/callback"]
    state = query["state"][0]

    response = client.get(
        f"/api/auth/oauth/yandex/callback?code=abc&state={state}", follow_redirects=False
    )
    assert response.headers["location"] == "/#/feed"
    me = client.get("/api/auth/me").json()
    assert me["role"] == "user" and me["email"] == "ya@yandex.ru" and me["name"] == "Анна"

    token_form = parse_qs(oauth_requests[0].content.decode())
    assert token_form["code"] == ["abc"] and token_form["client_id"] == ["ya-app"]
    assert challenge(token_form["code_verifier"][0]) == query["code_challenge"][0]

    # повторный вход — тот же аккаунт и та же папка с данными
    client.post("/api/applications/manual", json={"title": "Аналитик"})
    again = TestClient(site)
    state = start_oauth(again, "yandex")["state"][0]
    again.get(f"/api/auth/oauth/yandex/callback?code=x&state={state}", follow_redirects=False)
    assert [i["title"] for i in again.get("/api/applications").json()] == ["Аналитик"]


def test_yandex_links_to_existing_email_account(site, mailer):
    registered(site, mailer, "ya@yandex.ru")
    client = TestClient(site)
    state = start_oauth(client, "yandex")["state"][0]
    client.get(f"/api/auth/oauth/yandex/callback?code=abc&state={state}", follow_redirects=False)
    me = client.get("/api/auth/me").json()
    assert me["email"] == "ya@yandex.ru"
    # вход по паролю у того же аккаунта по-прежнему работает
    response = TestClient(site).post(
        "/api/auth/login", json={"email": "ya@yandex.ru", "password": USER_PASSWORD}
    )
    assert response.status_code == 200


def test_vk_login_without_email(site, oauth_requests):
    client = TestClient(site)
    query = start_oauth(client, "vk")
    assert query["scope"] == ["email"] and query["client_id"] == ["vk-app"]
    state = query["state"][0]

    url = f"/api/auth/oauth/vk/callback?code=c1&state={state}&device_id=dev1"
    assert client.get(url, follow_redirects=False).headers["location"] == "/#/feed"
    me = client.get("/api/auth/me").json()
    assert me["role"] == "user" and me["email"] is None and me["name"] == "Пётр И."

    token_request = oauth_requests[0]
    assert token_request.url.params["device_id"] == "dev1"
    assert token_request.url.params["state"] == state
    assert parse_qs(token_request.content.decode())["code"] == ["c1"]


def test_oauth_rejects_wrong_state_and_unknown_provider(site, oauth_requests):
    client = TestClient(site)
    start_oauth(client, "yandex")
    response = client.get(
        "/api/auth/oauth/yandex/callback?code=abc&state=forged", follow_redirects=False
    )
    assert response.headers["location"] == "/#/login?error=oauth"
    assert oauth_requests == []  # к Яндексу даже не обращались

    other = TestClient(site)  # без cookie из /start — чужая ссылка
    response = other.get("/api/auth/oauth/yandex/callback?code=a&state=s", follow_redirects=False)
    assert response.headers["location"] == "/#/login?error=oauth"
    assert other.get("/api/auth/oauth/google/start", follow_redirects=False).status_code == 404
    assert COOKIE_NAME not in other.cookies
