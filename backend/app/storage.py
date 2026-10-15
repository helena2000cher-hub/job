from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import Session

from app.models import Vacancy, utcnow


@dataclass
class SaveStats:
    created: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated


def save_vacancies(session: Session, vacancies: Iterable[Vacancy]) -> SaveStats:
    """Insert new vacancies and refresh existing ones (matched by id)."""
    stats = SaveStats()
    for vacancy in vacancies:
        existing = session.get(Vacancy, vacancy.id)
        if existing is None:
            session.add(vacancy)
            stats.created += 1
            continue
        for field, value in vacancy.model_dump(exclude={"id"}).items():
            setattr(existing, field, value)
        existing.fetched_at = utcnow()
        stats.updated += 1
    session.commit()
    return stats
