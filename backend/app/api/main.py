"""Web API for the UI. Run: uvicorn app.api.main:app --reload (from backend/)."""

from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from app.api.refresh import RefreshJob, Runner, default_runner
from app.collectors import COLLECTORS
from app.config import PROJECT_ROOT
from app.db import get_engine, init_db
from app.llm import PolzaLLM
from app.models import Match, Vacancy, VacancyMark, utcnow
from app.profile import PROFILE_PATH, RESUME_PATH, Profile, build_profile, read_resume, save_profile

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


class FeedItem(BaseModel):
    id: str
    title: str
    company: str | None
    region: str | None
    salary_from: int | None
    salary_to: int | None
    currency: str
    is_remote: bool
    source: str
    url: str
    published_at: date | None
    score: int | None
    similarity: float | None
    verdict: str
    matched_skills: list[str]
    missing_skills: list[str]
    red_flags: list[str]
    mark: str | None


class VacancyDetail(FeedItem):
    employment: str | None
    schedule: str | None
    experience_years: int | None
    education: str | None
    requirements: str | None
    duties: str | None
    conditions: str | None
    skills: list[str]
    fetched_at: datetime


class Feed(BaseModel):
    items: list[FeedItem]
    total_vacancies: int
    scored: int
    sources: dict[str, int]
    profile_ready: bool
    last_fetched_at: datetime | None


class MarkIn(BaseModel):
    status: Literal["saved", "hidden"] | None


class RefreshIn(BaseModel):
    sources: list[str] = ["trudvsem", "exa"]


def _item(model: type[FeedItem], v: Vacancy, m: Match | None, mark: VacancyMark | None):
    data = v.model_dump()
    data.update(
        score=m.score if m else None,
        similarity=m.similarity if m else None,
        verdict=m.verdict if m else "",
        matched_skills=m.matched_skills if m else [],
        missing_skills=m.missing_skills if m else [],
        red_flags=m.red_flags if m else [],
        mark=mark.status if mark else None,
    )
    return model.model_validate(data)


def create_app(
    engine: Engine | None = None,
    profile_path: Path = PROFILE_PATH,
    runner: Runner = default_runner,
    serve_frontend: bool = True,
) -> FastAPI:
    engine = engine or get_engine()
    init_db(engine)
    app = FastAPI(title="Job Matcher API")
    app.state.refresh = RefreshJob(engine, profile_path, runner)

    def session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    SessionDep = Annotated[Session, Depends(session)]

    def current_profile() -> Profile | None:
        if not profile_path.exists():
            return None
        return Profile.model_validate_json(profile_path.read_text(encoding="utf-8"))

    @app.get("/api/feed", response_model=Feed)
    def feed(
        s: SessionDep,
        min_score: int = 0,
        source: str | None = None,
        view: Literal["all", "saved", "hidden"] = "all",
    ):
        profile = current_profile()
        fingerprint = profile.fingerprint() if profile else None
        rows = s.exec(
            select(Vacancy, Match, VacancyMark)
            .join(Match, Match.vacancy_id == Vacancy.id)
            .join(VacancyMark, VacancyMark.vacancy_id == Vacancy.id, isouter=True)
            .where(Match.profile_fingerprint == fingerprint)
        ).all()

        sources = Counter(v.source for v, _, _ in rows)
        items = []
        for v, m, mark in rows:
            status = mark.status if mark else None
            if view == "all" and status == "hidden":
                continue
            if view != "all" and status != view:
                continue
            if m.score < min_score or (source and v.source != source):
                continue
            items.append(_item(FeedItem, v, m, mark))
        items.sort(key=lambda i: (i.score or 0, i.similarity or 0), reverse=True)

        return Feed(
            items=items,
            total_vacancies=s.exec(select(func.count()).select_from(Vacancy)).one(),
            scored=len(rows),
            sources=dict(sources.most_common()),
            profile_ready=profile is not None,
            last_fetched_at=s.exec(select(func.max(Vacancy.fetched_at))).one(),
        )

    @app.get("/api/vacancies/{vacancy_id}", response_model=VacancyDetail)
    def vacancy(vacancy_id: str, s: SessionDep):
        v = s.get(Vacancy, vacancy_id)
        if v is None:
            raise HTTPException(404, "Вакансия не найдена")
        return _item(VacancyDetail, v, s.get(Match, vacancy_id), s.get(VacancyMark, vacancy_id))

    @app.put("/api/vacancies/{vacancy_id}/mark")
    def mark(vacancy_id: str, body: MarkIn, s: SessionDep):
        if s.get(Vacancy, vacancy_id) is None:
            raise HTTPException(404, "Вакансия не найдена")
        existing = s.get(VacancyMark, vacancy_id)
        if body.status is None:
            if existing:
                s.delete(existing)
        else:
            s.merge(VacancyMark(vacancy_id=vacancy_id, status=body.status, updated_at=utcnow()))
        s.commit()
        return {"status": body.status}

    @app.get("/api/profile", response_model=Profile)
    def get_profile():
        profile = current_profile()
        if profile is None:
            raise HTTPException(404, "Профиль ещё не создан")
        return profile

    @app.put("/api/profile", response_model=Profile)
    def put_profile(profile: Profile):
        save_profile(profile, profile_path)
        return profile

    @app.post("/api/profile/rebuild", response_model=Profile)
    def rebuild_profile():
        if not RESUME_PATH.exists():
            raise HTTPException(400, "Положите резюме в data/resume.pdf")
        old = current_profile()
        profile = build_profile(read_resume(RESUME_PATH), PolzaLLM())
        if old:
            profile.preferences = old.preferences  # ручные настройки не теряем
        save_profile(profile, profile_path)
        return profile

    @app.get("/api/refresh")
    def refresh_status(request: Request):
        return request.app.state.refresh.state.to_dict()

    @app.post("/api/refresh", status_code=202)
    def refresh(body: RefreshIn, request: Request):
        unknown = set(body.sources) - set(COLLECTORS)
        if unknown:  # пустой список допустим — только пересчитать оценки, без сбора
            raise HTTPException(400, f"Неизвестные источники: {', '.join(unknown)}")
        if current_profile() is None:
            raise HTTPException(400, "Сначала создайте профиль")
        if not request.app.state.refresh.start(body.sources):
            raise HTTPException(409, "Обновление уже идёт")
        return request.app.state.refresh.state.to_dict()

    # Собранный фронтенд (npm run build) отдаётся тем же сервером — один процесс для деплоя.
    if serve_frontend and FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


app = create_app()
