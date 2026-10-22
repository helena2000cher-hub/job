from app.collectors.base import Collector, SearchQuery
from app.collectors.exa import ExaCollector
from app.collectors.superjob import SuperJobCollector
from app.collectors.trudvsem import TrudvsemCollector

COLLECTORS: dict[str, type[Collector]] = {
    TrudvsemCollector.name: TrudvsemCollector,
    ExaCollector.name: ExaCollector,
    SuperJobCollector.name: SuperJobCollector,
}

__all__ = [
    "COLLECTORS",
    "Collector",
    "ExaCollector",
    "SearchQuery",
    "SuperJobCollector",
    "TrudvsemCollector",
]
