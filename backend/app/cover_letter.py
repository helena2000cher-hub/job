"""Cover letter for a specific vacancy, written from the profile, resume and match assessment."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.llm import LLM
from app.matching.scorer import vacancy_card
from app.models import Match, Vacancy
from app.profile import RESUME_PATH, Profile, read_resume, redact_pii

MAX_RESUME_CHARS = 6000

Tone = Literal["business", "friendly"]

TONES: dict[str, str] = {
    "business": "деловой, сдержанный, без канцелярита",
    "friendly": "живой и дружелюбный, но профессиональный (как пишут в IT-стартапы)",
}

SYSTEM_PROMPT = """Ты пишешь сопроводительные письма к откликам на вакансии.
Правила:
- 120–200 слов, по-русски, без шаблонных фраз
  («прошу рассмотреть мою кандидатуру», «ваша компания — лидер»).
- Первая фраза — сразу по делу: кто кандидат и почему именно эта вакансия.
- 2–3 конкретных факта из опыта кандидата, которые закрывают ключевые требования вакансии
  (цифры и проекты бери ТОЛЬКО из резюме, ничего не выдумывай).
- Если каких-то требований у кандидата нет — не скрывай и не ври: коротко покажи близкий опыт
  или готовность быстро освоить.
- Финал — предложение созвониться. Без подписи с контактами (кандидат добавит сам).
Верни ТОЛЬКО JSON: {"subject": "тема письма", "letter": "текст письма"}"""


@dataclass
class CoverLetter:
    subject: str
    letter: str


def generate_cover_letter(
    profile: Profile,
    vacancy: Vacancy,
    match: Match | None,
    llm: LLM,
    *,
    tone: Tone = "business",
    wishes: str = "",
    resume_path: Path = RESUME_PATH,
) -> CoverLetter:
    resume = ""
    if resume_path.exists():
        resume = redact_pii(read_resume(resume_path))[:MAX_RESUME_CHARS]

    parts = [
        f"ТОН: {TONES[tone]}",
        f"КАНДИДАТ\n{profile.headline}\n{profile.matching_text()}",
    ]
    if resume:
        parts.append(f"РЕЗЮМЕ (источник фактов)\n{resume}")
    parts.append(f"ВАКАНСИЯ\n{vacancy_card(vacancy)}")
    if match:
        parts.append(
            "ОЦЕНКА СОВПАДЕНИЯ\n"
            f"Совпало: {', '.join(match.matched_skills) or '—'}\n"
            f"Не хватает: {', '.join(match.missing_skills) or '—'}"
        )
    if wishes.strip():
        parts.append(f"ПОЖЕЛАНИЯ КАНДИДАТА К ПИСЬМУ\n{wishes.strip()}")

    data = llm.chat_json(SYSTEM_PROMPT, "\n\n".join(parts), smart=True)
    letter = str(data.get("letter", "")).strip()
    if not letter:
        raise ValueError("Модель вернула пустое письмо")
    return CoverLetter(subject=str(data.get("subject", "")).strip(), letter=letter)
