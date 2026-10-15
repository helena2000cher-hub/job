"""Cover letter for a specific vacancy, written from the profile, resume and match assessment.

The letter has one job: get the candidate invited to an interview. So it sells strengths and
adjacent experience; gaps are left for the interview and never listed.
"""

import re
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
Цель письма — чтобы кандидата пригласили на собеседование. Письмо продаёт сильные стороны.

Правила:
- 120–200 слов, по-русски, без шаблонных фраз
  («прошу рассмотреть мою кандидатуру», «ваша компания — лидер»).
- Первая фраза — сразу по делу: кто кандидат и почему именно эта вакансия.
- 2–3 конкретных факта из опыта кандидата, которые закрывают ключевые требования вакансии.
  Цифры и проекты бери ТОЛЬКО из резюме и раздела «Дополнительно» — ничего не выдумывай.
- НЕ перечисляй, чего у кандидата нет, и не пиши «у меня нет опыта…», «не работала с…».
  Если требование не покрыто — просто не упоминай его, либо покажи близкий опыт в позитивном
  ключе («работала с X — быстро подключусь к Y»). Пробелы обсуждаются на собеседовании.
- Финал — предложение созвониться. Без подписи с контактами (кандидат добавит сам).

Формат: 3–4 коротких абзаца, абзацы разделены пустой строкой. Без markdown, без списков.
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
    if match and match.matched_skills:
        # Только совпадения: список пробелов модель охотно пересказывает в письме
        parts.append(f"СИЛЬНЫЕ СОВПАДЕНИЯ С ВАКАНСИЕЙ\n{', '.join(match.matched_skills)}")
    if wishes.strip():
        parts.append(f"ПОЖЕЛАНИЯ КАНДИДАТА К ПИСЬМУ\n{wishes.strip()}")

    # Быстрая модель: по тесту пишет не хуже дорогой, а стоит в десятки раз меньше
    data = llm.chat_json(SYSTEM_PROMPT, "\n\n".join(parts))
    letter = normalize_text(str(data.get("letter", "")))
    if not letter:
        raise ValueError("Модель вернула пустое письмо")
    return CoverLetter(subject=normalize_text(str(data.get("subject", ""))), letter=letter)


def normalize_text(text: str) -> str:
    """Fix model output: literal "\\n" instead of line breaks, stray spaces, 3+ blank lines."""
    text = text.replace("\\r", "").replace("\\n", "\n").replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
