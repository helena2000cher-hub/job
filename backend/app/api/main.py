"""Web API for the UI. Run: uvicorn app.api.main:app --reload (from backend/)."""

from collections import Counter
from collections.abc import Callable, Iterator
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
from app.cover_letter import Tone, generate_cover_letter
from app.db import get_engine, init_db
from app.llm import LLM, PolzaLLM
from app.models import STAGES, Application, Match, Vacancy, VacancyMark, utcnow
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
    mark: str | None  # "saved" — в трекере, "hidden" — скрыта из ленты
    stage: str | None  # этап в трекере откликов


class ApplicationOut(BaseModel):
    stage: str
    notes: str
    contact: str
    applied_at: date | None
    cover_letter: str
    cover_letter_subject: str
    updated_at: datetime


class TrackerItem(FeedItem):
    application: ApplicationOut


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
    application: ApplicationOut | None


class Feed(BaseModel):
    items: list[FeedItem]
    total_vacancies: int
    scored: int
    sources: dict[str, int]
    profile_ready: bool
    last_fetched_at: datetime | None


class MarkIn(BaseModel):
    status: Literal["saved", "hidden"] | None


Stage = Literal["interesting", "applied", "interview", "offer", "rejected"]
assert set(Stage.__args__) == set(STAGES)


class ApplicationIn(BaseModel):
    stage: Stage | None = None
    notes: str | None = None
    contact: str | None = None
    applied_at: date | None = None
    cover_letter: str | None = None
    cover_letter_subject: str | None = None


class CoverLetterIn(BaseModel):
    tone: Tone = "business"
    wishes: str = ""


class RefreshIn(BaseModel):
    sources: list[str] = ["trudvsem", "exa"]


def _item(
    model: type[FeedItem],
    v: Vacancy,
    m: Match | None,
    mark: VacancyMark | None,
    application: Application | None,
):
    data = v.model_dump()
    data.update(
        score=m.score if m else None,
        similarity=m.similarity if m else None,
        verdict=m.verdict if m else "",
        matched_skills=m.matched_skills if m else [],
        missing_skills=m.missing_skills if m else [],
        red_flags=m.red_flags if m else [],
        mark="hidden" if mark else ("saved" if application else None),
        stage=application.stage if application else None,
        application=application.model_dump() if application else None,
    )
    return model.model_validate(data)


def _untouched(a: Application) -> bool:
    return a.stage == "interesting" and not (a.notes or a.contact or a.cover_letter)


def _migrate_saved_marks(engine: Engine) -> None:
    """Before the tracker, «Сохранить» was a mark; now it is an Application at «Интересно»."""
    with Session(engine) as s:
        for mark in s.exec(select(VacancyMark).where(VacancyMark.status == "saved")).all():
            if s.get(Application, mark.vacancy_id) is None:
                s.add(Application(vacancy_id=mark.vacancy_id))
            s.delete(mark)
        s.commit()


