from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Vacancy(SQLModel, table=True):
    """A vacancy normalized to one schema regardless of the source it came from."""

    id: str = Field(primary_key=True, description="'<source>:<external_id>'")
    source: str = Field(index=True)
    external_id: str

    title: str
    company: str | None = None
    region: str | None = Field(default=None, index=True)
    address: str | None = None

    salary_from: int | None = None
    salary_to: int | None = None
    currency: str = "RUB"

    employment: str | None = None
    schedule: str | None = None
    is_remote: bool = Field(default=False, index=True)

    requirements: str | None = None
    duties: str | None = None
    conditions: str | None = None
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    experience_years: int | None = None
    education: str | None = None
    category: str | None = None

    url: str
    published_at: date | None = None
    source_updated_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=utcnow)

    raw: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    @property
    def text(self) -> str:
        """All descriptive text in one string — input for remote detection and matching."""
        parts = [self.title, self.requirements, self.duties, self.conditions, " ".join(self.skills)]
        return "\n".join(p for p in parts if p)
