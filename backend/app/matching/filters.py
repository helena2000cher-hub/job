"""Cheap hard filters: drop what definitely doesn't fit before spending money on LLM calls."""

from app.models import Vacancy
from app.profile import Preferences


def reject_reason(vacancy: Vacancy, prefs: Preferences) -> str | None:
    """Why the vacancy doesn't fit, or None if it passes."""
    if not vacancy.is_remote:
        if prefs.remote_only:
            return "не удалённая"
        if prefs.regions and vacancy.region not in prefs.regions:
            return f"регион: {vacancy.region}"

    # Отсекаем, только если потолок известен и ниже минимума. «от X» и «не указана» оценит LLM.
    if (
        prefs.salary_min
        and vacancy.currency == "RUB"
        and vacancy.salary_to is not None
        and vacancy.salary_to < prefs.salary_min
    ):
        return f"зарплата: до {vacancy.salary_to}"

    haystack = f"{vacancy.title}\n{vacancy.duties or ''}".lower()
    for word in prefs.stop_words:
        if word.lower() in haystack:
            return f"стоп-слово: «{word}»"
    return None