def create_app(
    engine: Engine | None = None,
    profile_path: Path = PROFILE_PATH,
    runner: Runner = default_runner,
    serve_frontend: bool = True,
    llm_factory: Callable[[], LLM] = PolzaLLM,
    resume_path: Path = RESUME_PATH,
) -> FastAPI:
    engine = engine or get_engine()
    init_db(engine)
    _migrate_saved_marks(engine)
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
            select(Vacancy, Match, VacancyMark, Application)
            .join(Match, Match.vacancy_id == Vacancy.id)
            .join(VacancyMark, VacancyMark.vacancy_id == Vacancy.id, isouter=True)
            .join(Application, Application.vacancy_id == Vacancy.id, isouter=True)
            .where(Match.profile_fingerprint == fingerprint)
        ).all()

        sources = Counter(row[0].source for row in rows)
        items = []
        for v, m, mark, application in rows:
            hidden = mark is not None
            if (view == "all" and hidden) or (view == "hidden" and not hidden):
                continue
            if view == "saved" and application is None:
                continue
            if m.score < min_score or (source and v.source != source):
                continue
            items.append(_item(FeedItem, v, m, mark, application))
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
        return _item(
            VacancyDetail,
            v,
            s.get(Match, vacancy_id),
            s.get(VacancyMark, vacancy_id),
            s.get(Application, vacancy_id),
        )

    @app.put("/api/vacancies/{vacancy_id}/mark")
    def mark(vacancy_id: str, body: MarkIn, s: SessionDep):
        if s.get(Vacancy, vacancy_id) is None:
            raise HTTPException(404, "Вакансия не найдена")
        hidden = s.get(VacancyMark, vacancy_id)
        application = s.get(Application, vacancy_id)
        if body.status == "hidden":
            s.merge(VacancyMark(vacancy_id=vacancy_id, status="hidden", updated_at=utcnow()))
        elif hidden:
            s.delete(hidden)
        if body.status == "saved" and application is None:
            s.add(Application(vacancy_id=vacancy_id))
        # «Убрать из сохранённых» удаляет только нетронутую запись — историю отклика не теряем
        if body.status is None and application and _untouched(application):
            s.delete(application)
        s.commit()
        return {"status": body.status}

    @app.get("/api/applications", response_model=list[TrackerItem])
    def applications(s: SessionDep):
        rows = s.exec(
            select(Vacancy, Application, Match)
            .join(Application, Application.vacancy_id == Vacancy.id)
            .join(Match, Match.vacancy_id == Vacancy.id, isouter=True)
        ).all()
        items = [_item(TrackerItem, v, m, None, a) for v, a, m in rows]
        items.sort(key=lambda i: i.application.updated_at, reverse=True)
        return items

    @app.put("/api/applications/{vacancy_id}", response_model=ApplicationOut)
    def update_application(vacancy_id: str, body: ApplicationIn, s: SessionDep):
        if s.get(Vacancy, vacancy_id) is None:
            raise HTTPException(404, "Вакансия не найдена")
        application = s.get(Application, vacancy_id) or Application(vacancy_id=vacancy_id)
        for field, value in body.model_dump(exclude_unset=True).items():
            if value is not None or field == "applied_at":
                setattr(application, field, value)
        if application.stage == "applied" and application.applied_at is None:
            application.applied_at = date.today()  # дата отклика проставляется сама
        application.updated_at = utcnow()
        s.add(application)
        s.commit()
        s.refresh(application)
        return application

    @app.delete("/api/applications/{vacancy_id}", status_code=204)
    def delete_application(vacancy_id: str, s: SessionDep):
        application = s.get(Application, vacancy_id)
        if application:
            s.delete(application)
            s.commit()

    @app.post("/api/applications/{vacancy_id}/cover-letter", response_model=ApplicationOut)
    def cover_letter(vacancy_id: str, body: CoverLetterIn, s: SessionDep):
        vacancy = s.get(Vacancy, vacancy_id)
        if vacancy is None:
            raise HTTPException(404, "Вакансия не найдена")
        profile = current_profile()
        if profile is None:
            raise HTTPException(400, "Сначала создайте профиль")
        letter = generate_cover_letter(
            profile,
            vacancy,
            s.get(Match, vacancy_id),
            llm_factory(),
            tone=body.tone,
            wishes=body.wishes,
            resume_path=resume_path,
        )
        application = s.get(Application, vacancy_id) or Application(vacancy_id=vacancy_id)
        application.cover_letter = letter.letter
        application.cover_letter_subject = letter.subject
        application.updated_at = utcnow()
        s.add(application)
        s.commit()
        s.refresh(application)
        return application

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
        if not resume_path.exists():
            raise HTTPException(400, "Положите резюме в data/resume.pdf")
        old = current_profile()
        profile = build_profile(read_resume(resume_path), llm_factory())
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
