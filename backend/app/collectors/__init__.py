from app.collectors.base import Collector, SearchQuery
from app.collectors.trudvsem import TrudvsemCollector

COLLECTORS: dict[str, type[Collector]] = {
    TrudvsemCollector.name: TrudvsemCollector,
}

__all__ = ["COLLECTORS", "Collector", "SearchQuery", "TrudvsemCollector"]
