"""Candidate profile: built from the resume by an LLM, then hand-editable in data/profile.json.

python -m app.profile                       # data/resume.pdf → data/profile.json
python -m app.profile --resume other.pdf --reset-preferences
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.careers import CareerSuggestions
from app.config import DATA_DIR
from app.llm import LLM, PolzaLLM

PROFILE_PATH = DATA_DIR / "profile.json"
RESUME_PATH = DATA_DIR / "resume.pdf"

DEFAULT_STOP_WORDS = ["склад", "кладовщик", "грузчик", "комплектовщик", "курьер", "холодные звонки"]


class Preferences(BaseModel):
    remote_only: bool = True
    regions: list[str] = Field(default_factory=list, description="регионы, где подходит офис")
    salary_min: int | None = None
    employment_types: list[str] = Field(default_factory=list)
    stop_words: list[str] = Field(default_factory=lambda: list(DEFAULT_STOP_WORDS))


class Profile(BaseModel):
    name: str = Field(default="", description="имя для шапки сайта; в нейросеть не передаётся")
    headline: str
    target_roles: list[str]
    skills: list[str]
    experience_years: float | None = None
    seniority: str | None = None
    industries: list[str] = Field(default_factory=list)
    education: str | None = None
    summary: str = ""
    extra: str = Field(default="", description="что умею, но нет в резюме — пишется вручную")
    stories: str = Field(
        default="", description="истории и достижения для сопроводительных писем (факты, цифры)"
    )
    full_name: str = Field(default="", description="подпись письма; в нейросеть не передаётся")
    contacts: str = Field(default="", description="контакты в подписи; в нейросеть не передаются")
    search_queries: list[str] = Field(default_factory=list, description="запросы для сбора")
    # Что ищем: по названиям выбранных профессий, по навыкам или по тому и другому
    search_mode: Literal["professions", "skills", "both"] = "professions"
    search_skills: list[str] = Field(default_factory=list, description="навыки для поиска")
    preferences: Preferences = Field(default_factory=Preferences)
    careers: CareerSuggestions | None = Field(
        default=None, description="профессии, подобранные по навыкам"
    )

    def matching_text(self) -> str:
        """Compact description used for embeddings and as LLM context."""
        lines = [
            f"Целевые роли: {', '.join(self.target_roles)}",
            f"Навыки: {', '.join(self.skills)}",
            f"Опыт: {self.experience_years or '?'} лет, уровень: {self.seniority or '?'}",
            f"Отрасли: {', '.join(self.industries)}",
            f"О себе: {self.summary}",
        ]
        if self.extra.strip():
            lines.append(f"Дополнительно (нет в резюме): {self.extra.strip()}")
        return "\n".join(lines)

    def query_plan(self) -> list[tuple[str, list[str]]]:
        """What the search looks for: each selected profession with its queries.

        Queries come from the profession's card in «Кем я могу работать»; a profession without a
        card (added by hand or left from the resume) is searched by its own title.
        """
        cards = {_norm(o.title): o for o in (self.careers.options if self.careers else [])}
        plan = []
        for role in self.target_roles:
            card = cards.get(_norm(role))
            plan.append((role, list(card.queries) if card and card.queries else [role]))
        return plan

    def effective_queries(self) -> list[str]:
        """Search queries by the chosen mode: professions' queries, skills, or both (no duplicates).

        Сайты вакансий ищут по всему тексту, поэтому запрос «n8n» находит и вакансии
        с неожиданными названиями, которые поиск по профессиям пропускает.
        """
        candidates: list[str] = []
        if self.search_mode in ("professions", "both"):
            candidates += [q for _, qs in self.query_plan() for q in qs]
        if self.search_mode in ("skills", "both"):
            candidates += self.search_skills
        queries: list[str] = []
        for q in candidates:
            if q.strip() and not any(_norm(q) == _norm(x) for x in queries):
                queries.append(q.strip())
        return queries or list(self.search_queries)  # ничего не выбрано — старый список

    def fingerprint(self) -> str:
        """Changes whenever the profile changes — cached match scores are then recomputed."""
        # Влияет только то, по чему вакансию ОЦЕНИВАЮТ. Имя, подпись, истории для писем,
        # подсказки профессий и настройки ПОИСКА (что собирать) оценку не меняют —
        # их правка не должна сбрасывать оценки.
        data = self.model_dump_json(
            exclude={
                "name", "full_name", "contacts", "stories", "careers",
                "search_queries", "search_mode", "search_skills",
            }
        )  # fmt: skip
        return hashlib.sha256(data.encode()).hexdigest()[:16]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


SYSTEM_PROMPT = """Ты — опытный IT-рекрутер.
Из текста резюме составь профиль кандидата для подбора вакансий.
Верни ТОЛЬКО JSON-объект с полями:
- headline: строка — желаемая должность одной фразой
- target_roles: массив 3–7 названий ролей, на которые кандидат реально может претендовать
- skills: массив 15–40 конкретных навыков и инструментов (жёсткие навыки важнее мягких)
- experience_years: число — релевантный опыт в годах
- seniority: "junior" | "middle" | "senior"
- industries: массив отраслей, где есть опыт
- education: строка
- summary: 2–3 предложения о сильных сторонах кандидата
- search_queries: массив 5–10 коротких поисковых запросов (1–3 слова) для сайтов вакансий
- preferences: объект {remote_only: bool, regions: [строки], salary_min: число или null,
  employment_types: [строки]} — только если это явно указано в резюме
