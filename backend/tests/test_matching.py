import pytest

from app.llm import extract_json
from app.matching.embeddings import cosine
from app.matching.filters import reject_reason
from app.matching.pipeline import run_matching
from app.matching.scorer import score_vacancy
from app.models import Match
from app.profile import Preferences
from tests.conftest import FakeLLM, make_vacancy


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"is_remote": True}, None),
        ({"is_remote": False, "region": "Пермский край"}, "не удалённая"),
        ({"salary_from": 30_000, "salary_to": 50_000}, "зарплата: до 50000"),
        ({"salary_from": 30_000}, None),  # «от 30 000» без потолка — пусть решает LLM
        ({"title": "Кладовщик на склад"}, "стоп-слово: «склад»"),
    ],
)
def test_reject_reason(kwargs, expected):
    prefs = Preferences(remote_only=True, salary_min=100_000)
    assert (
        reject_reason(make_vacancy(1, kwargs.pop("title", "Аналитик"), **kwargs), prefs) == expected
    )


def test_reject_reason_office_in_allowed_region():
    prefs = Preferences(remote_only=False, regions=["Пермский край"])
    perm = make_vacancy(1, "Аналитик", is_remote=False, region="Пермский край")
    moscow = make_vacancy(2, "Аналитик", is_remote=False, region="Москва")
    assert reject_reason(perm, prefs) is None
    assert reject_reason(moscow, prefs) == "регион: Москва"


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0)
    assert cosine([0, 0], [1, 1]) == 0


def test_extract_json_tolerates_fences_and_text():
    assert extract_json('Вот ответ:\n```json\n{"score": 80}\n```') == {"score": 80}
    assert extract_json('{"a": [1, 2]} — готово') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("не JSON")


def test_score_vacancy_normalizes_llm_answer(profile):
    llm = FakeLLM([{"score": 140, "matched_skills": ["BPMN", ""], "red_flags": "не список"}])
    result = score_vacancy(profile, make_vacancy(1, "Аналитик"), llm)
    assert result == {
        "score": 100,
        "matched_skills": ["BPMN"],
        "missing_skills": [],
        "red_flags": [],
        "verdict": "",
    }
    assert llm.chat_calls[0][2] is False  # массовая оценка — быстрая модель


def test_pipeline_filters_ranks_and_caches(session, profile):
    session.add_all(
        [
            make_vacancy(1, "Бизнес-аналитик"),
            make_vacancy(2, "Оператор чата"),
            make_vacancy(3, "Аналитик в офисе", is_remote=False),
            make_vacancy(4, "Кладовщик склад"),
        ]
    )
    session.commit()
    llm = FakeLLM()

    report = run_matching(session, profile, llm, top_n=10)

    assert report.total == 4
    assert report.rejected == {"не удалённая": 1, "стоп-слово": 1}
    assert report.scored == 2
    assert [v.title for v, _ in report.results] == ["Бизнес-аналитик", "Оператор чата"]
    assert session.get(Match, "test:1").score == 85

    # повторный запуск: ни новых эмбеддингов вакансий, ни новых LLM-оценок
    llm2 = FakeLLM()
    again = run_matching(session, profile, llm2, top_n=10)
    assert (again.scored, again.reused) == (0, 2)
    assert llm2.chat_calls == []
    assert llm2.embed_calls == [[profile.matching_text()]]

    # профиль изменился — оценки устарели и пересчитываются
    profile.skills.append("SQL")
    assert run_matching(session, profile, FakeLLM(), top_n=10).scored == 2


def test_pipeline_top_n_and_failures(session, profile):
    session.add_all([make_vacancy(i, f"Аналитик {i}") for i in range(5)])
    session.commit()

    class Flaky(FakeLLM):
        def chat_json(self, system, user, *, smart=False):
            if "Аналитик 0" in user:
                raise RuntimeError("timeout")
            return super().chat_json(system, user, smart=smart)

    report = run_matching(session, profile, Flaky(), top_n=3)
    assert report.scored + report.failed == 3
    assert len(report.results) == report.scored


def test_pipeline_scores_duplicates_once(session, profile):
    session.add_all(
        [
            make_vacancy(1, "Редактор текстов", company="Сбер", region="Москва"),
            make_vacancy(2, "Редактор  ТЕКСТОВ", company="Сбер", region="Пермский край"),
            make_vacancy(3, "Редактор текстов", company="Другая компания"),
        ]
    )
    session.commit()
    llm = FakeLLM()

    report = run_matching(session, profile, llm, top_n=10)

    assert report.duplicates == 1
    assert report.scored == 2
    assert len(llm.chat_calls) == 2
