import json
from pathlib import Path

import httpx
import pytest

from app.collectors.base import SearchQuery
from app.collectors.trudvsem import BASE_URL, TrudvsemCollector, parse_vacancy

PAGE = json.loads((Path(__file__).parent / "fixtures" / "trudvsem_page.json").read_text("utf-8"))
EMPTY = {"status": "200", "meta": {"total": 0}, "results": {}}


def make_collector(pages: list[dict], requests: list[httpx.Request]) -> TrudvsemCollector:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["offset"])
        return httpx.Response(200, json=pages[page] if page < len(pages) else EMPTY)

    client = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return TrudvsemCollector(client)


def test_parse_vacancy_normalizes_fields():
    v = parse_vacancy(PAGE["results"]["vacancies"][0]["vacancy"])

    assert v.id == "trudvsem:00000000-0000-0000-0000-000000000001"
    assert v.title == "Ведущий аналитик"
    assert v.company == 'ООО "Пример"'
    assert v.region == "Пермский край"
    assert v.address == "г Пермь, ул. Примерная, 1"
    assert (v.salary_from, v.salary_to) == (35000, None)  # «от 35000», а не 35000–35000
    assert v.requirements == "Высшее образование; уверенный MS Excel , 1С"  # HTML вычищен
    assert v.experience_years == 3
    assert str(v.published_at) == "2026-03-06"
    assert v.source_updated_at is not None
    assert v.is_remote is False


def test_parse_vacancy_remote_and_skills():
    v = parse_vacancy(PAGE["results"]["vacancies"][1]["vacancy"])

    assert v.is_remote is True
    assert (v.salary_from, v.salary_to) == (40000, 60000)
    assert v.skills == ["CRM", "Деловая переписка"]


def test_fetch_uses_region_path_and_skips_malformed():
    requests: list[httpx.Request] = []
    collector = make_collector([PAGE], requests)

    vacancies = list(collector.fetch(SearchQuery(text="аналитик", region_code="5900000000000")))

    assert len(vacancies) == 2  # третья запись без обязательных полей пропущена
    assert requests[0].url.path == "/api/v1/vacancies/region/5900000000000"
    assert requests[0].url.params["text"] == "аналитик"
    assert len(requests) == 1  # страница неполная — дальше не идём


def test_fetch_remote_only_and_limit():
    requests: list[httpx.Request] = []
    collector = make_collector([PAGE], requests)

    remote = list(collector.fetch(SearchQuery(text="оператор", remote_only=True)))
    assert [v.external_id[-1] for v in remote] == ["2"]  # без дублей из двух запросов
    assert requests[0].url.path == "/api/v1/vacancies"
    assert [r.url.params["text"] for r in requests] == [
        "оператор удаленная",
        "оператор дистанционная",
    ]

    assert len(list(collector.fetch(SearchQuery(limit=1)))) == 1


def test_fetch_paginates_until_empty():
    template = PAGE["results"]["vacancies"][0]["vacancy"]

    def page(n: int) -> dict:
        items = [{"vacancy": {**template, "id": f"{n}-{i}"}} for i in range(100)]
        return {"results": {"vacancies": items}}

    requests: list[httpx.Request] = []
    collector = make_collector([page(0), page(1)], requests)

    vacancies = list(collector.fetch(SearchQuery(limit=1000)))

    assert len(vacancies) == 200
    assert [r.url.params["offset"] for r in requests] == ["0", "1", "2"]


def test_fetch_raises_on_http_error():
    client = httpx.Client(
        base_url=BASE_URL, transport=httpx.MockTransport(lambda r: httpx.Response(503))
    )
    with pytest.raises(httpx.HTTPStatusError):
        list(TrudvsemCollector(client).fetch(SearchQuery()))
