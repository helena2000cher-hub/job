"""Web API for the UI. Run: uvicorn app.api.main:app --reload (from backend/).

Every request works in a workspace: the owner's (valid session cookie) or the public demo sandbox.
"""

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, func, select

from app.advice import Advice, generate_advice, load_advice, save_advice
from app.api.auth import COOKIE_NAME, SESSION_DAYS, Auth
from app.api.refresh import RefreshJob, RefreshState, Runner, default_runner
from app.collectors import COLLECTORS
from app.config import DATA_DIR, PROJECT_ROOT, get_settings
from app.cover_letter import Tone, generate_cover_letter
from app.db import get_engine, init_db
from app.demo import DemoResetter
from app.llm import LLM, PolzaLLM
from app.models import STAGES, Application, Match, Vacancy, VacancyMark, utcnow
from app.profile import PROFILE_PATH, RESUME_PATH, Profile, build_profile, read_resume, save_profile
from app.tracker import compute_analytics, mark_no_response

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
    cover_letter_tone: str | None = None
    updated_at: datetime
    stage_changed_at: datetime | None = None


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


Stage = Literal[
    "interesting", "applied", "no_response", "test_task", "interview", "offer", "rejected"
]
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


class LoginIn(BaseModel):
    password: str


class Me(BaseModel):
    role: Literal["owner", "demo"]
    auth_enabled: bool
    demo_available: bool


