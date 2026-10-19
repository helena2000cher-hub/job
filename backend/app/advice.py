"""AI advice on the resume and cover letters, based on response statistics and frequent gaps."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.llm import LLM
from app.models import utcnow
from app.profile import Profile

MIN_SENT_FOR_STATS = 5  # меньше — статистика ещё ничего не говорит, советуем по пробелам

SYSTEM_PROMPT = """Ты — карьерный консультант. Кандидат ищет работу и откликается на вакансии.
По статистике откликов и частым пробелам дай конкретные советы, как получать больше приглашений
на собеседование.

Правила:
- Только практичные шаги, которые можно сделать за день-неделю: что добавить или переформулировать
  в резюме, как менять сопроводительные письма, на какие вакансии откликаться чаще.
- Опирайся на цифры. Если откликов мало — прямо скажи, что выводы предварительные, и сделай акцент
  на пробелах в навыках и на количестве откликов.
- Не выдумывай опыт: советуй, как подать имеющийся, и что стоит подтянуть.
- По 2–4 совета в каждом разделе, каждый — 1–2 предложения.
Верни ТОЛЬКО JSON:
{"summary": "главный вывод в 1–2 предложениях",
 "resume": ["совет по резюме", ...],
 "letters": ["совет по сопроводительным письмам", ...],
 "search": ["совет по выбору вакансий и количеству откликов", ...]}"""


class Advice(BaseModel):
    summary: str = ""
    resume: list[str] = Field(default_factory=list)
    letters: list[str] = Field(default_factory=list)
    search: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)
    based_on_sent: int = 0


def generate_advice(profile: Profile, stats: dict[str, Any], llm: LLM) -> Advice:
    sent = stats["sent"]
    lines = [
        f"ПРОФИЛЬ КАНДИДАТА\n{profile.headline}\n{profile.matching_text()}",
        "СТАТИСТИКА ОТКЛИКОВ",
        f"Отправлено: {sent}, приглашений (собеседование/оффер): {stats['positive']}, "
        f"отказов: {stats['rejected']}, без ответа {stats['no_response_days']}+ дней: "
        f"{stats['no_response']}, ждут ответа: {stats['waiting']}",
    ]
    if sent < MIN_SENT_FOR_STATS:
        lines.append(f"Откликов пока меньше {MIN_SENT_FOR_STATS} — статистика предварительная.")
    for title, key in [
        ("По письмам", "by_letter"),
        ("По баллу совпадения", "by_score"),
        ("По сайтам", "by_source"),
    ]:
        if stats[key]:
            parts = [f"{r['label']}: {r['positive']} из {r['sent']}" for r in stats[key]]
            lines.append(f"{title}: " + "; ".join(parts))
    if stats["top_gaps"]:
        gaps = ", ".join(f"{g['skill']} ({g['count']})" for g in stats["top_gaps"])
        lines.append(f"ЧАСТЫЕ ПРОБЕЛЫ в подходящих вакансиях (сколько раз встречается): {gaps}")

    data = llm.chat_json(SYSTEM_PROMPT, "\n".join(lines))
    return Advice(
        summary=str(data.get("summary", "")).strip(),
        resume=_items(data.get("resume")),
        letters=_items(data.get("letters")),
        search=_items(data.get("search")),
        based_on_sent=sent,
    )


def _items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()][:5]


def load_advice(path: Path) -> Advice | None:
    if not path.exists():
        return None
    return Advice.model_validate_json(path.read_text(encoding="utf-8"))


def save_advice(advice: Advice, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(advice.model_dump(mode="json"), ensure_ascii=False, indent=2), "utf-8"
    )
