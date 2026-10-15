import json

import httpx
import pytest

from app.collectors.base import SearchQuery
from app.collectors.exa import HABR, HH, WEB, ExaCollector, parse_result


def summary(**fields) -> str:
    base = {"is_open_vacancy": True, "title": "Бизнес-аналитик", "remote": True}
    return json.dumps(base | fields, ensure_ascii=False)


HH_RESULT = {
    "url": "https://perm.hh.ru/vacancy/137463195?from=search",
    "publishedDate": "2026-09-17T00:00:00.000Z",
    "text": "Бизнес-аналитик. Удалённая работа.",
    "summary": summary(
        company="ЛИАН",
        city="null",
        salary_from=200000,
        salary_to=280000,
        experience="3–6 лет",
        requirements="BPMN, SQL",
        skills=["BPMN", " ", "SQL"],
    ),
}


def test_parse_hh_result():
    v = parse_result(HH_RESULT, HH)

    assert v.id == "hh.ru:137463195"
    assert v.source == "hh.ru"
    assert v.url == "https://hh.ru/vacancy/137463195"  # канонический адрес без поддомена и меток
    assert v.company == "ЛИАН"
    assert v.region is None  # строка "null" от модели — это пусто
    assert (v.salary_from, v.salary_to) == (200000, 280000)
    assert v.requirements == "3–6 лет; BPMN, SQL"
    assert v.skills == ["BPMN", "SQL"]
    assert v.is_remote is True
    assert str(v.published_at) == "2026-09-17"


def test_parse_habr_strips_site_suffix_and_skips_listings():
    result = {
        "url": "https://career.habr.com/vacancies/1000167783",
        "summary": summary(title="GenAI-разработчик, удаленно — Хабр Карьера", salary_from=0),
    }
    v = parse_result(result, HABR)
    assert v.title == "GenAI-разработчик, удаленно"
    assert v.salary_from is None  # 0 = не указана

    listing = {
        "url": "https://career.habr.com/vacancies/biznes_analitik/remote",
        "summary": summary(),
    }
    assert parse_result(listing, HABR) is None


@pytest.mark.parametrize(
    "result",
    [
        {"url": "https://hh.ru/vacancy/1", "summary": summary(is_open_vacancy=False)},  # архив
        {"url": "https://hh.ru/vacancy/1", "summary": "не JSON"},
        {"url": "https://hh.ru/vacancy/1", "summary": summary(title="null")},
        {"url": "https://hh.ru/employer/1", "summary": summary()},  # не вакансия
    ],
)
def test_parse_rejects_unusable_results(result):
    assert parse_result(result, HH) is None


def test_parse_web_result_uses_domain_as_source():
    result = {
        "url": "https://www.example-company.ru/careers/analyst",
        "text": "Работа удаленно",
        "summary": {"is_open_vacancy": True, "title": "Аналитик", "remote": False},
    }
    v = parse_result(result, WEB)
    assert v.source == "example-company.ru"
    assert v.id.startswith("example-company.ru:")
    assert v.is_remote is True  # модель не отметила, но в тексте явно сказано


def make_collector(sites, requests, results):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"results": results, "costDollars": {"total": 0.012}})

    return ExaCollector(sites, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_builds_requests_per_site():
    requests: list[dict] = []
    collector = make_collector(["hh.ru", "web"], requests, [HH_RESULT])

    vacancies = list(collector.fetch(SearchQuery(text="бизнес-аналитик", remote_only=True)))

    assert len(requests) == 2
    hh, web = requests
    assert hh["query"] == "вакансия бизнес-аналитик удаленная работа"
    assert hh["includeDomains"] == ["hh.ru"]
    assert "hh.ru" in web["excludeDomains"] and "includeDomains" not in web
    assert hh["contents"]["summary"]["schema"]["required"] == ["is_open_vacancy", "title"]
    assert "startPublishedDate" in hh
    # результат с hh.ru-адресом в режиме web — страница с домена hh.ru, тоже принимается как web
    assert [v.source for v in vacancies] == ["hh.ru", "perm.hh.ru"]
    assert collector.cost_dollars == pytest.approx(0.024)


def test_fetch_skips_non_remote_when_remote_only():
    office = {"url": "https://hh.ru/vacancy/2", "summary": summary(remote=False)}
    collector = make_collector(["hh.ru"], [], [office, HH_RESULT])

    vacancies = list(collector.fetch(SearchQuery(text="аналитик", remote_only=True)))

    assert [v.external_id for v in vacancies] == ["137463195"]
    assert collector.skipped == 1


def test_fetch_requires_text():
    collector = make_collector(["hh.ru"], [], [])
    with pytest.raises(ValueError):
        list(collector.fetch(SearchQuery()))


def test_parse_skips_archived_even_if_model_says_open():
    result = {
        "url": "https://hh.ru/vacancy/5",
        "text": "Бизнес-аналитик. Вакансия в архиве. Удалённо. " + "x" * 600,
        "summary": summary(),
    }
    assert parse_result(result, HH) is None


def test_remote_trusts_page_text_over_model():
    office_text = "Вакансия «AI инженер» в Москве, офис на Ленинградском. " + "x" * 600
    office = {"url": "https://hh.ru/vacancy/6", "text": office_text, "summary": summary()}
    assert parse_result(office, HH).is_remote is False

    short = {"url": "https://hh.ru/vacancy/7", "text": "AI инженер", "summary": summary()}
    assert parse_result(short, HH).is_remote is True  # текста почти нет — верим модели

    habr = {
        "url": "https://career.habr.com/vacancies/8",
        "text": "Можно удаленно. " + "x" * 600,
        "summary": summary(remote=False),
    }
    assert parse_result(habr, HABR).is_remote is True


def test_title_prefix_removed():
    result = {"url": "https://hh.ru/vacancy/9", "summary": summary(title="Вакансия «Аналитик BI»")}
    assert parse_result(result, HH).title == "Аналитик BI"


def test_currency_from_summary():
    result = {
        "url": "https://hh.ru/vacancy/10",
        "summary": summary(salary_from=1500000, currency="kzt"),
    }
    assert parse_result(result, HH).currency == "KZT"
    assert parse_result(HH_RESULT, HH).currency == "RUB"  # по умолчанию
