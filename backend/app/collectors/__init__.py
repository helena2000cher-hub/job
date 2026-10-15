from app.collectors.base import Collector, SearchQuery
from app.collectors.exa import ExaCollector
from app.collectors.trudvsem import TrudvsemCollector

COLLECTORS: dict[str, type[Collector]] = {
    TrudvsemCollector.name: TrudvsemCollector,
    ExaCollector.name: ExaCollector,
}

__all__ = ["COLLECTORS", "Collector", "ExaCollector", "SearchQuery", "TrudvsemCollector"]
