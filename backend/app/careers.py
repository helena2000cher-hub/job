"""Skills → professions: which jobs the candidate's skills fit, including other fields.

Same idea as LinkedIn Career Explorer: a profession fits when its key skills overlap with the
candidate's; we show what transfers and what to build. The past job title is deliberately not
sent, so suggestions come from skills, not from the old role.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm import LLM
from app.models import utcnow

Kind = Literal["core", "adjacent", "new_field"]

SYSTEM_PROMPT = """Ты — карьерный консультант по российскому рынку труда.
По НАВЫКАМ кандидата (не по прошлой должности) подбери профессии, где эти навыки ценятся.

Нужно 10–12 профессий трёх видов:
- "core" (3–4): навыки кандидата — ядро профессии, можно откликаться сразу;
- "adjacent" (3–4): смежные роли — большая часть навыков переносится, чего-то немного не хватает;
- "new_field" (3–4): другие сферы (маркетинг, продажи, финансы, образование, производство и т.п.),
  где эти навыки неожиданно ценны.

Для каждой профессии:
- title — название, как пишут в вакансиях на hh.ru;
- field — сфера (2–3 слова);
- fit — 0–100: какая доля КЛЮЧЕВЫХ навыков профессии уже есть у кандидата
  (учитывай важность навыков);
- why — одно предложение, почему подходит;
- transferable — 3–6 навыков кандидата, которые здесь пригодятся (бери из списка кандидата);
- gaps — 0–4 главных навыка, которых не хватает (1–4 слова каждый);
- queries — 2–3 коротких поисковых запроса для сайтов вакансий (1–3 слова).

Не выдумывай навыки кандидата. Не повторяй одну профессию под разными названиями.
Верни ТОЛЬКО JSON: {"options": [{"title": ..., "field": ..., "kind": ..., "fit": ..., "why": ...,
"transferable": [...], "gaps": [...], "queries": [...]}, ...]}"""


class CareerOption(BaseModel):
    title: str
    field: str = ""
    kind: Kind = "adjacent"
    fit: int = 0
    why: str = ""
    transferable: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)


class CareerSuggestions(BaseModel):
    options: list[CareerOption] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)
    # Навыки на момент подбора — интерфейс подскажет обновить, если они изменились
    skills_snapshot: list[str] = Field(default_factory=list)
    extra_snapshot: str = ""


def suggest_careers(
    skills: list[str],
    extra: str,
    experience_years: float | None,
    industries: list[str],
    llm: LLM,
) -> CareerSuggestions:
    if not skills and not extra.strip():
        raise ValueError("Добавьте навыки — по ним подбираются профессии")
    lines = [f"НАВЫКИ: {', '.join(skills)}"]
    if extra.strip():
        lines.append(f"ЕЩЁ УМЕЕТ (нет в резюме): {extra.strip()}")
    if experience_years:
        lines.append(f"Опыт работы: {experience_years:g} лет")
    if industries:
        lines.append(f"Отрасли, где есть опыт: {', '.join(industries)}")

    data = llm.chat_json(SYSTEM_PROMPT, "\n".join(lines))
    options = [_option(o) for o in (data.get("options") or []) if isinstance(o, dict)]
    options = [o for o in options if o.title]
    # Одна профессия под разными регистрами/пробелами — оставляем первую
    seen: set[str] = set()
    unique = []
    for o in options:
        key = " ".join(o.title.lower().split())
        if key not in seen:
            seen.add(key)
            unique.append(o)
    order = {"core": 0, "adjacent": 1, "new_field": 2}
    unique.sort(key=lambda o: (order[o.kind], -o.fit))
    return CareerSuggestions(
        options=unique[:14], skills_snapshot=list(skills), extra_snapshot=extra
    )


def _option(raw: dict[str, Any]) -> CareerOption:
    kind = raw.get("kind")
    try:
        fit = max(0, min(100, int(raw.get("fit", 0))))
    except (TypeError, ValueError):
        fit = 0
    return CareerOption(
        title=str(raw.get("title", "")).strip(),
        field=str(raw.get("field", "")).strip(),
        kind=kind if kind in ("core", "adjacent", "new_field") else "adjacent",
        fit=fit,
        why=str(raw.get("why", "")).strip(),
        transferable=_strs(raw.get("transferable"), 6),
        gaps=_strs(raw.get("gaps"), 4),
        queries=_strs(raw.get("queries"), 3),
    )


def _strs(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()][:limit]
