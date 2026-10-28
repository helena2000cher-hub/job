"""Background «Обновить»: collect from the chosen sources, then re-run matching."""

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.collecting import SOURCE_TITLES, collect
from app.config import get_settings
from app.llm import PolzaLLM
from app.matching.pipeline import run_matching
from app.models import utcnow
from app.profile import load_profile

log = logging.getLogger(__name__)

# Сколько вакансий брать на один запрос из профиля: Exa платный, trudvsem медленный.
LIMITS = {"exa": 20, "trudvsem": 50, "superjob": 50}
MATCH_TOP_N = 40


@dataclass
class RefreshState:
    running: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None
    new_vacancies: int = 0
    scored: int = 0
    cost_dollars: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


Runner = Callable[[RefreshState, list[str], Engine, Path], None]


def default_runner(state: RefreshState, sources: list[str], engine: Engine, profile_path: Path):
    profile = load_profile(profile_path)
    prefs = profile.preferences
    region = None if prefs.remote_only else get_settings().default_region_code

    for source in sources:
        state.log.append(f"Ищу на {SOURCE_TITLES.get(source, source)}…")
        result = collect(
            source,
            profile.effective_queries(),  # только отмеченные профессии
            remote_only=prefs.remote_only,
            region_code=region,
            limit=LIMITS.get(source, 30),
            on_progress=state.log.append,
            engine=engine,  # база того, кто запустил поиск (владелец или пользователь)
        )
        state.new_vacancies += result.created
        state.cost_dollars += result.cost_dollars
        title = SOURCE_TITLES.get(source, source)
        state.log.append(f"{title}: новых вакансий {result.created}")

    state.log.append("Сравниваю вакансии с вашим профилем…")
    with Session(engine, expire_on_commit=False) as session:
        report = run_matching(session, profile, PolzaLLM(), top_n=MATCH_TOP_N)
    state.scored = report.scored
    state.log.append(f"Оценено вакансий: {report.scored + report.reused}")


class RefreshJob:
    def __init__(self, engine: Engine, profile_path: Path, runner: Runner = default_runner):
        self._engine = engine
        self._profile_path = profile_path
        self._runner = runner
        self._lock = threading.Lock()
        self.state = RefreshState()

    def start(self, sources: list[str]) -> bool:
        """Start in a background thread; False if a refresh is already running."""
        with self._lock:
            if self.state.running:
                return False
            self.state = RefreshState(running=True, started_at=utcnow())
        threading.Thread(target=self._run, args=(sources,), daemon=True).start()
        return True

    def _run(self, sources: list[str]) -> None:
        try:
            self._runner(self.state, sources, self._engine, self._profile_path)
            self.state.log.append("Готово")
        except Exception as exc:
            log.exception("refresh failed")
            self.state.error = str(exc)
        finally:
            self.state.finished_at = utcnow()
            self.state.running = False