@dataclass(frozen=True)
class Workspace:
    engine: Engine
    profile_path: Path
    resume_path: Path
    demo: bool = False


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
    auth: Auth | None = None,
    demo_engine: Engine | None = None,
    demo_profile_path: Path | None = None,
    demo_reset_hours: float = 0,
    cookie_secure: bool = False,
) -> FastAPI:
    engine = engine or get_engine()
    init_db(engine)
    _migrate_saved_marks(engine)
    auth = auth or Auth("", "")  # по умолчанию вход выключен: локально все — владелец
    app = FastAPI(title="Job Matcher API")
    app.state.refresh = RefreshJob(engine, profile_path, runner)

    owner = Workspace(engine, profile_path, resume_path)
    demo: Workspace | None = None
    if auth.enabled and demo_engine is not None and demo_profile_path is not None:
        demo = Workspace(demo_engine, demo_profile_path, DATA_DIR / "-no-demo-resume-", demo=True)
        app.state.demo = DemoResetter(demo_engine, demo_profile_path, demo_reset_hours)

    def workspace(request: Request) -> Workspace:
        if auth.verify(request.cookies.get(COOKIE_NAME)):
            return owner
        if demo is not None:
            return demo
        raise HTTPException(401, "Нужно войти")

    WsDep = Annotated[Workspace, Depends(workspace)]

    def owner_only(ws: WsDep) -> Workspace:
        if ws.demo:
            raise HTTPException(403, "В демо-режиме это недоступно: функция вызывает платные API")
        return ws

    OwnerDep = Annotated[Workspace, Depends(owner_only)]

    def session(ws: WsDep) -> Iterator[Session]:
        with Session(ws.engine) as s:
            yield s

    SessionDep = Annotated[Session, Depends(session)]

    def current_profile(ws: Workspace) -> Profile | None:
        if not ws.profile_path.exists():
            return None
        return Profile.model_validate_json(ws.profile_path.read_text(encoding="utf-8"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/auth/me", response_model=Me)
    def me(ws: WsDep):
        return Me(
            role="demo" if ws.demo else "owner",
            auth_enabled=auth.enabled,
            demo_available=demo is not None,
        )

    @app.post("/api/auth/login", response_model=Me)
    def login(body: LoginIn, request: Request, response: Response):
        if not auth.enabled:
            return Me(role="owner", auth_enabled=False, demo_available=False)
        client = request.client.host if request.client else "?"
        if auth.is_blocked(client):
            raise HTTPException(429, "Слишком много попыток. Подождите 5 минут")
        if not auth.check_password(body.password):
            auth.record_failure(client)
            raise HTTPException(401, "Неверный пароль")
        auth.reset_failures(client)
        response.set_cookie(
            COOKIE_NAME,
            auth.issue(),
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
        )
        return Me(role="owner", auth_enabled=True, demo_available=demo is not None)

    @app.post("/api/auth/logout", status_code=204)
    def logout(response: Response):
        response.delete_cookie(COOKIE_NAME)

    @app.get("/api/feed", response_model=Feed)
    def feed(
        s: SessionDep,
        ws: WsDep,
        min_score: int = 0,
        source: str | None = None,
        view: Literal["all", "saved", "hidden"] = "all",
    ):
        profile = current_profile(ws)
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
        mark_no_response(s)
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
        existing = s.get(Application, vacancy_id)
        application = existing or Application(vacancy_id=vacancy_id)
        old_stage = existing.stage if existing else None
        for field, value in body.model_dump(exclude_unset=True).items():
            if value is not None or field == "applied_at":
                setattr(application, field, value)
        if body.stage is not None and body.stage != old_stage:
            application.stage_changed_at = utcnow()
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
    def cover_letter(vacancy_id: str, body: CoverLetterIn, s: SessionDep, ws: OwnerDep):
        vacancy = s.get(Vacancy, vacancy_id)
        if vacancy is None:
            raise HTTPException(404, "Вакансия не найдена")
        profile = current_profile(ws)
        if profile is None:
            raise HTTPException(400, "Сначала создайте профиль")
        letter = generate_cover_letter(
            profile,
            vacancy,
            s.get(Match, vacancy_id),
            llm_factory(),
            tone=body.tone,
            wishes=body.wishes,
            resume_path=ws.resume_path,
        )
        application = s.get(Application, vacancy_id) or Application(vacancy_id=vacancy_id)
        application.cover_letter = letter.letter
        application.cover_letter_subject = letter.subject
        application.cover_letter_tone = body.tone
        application.updated_at = utcnow()
        s.add(application)
        s.commit()
        s.refresh(application)
        return application

    @app.get("/api/profile", response_model=Profile)
    def get_profile(ws: WsDep):
        profile = current_profile(ws)
        if profile is None:
            raise HTTPException(404, "Профиль ещё не создан")
        return profile

    @app.put("/api/profile", response_model=Profile)
    def put_profile(profile: Profile, ws: OwnerDep):  # в демо смена профиля сломала бы ленту
        save_profile(profile, ws.profile_path)
        return profile

    @app.post("/api/profile/rebuild", response_model=Profile)
    def rebuild_profile(ws: OwnerDep):
        if not ws.resume_path.exists():
            raise HTTPException(400, "Положите резюме в data/resume.pdf")
        old = current_profile(ws)
        profile = build_profile(read_resume(ws.resume_path), llm_factory())
        if old:
            profile.preferences, profile.extra = old.preferences, old.extra  # ручное не теряем
        save_profile(profile, ws.profile_path)
        return profile

    def advice_path(ws: Workspace) -> Path:
        return ws.profile_path.parent / ("demo_advice.json" if ws.demo else "advice.json")

    @app.get("/api/analytics")
    def analytics(s: SessionDep, ws: WsDep):
        mark_no_response(s)
        profile = current_profile(ws)
        stats = compute_analytics(s, profile.fingerprint() if profile else None)
        advice = load_advice(advice_path(ws))
        return {**stats, "advice": advice.model_dump(mode="json") if advice else None}

    @app.post("/api/analytics/advice", response_model=Advice)
    def make_advice(s: SessionDep, ws: OwnerDep):
        profile = current_profile(ws)
        if profile is None:
            raise HTTPException(400, "Сначала создайте профиль")
        mark_no_response(s)
        advice = generate_advice(
            profile, compute_analytics(s, profile.fingerprint()), llm_factory()
        )
        save_advice(advice, advice_path(ws))
        return advice

    @app.get("/api/refresh")
    def refresh_status(request: Request, ws: WsDep):
        if ws.demo:
            return RefreshState().to_dict()  # журнал владельца гостям не показываем
        return request.app.state.refresh.state.to_dict()

    @app.post("/api/refresh", status_code=202)
    def refresh(body: RefreshIn, request: Request, ws: OwnerDep):
        unknown = set(body.sources) - set(COLLECTORS)
        if unknown:  # пустой список допустим — только пересчитать оценки, без сбора
            raise HTTPException(400, f"Неизвестные источники: {', '.join(unknown)}")
        if current_profile(ws) is None:
            raise HTTPException(400, "Сначала создайте профиль")
        if not request.app.state.refresh.start(body.sources):
            raise HTTPException(409, "Обновление уже идёт")
        return request.app.state.refresh.state.to_dict()

    # Собранный фронтенд (npm run build) отдаётся тем же сервером — один процесс для деплоя.
    if serve_frontend and FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


def create_app_from_settings() -> FastAPI:
    """Production wiring from .env: password login and the public demo sandbox."""
    settings = get_settings()
    auth = Auth(settings.app_password, settings.session_secret)
    demo_engine = None
    if auth.enabled and settings.demo_enabled:
        demo_engine = create_engine(
            f"sqlite:///{(DATA_DIR / 'demo.db').as_posix()}",
            connect_args={"check_same_thread": False},
        )
    return create_app(
        auth=auth,
        demo_engine=demo_engine,
        demo_profile_path=DATA_DIR / "demo_profile.json",
        demo_reset_hours=settings.demo_reset_hours,
        cookie_secure=settings.cookie_secure,
    )


app = create_app_from_settings()
