from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from app.models import Vacancy


@dataclass(frozen=True)
class SearchQuery:
    text: str | None = None
    region_code: str | None = None  # None — по всей стране
    remote_only: bool = False
    limit: int = 200  # максимум вакансий за один сбор


class Collector(ABC):
    """A vacancy source. Each source turns its own format into the common Vacancy model."""

    name: str

    @abstractmethod
    def fetch(self, query: SearchQuery) -> Iterator[Vacancy]: ...
