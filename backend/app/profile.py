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

from pydantic import BaseModel, Field

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
    headline: str
    target_roles: list[str]
    skills: list[str]
    experience_years: float | None = None
    seniority: str | None = None
    industries: list[str] = Field(default_factory=list)
    education: str | None = None
    summary: str = ""
    extra: str = Field(default="", description="что умею, но нет в резюме — пишется вручную")
    search_queries: list[str] = Field(default_factory=list, description="запросы для сбора")
    preferences: Preferences = Field(default_factory=Preferences)

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

    def fingerprint(self) -> str:
        """Changes whenever the profile changes — cached match scores are then recomputed."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]


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
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8")


def build_profile(resume_text: str, llm: LLM) -> Profile:
    data = llm.chat_json(SYSTEM_PROMPT, redact_pii(resume_text), smart=True)
    prefs = {k: v for k, v in (data.pop("preferences", None) or {}).items() if v not in (None, [])}
    return Profile(**data, preferences=Preferences(**prefs))


def load_profile(path: Path = PROFILE_PATH) -> Profile:
    if not path.exists():
        raise FileNotFoundError(
            f"Профиль не найден: {path}. Сначала запустите: python -m app.profile"
        )
    return Profile.model_validate_json(path.read_text(encoding="utf-8"))


def save_profile(profile: Profile, path: Path = PROFILE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2), "utf-8")


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

    profile = build_profile(read_resume(args.resume), PolzaLLM())
    if PROFILE_PATH.exists() and not args.reset_preferences:
        old = load_profile()
        profile.preferences, profile.extra = old.preferences, old.extra
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
