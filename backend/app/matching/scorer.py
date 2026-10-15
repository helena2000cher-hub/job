"""LLM assessment of a single vacancy against the profile: score + explanation."""

from typing import Any

from app.llm import LLM
from app.models import Vacancy
from app.profile import Profile

MAX_VACANCY_CHARS = 3500

SYSTEM_PROMPT = """Ты — карьерный консультант. Оцени, насколько вакансия подходит кандидату.
Учитывай: совпадение роли и навыков, уровень опыта, формат работы, зарплату относительно ожиданий.
Шкала score (0–100):
  90–100 — почти идеально, стоит откликаться сразу
  70–89  — хорошо подходит, есть небольшие пробелы
  50–69  — частично подходит (другая роль или заметные пробелы)
  0–49   — не подходит
Верни ТОЛЬКО JSON:
{"score": число,
 "matched_skills": [навыки кандидата, которые нужны в вакансии],
 "missing_skills": [требования вакансии, которых нет у кандидата],
 "red_flags": [настораживающее: низкая зарплата, на деле продажи/колл-центр, размытое описание…],
 "verdict": "1–2 предложения: почему подходит или нет"}
Пиши кратко, на русском."""


def vacancy_card(v: Vacancy) -> str:
    salary = (
        f"{v.salary_from or '?'}–{v.salary_to or '?'} {v.currency}"
        if v.salary_from or v.salary_to
        else "не указана"
    )
    lines = [
        f"Должность: {v.title}",
        f"Компания: {v.company or '?'}",
        f"Регион: {v.region or '?'}; удалённо: {'да' if v.is_remote else 'нет'}",
        f"Зарплата: {salary}",
        f"Занятость: {v.employment or '?'}; график: {v.schedule or '?'}",
        f"Опыт: {v.experience_years if v.experience_years is not None else '?'} лет",
        f"Требования: {v.requirements or '—'}",
        f"Обязанности: {v.duties or '—'}",
        f"Условия: {v.conditions or '—'}",
    ]
    if v.skills:
        lines.append(f"Навыки: {', '.join(v.skills)}")
    return "\n".join(lines)[:MAX_VACANCY_CHARS]


def score_vacancy(profile: Profile, vacancy: Vacancy, llm: LLM) -> dict[str, Any]:
    prefs = profile.preferences
    user = (
        f"КАНДИДАТ\n{profile.matching_text()}\n"
        f"Ожидания: зарплата от {prefs.salary_min or '?'} ₽, "
        f"{'только удалённо' if prefs.remote_only else 'удалённо или офис'}\n\n"
        f"ВАКАНСИЯ\n{vacancy_card(vacancy)}"
    )
    data = llm.chat_json(SYSTEM_PROMPT, user)
    return {
        "score": max(0, min(100, int(data.get("score", 0)))),
        "matched_skills": _str_list(data.get("matched_skills")),
        "missing_skills": _str_list(data.get("missing_skills")),
        "red_flags": _str_list(data.get("red_flags")),
        "verdict": str(data.get("verdict", "")).strip(),
    }


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]