Пиши на русском. Не выдумывай то, чего нет в резюме."""


_PII_PATTERNS = [
    re.compile(r"\+?\d[\d\s\-()]{8,}\d"),  # телефоны
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),  # email
    re.compile(r"родил(?:ся|ась)\s+\d{1,2}\s+\w+\s+\d{4}", re.IGNORECASE),
]


def redact_pii(text: str) -> str:
    """Strip contacts and birth date — the model doesn't need them to match vacancies."""
    for pattern in _PII_PATTERNS:
        text = pattern.sub("[скрыто]", text)
    return text


def read_resume(path: Path) -> str:
    from app.resume import extract_text  # PDF, Word, ODT, RTF, TXT

    return extract_text(path.read_bytes(), path.name)


def build_profile(resume_text: str, llm: LLM) -> Profile:
    data = llm.chat_json(SYSTEM_PROMPT, redact_pii(resume_text), smart=True)
    prefs = {k: v for k, v in (data.pop("preferences", None) or {}).items() if v not in (None, [])}
    return Profile(**data, preferences=Preferences(**prefs))


def rebuild_profile(resume_text: str, old: Profile | None, llm: LLM) -> Profile:
    """New profile from a resume that keeps everything the user did by hand.

    Навыки из резюме добавляются к уже имеющимся (вписанные вручную не пропадают),
    выбранные профессии и настройки поиска остаются, если в профиле уже есть подбор профессий.
    """
    profile = build_profile(resume_text, llm)
    if old is None:
        return profile
    profile.skills = _merge(profile.skills, old.skills)
    profile.preferences, profile.extra, profile.name = old.preferences, old.extra, old.name
    profile.careers = old.careers
    profile.stories, profile.full_name, profile.contacts = old.stories, old.full_name, old.contacts
    if old.careers is not None:  # профессии уже выбраны по навыкам — резюме их не перебивает
        profile.target_roles = old.target_roles
        profile.search_mode, profile.search_skills = old.search_mode, old.search_skills
    profile.search_queries = profile.effective_queries()
    return profile


def _merge(first: list[str], second: list[str]) -> list[str]:
    result = list(first)
    for item in second:
        if not any(_norm(item) == _norm(x) for x in result):
            result.append(item)
    return result


def load_profile(path: Path = PROFILE_PATH) -> Profile:
    if not path.exists():
        raise FileNotFoundError(
            f"Профиль не найден: {path}. Сначала запустите: python -m app.profile"
        )
    return Profile.model_validate_json(path.read_text(encoding="utf-8"))


def save_profile(profile: Profile, path: Path = PROFILE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2), "utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Построить профиль кандидата из резюме")
    parser.add_argument("--resume", type=Path, default=RESUME_PATH)
    parser.add_argument(
        "--reset-preferences",
        action="store_true",
        help="перезаписать предпочтения (по умолчанию сохраняются отредактированные вручную)",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    old = load_profile() if PROFILE_PATH.exists() and not args.reset_preferences else None
    profile = rebuild_profile(read_resume(args.resume), old, PolzaLLM())
    save_profile(profile)

    print(f"Профиль сохранён: {PROFILE_PATH}")
    print(f"  {profile.headline}")
    print(f"  Роли: {', '.join(profile.target_roles)}")
    print(f"  Навыки ({len(profile.skills)}): {', '.join(profile.skills)}")
    print(f"  Запросы для поиска: {', '.join(profile.search_queries)}")
    print(f"  Предпочтения: {profile.preferences.model_dump()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
