"""Application tracker logic: automatic «no response» and response analytics."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models import (
    NO_RESPONSE_DAYS,
    POSITIVE_STAGES,
    SENT_STAGES,
    Application,
    Match,
    Vacancy,
    utcnow,
)

TONE_LABELS = {"business": "Деловой тон", "friendly": "Дружелюбный тон"}


def mark_no_response(session: Session, today: date | None = None) -> int:
    """Move «applied» to «no_response» after NO_RESPONSE_DAYS days without any change."""
    today = today or date.today()
    deadline = today - timedelta(days=NO_RESPONSE_DAYS)
    moved = 0
    for a in session.exec(select(Application).where(Application.stage == "applied")).all():
        last_change = (a.stage_changed_at or datetime.min).date()
        if a.applied_at and a.applied_at <= deadline and last_change <= deadline:
            a.stage = "no_response"
            a.stage_changed_at = utcnow()
            a.updated_at = utcnow()
            session.add(a)
            moved += 1
    if moved:
        session.commit()
    return moved


def _bucket(groups: dict[str, dict[str, int]], key: str, positive: bool) -> None:
    groups[key]["sent"] += 1
    groups[key]["positive"] += int(positive)


def _rows(groups: dict[str, dict[str, int]], order: list[str] | None = None) -> list[dict]:
    keys = order or sorted(groups, key=lambda k: -groups[k]["sent"])
    return [
        {
            "label": k,
            "sent": groups[k]["sent"],
            "positive": groups[k]["positive"],
            "rate": round(groups[k]["positive"] / groups[k]["sent"], 3),
        }
        for k in keys
        if groups[k]["sent"]
    ]


def _score_band(score: int | None) -> str:
    if score is None:
        return "без оценки"
    if score >= 80:
        return "80+"
    if score >= 60:
        return "60–79"
    return "до 60"


def compute_analytics(
    session: Session, profile_fingerprint: str | None, today: date | None = None
) -> dict[str, Any]:
    today = today or date.today()
    rows = session.exec(
        select(Application, Vacancy, Match)
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .join(Match, Match.vacancy_id == Vacancy.id, isouter=True)
    ).all()

    stages = Counter(a.stage for a, _, _ in rows)
    sent_rows = [(a, v, m) for a, v, m in rows if a.stage in SENT_STAGES]
    positive = sum(stages[s] for s in POSITIVE_STAGES)
    sent = len(sent_rows)

    by_letter: dict[str, dict[str, int]] = defaultdict(lambda: {"sent": 0, "positive": 0})
    by_score: dict[str, dict[str, int]] = defaultdict(lambda: {"sent": 0, "positive": 0})
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"sent": 0, "positive": 0})
    for a, v, m in sent_rows:
        ok = a.stage in POSITIVE_STAGES
        if not a.cover_letter:
            letter = "Без письма"
        else:
            letter = TONE_LABELS.get(a.cover_letter_tone or "", "Письмо (тон не отмечен)")
        _bucket(by_letter, letter, ok)
        _bucket(by_score, _score_band(m.score if m else None), ok)
        _bucket(by_source, v.source, ok)

    # Чего чаще всего не хватает в подходящих вакансиях — материал для резюме и обучения
    gaps: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    if profile_fingerprint:
        matches = session.exec(
            select(Match).where(Match.profile_fingerprint == profile_fingerprint, Match.score >= 60)
        ).all()
        for m in matches:
            for skill in m.missing_skills:
                key = skill.strip().lower()
                if key:
                    gaps[key] += 1
                    spellings[key][skill.strip()] += 1

    week_ago = today - timedelta(days=7)
    return {
        "total": len(rows),
        "stages": {s: stages.get(s, 0) for s in stages},
        "sent": sent,
        "sent_last_7_days": sum(
            1 for a, _, _ in sent_rows if a.applied_at and a.applied_at > week_ago
        ),
        "positive": positive,
        "rejected": stages.get("rejected", 0),
        "no_response": stages.get("no_response", 0),
        "waiting": stages.get("applied", 0),
        "response_rate": round(positive / sent, 3) if sent else None,
        "by_letter": _rows(by_letter),
        "by_score": _rows(by_score, ["80+", "60–79", "до 60", "без оценки"]),
        "by_source": _rows(by_source),
        "top_gaps": [{"skill": _label(spellings[k]), "count": n} for k, n in gaps.most_common(12)],
        "no_response_days": NO_RESPONSE_DAYS,
    }


def _label(spellings: Counter[str]) -> str:
    """Most frequent spelling of a skill; on a tie prefer the one with capitals («SQL» > «sql»)."""
    return max(spellings, key=lambda s: (spellings[s], sum(ch.isupper() for ch in s)))
