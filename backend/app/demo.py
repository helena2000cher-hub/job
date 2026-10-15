"""Public demo: a sandbox with a fictional candidate and vacancies, reset to the seed periodically.

Visitors who are not logged in work with this sandbox, never with the owner's data.
"""

import json
import logging
import threading
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.models import Application, Match, Vacancy
from app.profile import Profile, save_profile

log = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parents[1] / "demo" / "seed.json"


def reset_demo(engine: Engine, profile_path: Path, seed_path: Path = SEED_PATH) -> None:
    """Recreate the demo database and profile from the seed file."""
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    profile = Profile.model_validate(seed["profile"])
    save_profile(profile, profile_path)
    fingerprint = profile.fingerprint()

    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    today = date.today()
    with Session(engine) as s:
        for i, item in enumerate(seed["vacancies"]):
            vacancy = Vacancy(
                id=item["id"],
                source=item["source"],
                external_id=item["id"].split(":")[1],
                title=item["title"],
                company=item["company"],
                salary_from=item.get("salary_from"),
                salary_to=item.get("salary_to"),
                employment="Полная занятость",
                is_remote=True,
                requirements=item.get("requirements"),
                duties=item.get("duties"),
                conditions=item.get("conditions"),
                skills=item.get("skills", []),
                url=f"https://example.com/demo-vacancy/{i + 1}",
                published_at=today - timedelta(days=i + 1),
            )
            m = item["match"]
            s.add(vacancy)
            s.add(
                Match(
                    vacancy_id=vacancy.id,
                    profile_fingerprint=fingerprint,
                    content_hash=vacancy.content_hash(),
                    score=m["score"],
                    similarity=m["score"] / 100,
                    matched_skills=m["matched"],
                    missing_skills=m["missing"],
                    red_flags=m["red_flags"],
                    verdict=m["verdict"],
                    model="demo",
                )
            )
        for a in seed["applications"]:
            days = a.pop("applied_days_ago")
            s.add(Application(**a, applied_at=today - timedelta(days=days) if days else None))
        s.commit()


class DemoResetter:
    """Resets the demo sandbox now and then every `hours` in a daemon thread."""

    def __init__(self, engine: Engine, profile_path: Path, hours: float) -> None:
        self._engine = engine
        self._profile_path = profile_path
        self._interval = hours * 3600
        self._lock = threading.Lock()
        self.reset()
        if self._interval > 0:
            threading.Thread(target=self._loop, daemon=True).start()

    def reset(self) -> None:
        with self._lock:
            reset_demo(self._engine, self._profile_path)

    def _loop(self) -> None:
        stop = threading.Event()
        while not stop.wait(self._interval):
            try:
                self.reset()
                log.info("demo sandbox reset")
            except Exception:
                log.exception("demo reset failed")
