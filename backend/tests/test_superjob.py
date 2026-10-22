import httpx
import pytest

from app.collectors.base import SearchQuery
from app.collectors.superjob import BASE_URL, SuperJobCollector, parse_vacancy

ITEM = {
    "id": 52008926,
    "profession": "Бизнес-аналитик / системный аналитик",
    "firm_name": "ООО «Пример»",
    "town": {"id": 47, "title": "Пермь"},
    "payment_from": 150000,
    "payment_to": 0,
    "currency": "rub",
    "candidat": "Опыт от 3 лет.<br>BPMN, SQL, <b>User Stories</b>.",
    "work": "Сбор и анализ требований",
    "compensation": "Удалённая работа, ДМС",
    "link": "https://www.superjob.ru/vakansii/biznes-sistemnyj-analitik-52008926.html",
    "date_published": 1791000000,
    "place_of_work": {"id": 2, "title": "На дому"},
    "experience": {"id": 3, "title": "От 3 лет"},
    "type_of_work": {"id": 6, "title": "Полный рабочий день"},
    "catalogues": [{"id": 33, "title": "IT, Интернет, связь, телеком"}],
}
OFFICE = {**ITEM, "id": 2, "profession": "Аналитик в офис", "place_of_work": {"id": 1},
          "compensation": "Офис в центре города", "candidat": "Excel"}  # fmt: skip


def make_collector(pages, requests):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        objects = pages[page] if page < len(pages) else []
        return httpx.Response(200, json={"objects": objects, "more": page + 1 < len(pages)})

    return SuperJobCollector(
        httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    )


def test_parse_vacancy():
    v = parse_vacancy(ITEM)
    assert v.id == "superjob.ru:52008926" and v.source == "superjob.ru"
    assert v.title == "Бизнес-аналитик / системный аналитик"
    assert v.company == "ООО «Пример»" and v.region == "Пермь"
    assert (v.salary_from, v.salary_to, v.currency) == (150000, None, "RUB")  # 0 = не указано
    assert v.requirements == "Опыт от 3 лет. BPMN, SQL, User Stories ."  # HTML вычищен
    assert v.experience_years == 3
    assert v.is_remote is True  # «на дому»
    assert v.url.endswith("-52008926.html")
    assert v.published_at is not None and v.category.startswith("IT")


def test_office_vacancy_not_remote():
    assert parse_vacancy(OFFICE).is_remote is False


def test_fetch_remote_uses_place_of_work_and_paginates():
    requests: list[httpx.Request] = []
    collector = make_collector([[ITEM, OFFICE], [{**ITEM, "id": 3}]], requests)

    found = list(collector.fetch(SearchQuery(text="бизнес-аналитик", remote_only=True, limit=10)))

    assert [v.external_id for v in found] == ["52008926", "3"]  # офисная отброшена
    first = requests[0].url.params
    assert first["keyword"] == "бизнес-аналитик" and first["place_of_work"] == "2"
    assert [r.url.params["page"] for r in requests] == ["0", "1"]  # more=false — дальше не идём


def test_fetch_office_uses_town_and_limit():
    requests: list[httpx.Request] = []
    collector = make_collector([[ITEM, OFFICE]], requests)

    found = list(
        collector.fetch(SearchQuery(text="аналитик", region_code="5900000000000", limit=1))
    )

    assert len(found) == 1
    assert requests[0].url.params["town"] == "Пермь"
    assert "place_of_work" not in requests[0].url.params


def test_requires_api_key(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "superjob_api_key", "")
    with pytest.raises(RuntimeError, match="SUPERJOB_API_KEY"):
        SuperJobCollector()


def test_http_error_raises():
    client = httpx.Client(
        base_url=BASE_URL, transport=httpx.MockTransport(lambda r: httpx.Response(403))
    )
    with pytest.raises(httpx.HTTPStatusError):
        list(SuperJobCollector(client).fetch(SearchQuery(text="x")))
