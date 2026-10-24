"""Cover letter for a specific vacancy, built on the structure of a letter that worked.

Structure: positioning + bridge to the vacancy → «Что уже сделано на практике» (3–4 projects, each
tied to the vacancy) → optionally «Честно о пробелах» (each gap paired with a strength) → call to
action → signature. Facts come only from the resume, «что ещё умею» and «истории для писем».

Privacy: the name, full name and contacts never reach the model. The model writes a {NAME}
placeholder; the code substitutes the name and appends the signature.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.llm import LLM
from app.matching.scorer import vacancy_card
from app.models import Match, Vacancy
from app.profile import RESUME_PATH, Profile, redact_pii
from app.resume import ResumeStore

MAX_RESUME_CHARS = 6000
NAME_PLACEHOLDER = "{NAME}"

Tone = Literal["business", "friendly"]

TONES: dict[str, str] = {
    "business": "деловой, сдержанный, без канцелярита",
    "friendly": "живой и дружелюбный, но профессиональный (как пишут в IT-стартапы)",
}

SYSTEM_PROMPT = """Ты пишешь сопроводительные письма к откликам.
Цель — приглашение на собеседование.
Пиши от первого лица, в роде кандидата (по резюме), по-русски, без шаблонных фраз
(«прошу рассмотреть мою кандидатуру», «ваша компания — лидер рынка»).

Структура письма (обычный текст, без markdown; пункты — с символа «• »):

1. «Здравствуйте!»
2. Абзац-позиционирование: «Меня зовут {NAME}.» — ровно так, с заполнителем {NAME}. Затем одной
   фразой, кто кандидат по сути (роль, которая подходит ИМЕННО этой вакансии), коротко — какой опыт
   был до этого. Затем мост: чем эта вакансия совпадает с опытом кандидата — назови конкретные
   задачи вакансии.
3. «Что уже сделано на практике:» и 3–4 пункта. Каждый пункт: название проекта или места работы —
   что конкретно сделано (цифры, технологии, результат) — и ЯВНАЯ связка с вакансией
   («Это тот же принцип, что у вас: …», «Для вашей задачи … этот опыт пригодится напрямую»).
   Если в «историях» есть случай, показывающий, КАК кандидат работает (нашёл ошибку, проверил факты,
   улучшил процесс), — сделай из него отдельный пункт и свяжи с задачами вакансии.
4. {GAPS}
5. Призыв к действию: готовность к тестовому заданию и предложение показать проекты на созвоне.
6. Ничего после этого: без подписи, имени и контактов — их добавят автоматически.

Правила по фактам: проекты, цифры, технологии и истории бери ТОЛЬКО из резюме, «что ещё умеет» и
«истории для писем». Ничего не выдумывай и не преувеличивай. Название вакансии и компании можно
упоминать. Объём — 220–330 слов.

Верни ТОЛЬКО JSON: {"subject": "тема письма", "letter": "текст письма"}"""

GAPS_ON = """«Честно о пробелах:» — 1–3 главных требования вакансии, которых нет у кандидата,
   одним-двумя предложениями. К КАЖДОМУ пробелу сразу приложи сильную сторону,
   которая его компенсирует,
   или как кандидат его закроет («…пока не работала. Привычная мне задача — разобраться в чужом
   API и проверить, что данные сходятся»). Тон спокойный и уверенный, без извинений."""
GAPS_OFF = """Пробелы не упоминай вовсе. Если требование не покрыто — просто не пиши о нём."""


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
    mention_gaps: bool = True,
    resume_path: Path = RESUME_PATH,
) -> CoverLetter:
    resume = redact_pii(ResumeStore(resume_path).text())[:MAX_RESUME_CHARS]

    parts = [f"ТОН: {TONES[tone]}", f"КАНДИДАТ\n{profile.headline}\n{profile.matching_text()}"]
    gender = detect_gender(resume)
    if gender:
        # иначе модель согласует с профессией: «я разработчик, который…» вместо «которая»
        parts.insert(1, f"ПОЛ КАНДИДАТА: {gender} — согласуй все слова о себе в этом роде")
    if profile.stories.strip():
        parts.append(f"ИСТОРИИ И ДОСТИЖЕНИЯ ДЛЯ ПИСЕМ (источник фактов)\n{profile.stories.strip()}")
    if resume:
        parts.append(f"РЕЗЮМЕ (источник фактов)\n{resume}")
    parts.append(f"ВАКАНСИЯ\n{vacancy_card(vacancy)}")
    if match and match.matched_skills:
        parts.append(f"СИЛЬНЫЕ СОВПАДЕНИЯ С ВАКАНСИЕЙ\n{', '.join(match.matched_skills)}")
    if mention_gaps and match and match.missing_skills:
        parts.append(f"ЧЕГО НЕ ХВАТАЕТ ПО ОЦЕНКЕ\n{', '.join(match.missing_skills)}")
    if wishes.strip():
        parts.append(f"ПОЖЕЛАНИЯ КАНДИДАТА К ПИСЬМУ\n{wishes.strip()}")

    system = SYSTEM_PROMPT.replace("{GAPS}", GAPS_ON if mention_gaps else GAPS_OFF)
    data = llm.chat_json(system, "\n\n".join(parts))  # быстрая модель: качество проверено
    letter = normalize_text(str(data.get("letter", "")))
    if not letter:
        raise ValueError("Модель вернула пустое письмо")
    letter = _insert_name(letter, profile.name)
    signature = "\n".join(x for x in (profile.full_name.strip(), profile.contacts.strip()) if x)
    if signature:
        letter = f"{letter}\n\n{signature}"
    return CoverLetter(subject=normalize_text(str(data.get("subject", ""))), letter=letter)


def _insert_name(letter: str, name: str) -> str:
    name = name.strip()
    if name:
        return letter.replace(NAME_PLACEHOLDER, name)
    # имени в профиле нет — убираем фразу «Меня зовут {NAME}.» целиком
    letter = re.sub(r"Меня зовут \{NAME\}[.,]?\s*", "", letter)
    return letter.replace(NAME_PLACEHOLDER, "").strip()


def normalize_text(text: str) -> str:
    """Fix model output: literal "\\n", markdown bullets, stray spaces, 3+ blank lines."""
    text = text.replace("\\r", "").replace("\\n", "\n").replace("\r", "")
    text = re.sub(r"^[ \t]*[*\-–][ \t]+", "• ", text, flags=re.MULTILINE)  # «* » и «- » → «• »
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # без markdown-жирного
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_gender(resume: str) -> str | None:
    """hh.ru пишет пол в шапке резюме: «Женщина, 41 год» / «Мужчина, …»."""
    head = resume[:400].lower()
    if re.search(r"\bженщина\b", head):
        return "женский (например: «которая», «сделала», «готова»)"
    if re.search(r"\bмужчина\b", head):
        return "мужской (например: «который», «сделал», «готов»)"
    return None
