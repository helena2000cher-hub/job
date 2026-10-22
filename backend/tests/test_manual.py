import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.api.auth import Auth
from app.api.main import create_app
from app.collectors.exa import fetch_vacancy, identify
from app.models import Vacancy
from app.profile import save_profile
from tests.conftest import make_vacancy

HH_URL = "https://perm.hh.ru/vacancy/138000001?from=applicant_recommendation&hhtmFrom=chat"


def memory_engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


@pytest.fixture
def setup(tmp_path, profile):
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)
    engine = memory_engine()
    calls: list[str] = []
    fetched: dict[str, Vacancy | None] = {}

    def fake_fetcher(url: str) -> Vacancy | None:
        calls.append(url)
        result = fetched.get("next")
        if isinstance(result, Exception):
            raise result
        return result

    app = create_app(
        engine, profile_path, serve_frontend=False, vacancy_fetcher=fake_fetcher,
        resume_path=tmp_path / "none.pdf",
    )  # fmt: skip
    return TestClient(app), engine, calls, fetched


def test_identify_canonicalizes_hh_links():
    ident = identify(HH_URL)
    assert ident.id == "hh.ru:138000001"
    assert ident.url == "https://hh.ru/vacancy/138000001"
    other = identify("https://company.ru/jobs/analyst")
    assert other.source == "company.ru" and other.id.startswith("company.ru:")


def test_add_by_link_fetches_vacancy(setup):
    client, engine, calls, fetched = setup
    fetched["next"] = Vacancy(
        id="hh.ru:138000001", source="hh.ru", external_id="138000001",
        title="Бизнес-ассистент собственника", company="Премиум Коттон",
        url="https://hh.ru/vacancy/138000001",
    )  # fmt: skip

    r = client.post("/api/applications/manual", json={"url": HH_URL, "stage": "questionnaire"})

    assert r.status_code == 200, r.text
    data = r.json()
    assert (data["vacancy_id"], data["fetched"]) == ("hh.ru:138000001", True)
    assert data["company"] == "Премиум Коттон"
    assert data["application"]["stage"] == "questionnaire"
    assert data["application"]["applied_at"] == date.today().isoformat()
    assert calls == [HH_URL]
    sent = client.get("/api/analytics").json()["sent_list"]
    assert [i["title"] for i in sent] == ["Бизнес-ассистент собственника"]


def test_link_not_loaded_falls_back_to_title(setup):
    client, _, _, fetched = setup
    fetched["next"] = httpx.ConnectError("exa down")

    no_title = client.post("/api/applications/manual", json={"url": HH_URL})
    assert no_title.status_code == 400
    assert "укажите название" in no_title.json()["detail"]

    r = client.post(
        "/api/applications/manual",
        json={"url": HH_URL, "title": "Ассистент", "company": "Коттон", "notes": "анкета"},
    ).json()
    assert (r["vacancy_id"], r["fetched"]) == ("hh.ru:138000001", False)  # id всё равно по ссылке
    detail = client.get("/api/vacancies/hh.ru:138000001").json()
    assert detail["url"] == "https://hh.ru/vacancy/138000001"
    assert detail["application"]["notes"] == "анкета"


def test_add_by_title_only(setup):
    client, _, calls, _ = setup
    r = client.post(
        "/api/applications/manual",
        json={"title": "Аналитик", "company": "Ромашка", "applied_at": "2026-10-01"},
    ).json()
    assert r["vacancy_id"].startswith("manual:")
    assert r["application"]["applied_at"] == "2026-10-01"
    assert calls == []  # без ссылки ничего не загружаем
    assert client.get(f"/api/vacancies/{r['vacancy_id']}").json()["url"] == ""

    assert client.post("/api/applications/manual", json={}).status_code == 400


def test_existing_vacancy_is_reused_without_fetch(setup):
    client, engine, calls, _ = setup
    with Session(engine) as s:
        s.add(make_vacancy(1, "Уже найдена поиском", id="hh.ru:138000001", source="hh.ru"))
        s.commit()

    r = client.post("/api/applications/manual", json={"url": HH_URL}).json()

    assert (r["vacancy_id"], r["title"]) == ("hh.ru:138000001", "Уже найдена поиском")
    assert calls == []  # вакансия есть в базе — Exa не нужен


def test_manual_add_forbidden_in_demo(tmp_path, profile):
    app = create_app(
        memory_engine(), tmp_path / "p.json", serve_frontend=False,
        auth=Auth("pw", "s" * 40), demo_engine=memory_engine(),
        demo_profile_path=tmp_path / "demo.json",
    )  # fmt: skip
    r = TestClient(app).post("/api/applications/manual", json={"title": "X"})
    assert r.status_code == 403


def test_fetch_vacancy_via_exa_contents_allows_closed():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        summary = {"is_open_vacancy": False, "title": "Бизнес-ассистент", "company": "Коттон"}
        result = {"url": "https://hh.ru/vacancy/138000001", "text": "Вакансия в архиве",
                  "summary": json.dumps(summary, ensure_ascii=False)}  # fmt: skip
        return httpx.Response(200, json={"results": [result]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    vacancy = fetch_vacancy(HH_URL, client)

    assert vacancy is not None  # закрытая после отклика вакансия всё равно сохраняется
    assert (vacancy.id, vacancy.company) == ("hh.ru:138000001", "Коттон")
    assert requests[0]["urls"] == [HH_URL]
    assert requests[0]["summary"]["schema"]["required"] == ["is_open_vacancy", "title"]
