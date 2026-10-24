"""Web API for the UI. Run: uvicorn app.api.main:app --reload (from backend/).

Every request works in a workspace: the owner's, a registered user's (each in its own folder
data/users/<id>/) or the public demo sandbox — chosen by the session cookie.
"""

import hashlib
import logging
import shutil
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, func, select

from app.accounts import AccountError, Accounts, User
from app.advice import Advice, generate_advice, load_advice, save_advice
from app.api.auth import (
    COOKIE_NAME,
    OAUTH_COOKIE,
    OWNER,
    SESSION_DAYS,
    Attempts,
    Auth,
    parse_user_payload,
    user_payload,
)
from app.api.refresh import RefreshJob, RefreshState, Runner, default_runner
from app.careers import suggest_careers
from app.collectors import COLLECTORS
from app.collectors.exa import fetch_vacancy, identify
from app.config import DATA_DIR, PROJECT_ROOT, get_settings
from app.cover_letter import Tone, generate_cover_letter
from app.db import get_engine, init_db
from app.demo import DemoResetter
from app.llm import LLM, PolzaLLM
from app.mailer import LogMailer, Mailer, SmtpMailer
from app.models import SENT_STAGES, STAGES, Application, Match, Vacancy, VacancyMark, utcnow
from app.oauth import VK, OAuthError, Provider, Yandex, http_client, new_verifier
from app.profile import PROFILE_PATH, RESUME_PATH, Profile, rebuild_profile, save_profile
from app.resume import (
    MAX_UPLOAD_BYTES,
    ResumeError,
    ResumeForm,
    ResumeSource,
    ResumeStore,
    extract_text,
    fetch_resume_text,
    form_from_text,
)
from app.tracker import compute_analytics, mark_no_response

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

log = logging.getLogger(__name__)


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
    "interesting",
    "applied",
    "no_response",
    "questionnaire",
    "test_task",
    "interview",
    "offer",
    "rejected",
]
assert set(Stage.__args__) == set(STAGES)


class ApplicationIn(BaseModel):
    stage: Stage | None = None
    notes: str | None = None
    contact: str | None = None
    applied_at: date | None = None
    cover_letter: str | None = None
    cover_letter_subject: str | None = None


class ManualApplicationIn(BaseModel):
    """Отклик, отправленный мимо сайта: по ссылке (данные подтянутся) или по названию."""

    url: str = ""
    title: str = ""
    company: str = ""
    stage: Stage = "applied"
    applied_at: date | None = None
    notes: str = ""


class ManualApplicationOut(BaseModel):
    vacancy_id: str
    title: str
    company: str | None
    fetched: bool  # данные вакансии подтянуты по ссылке
    application: ApplicationOut


class CoverLetterIn(BaseModel):
    tone: Tone = "business"
    wishes: str = ""
    mention_gaps: bool = True  # блок «Честно о пробелах» — каждый пробел вместе с плюсом


class LoginIn(BaseModel):
    password: str
    email: str = ""  # пусто — вход владельца по паролю из .env


class RegisterIn(BaseModel):
    email: str
    password: str
    consent: bool = False  # согласие на обработку персональных данных (152-ФЗ)


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str


class Me(BaseModel):
    role: Literal["owner", "user", "demo"]
    auth_enabled: bool
    demo_available: bool
    internals: bool = True  # показывать стоимость и сервисы (личный режим); False — для клиентов
    registration: bool = False  # можно зарегистрироваться
    providers: dict[str, str] = {}  # вход одной кнопкой: {"yandex": "Яндекс ID", ...}
    email: str | None = None
    name: str = ""


class Limit(BaseModel):
    used: int
    limit: int


@dataclass(frozen=True)
class Workspace:
    engine: Engine
    profile_path: Path
    resume_path: Path
    demo: bool = False
    user: User | None = dc_field(default=None, compare=False)  # None — владелец или демо


class ResumeOut(BaseModel):
    source: ResumeSource | None
    form: ResumeForm | None


class ResumeResult(BaseModel):
    profile: Profile
    source: ResumeSource


class ResumeLinkIn(BaseModel):
    url: str


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
    vacancy_fetcher: Callable[[str], Vacancy | None] = fetch_vacancy,
    resume_fetcher: Callable[[str], str] = fetch_resume_text,
    available_sources: Callable[[], dict[str, bool]] | None = None,
    public_mode: bool = False,
    auth: Auth | None = None,
    demo_engine: Engine | None = None,
    demo_profile_path: Path | None = None,
    demo_reset_hours: float = 0,
    cookie_secure: bool = False,
    accounts: Accounts | None = None,
    users_dir: Path = DATA_DIR / "users",
    mailer: Mailer | None = None,
    providers: dict[str, Provider] | None = None,
    oauth_client: Callable[[], httpx.Client] = http_client,
    public_url: str = "http://localhost:8000",
    limits: dict[str, int] | None = None,
    max_parallel_searches: int = 2,
) -> FastAPI:
    engine = engine or get_engine()
    init_db(engine)
    _migrate_saved_marks(engine)
    auth = auth or Auth("", "")  # по умолчанию вход выключен: локально все — владелец
    if not auth.enabled:
        accounts = None  # без входа владельца нельзя отличить пользователя от владельца
    mailer = mailer or LogMailer()
    providers = providers or {}
    limits = limits if limits is not None else get_settings().limits()
    public_url = public_url.rstrip("/")
    app = FastAPI(title="Работа в точку API")
    app.state.refresh = RefreshJob(engine, profile_path, runner)

    owner = Workspace(engine, profile_path, resume_path)
    demo: Workspace | None = None
    if auth.enabled and demo_engine is not None and demo_profile_path is not None:
        demo = Workspace(demo_engine, demo_profile_path, DATA_DIR / "-no-demo-resume-", demo=True)
        app.state.demo = DemoResetter(demo_engine, demo_profile_path, demo_reset_hours)

    # Пользователи: у каждого своя папка с базой, профилем и резюме; поиск — свой RefreshJob.
    user_engines: dict[int, Engine] = {}
    user_jobs: dict[int, RefreshJob] = {}
    users_lock = threading.Lock()

    def user_workspace(user: User) -> Workspace:
        folder = users_dir / str(user.id)
        with users_lock:
            if user.id not in user_engines:
                folder.mkdir(parents=True, exist_ok=True)
                user_engine = create_engine(
                    f"sqlite:///{(folder / 'jobs.db').as_posix()}",
                    connect_args={"check_same_thread": False},
                )
                init_db(user_engine)
                user_engines[user.id] = user_engine
                user_jobs[user.id] = RefreshJob(user_engine, folder / "profile.json", runner)
            return Workspace(
                user_engines[user.id], folder / "profile.json", folder / "resume.pdf", user=user
            )

    def refresh_job(request: Request, ws: Workspace) -> RefreshJob:
        return user_jobs[ws.user.id] if ws.user else request.app.state.refresh

    def current_user(request: Request) -> User | None:
        parsed = parse_user_payload(auth.read(request.cookies.get(COOKIE_NAME)))
        if accounts is None or parsed is None:
            return None
        user = accounts.get(parsed[0])
        return user if user and user.session_version == parsed[1] else None

    def workspace(request: Request) -> Workspace:
        if auth.verify(request.cookies.get(COOKIE_NAME)):
            return owner
        if user := current_user(request):
            return user_workspace(user)
        if demo is not None:
            return demo
        raise HTTPException(401, "Нужно войти")

    WsDep = Annotated[Workspace, Depends(workspace)]

    def owner_only(ws: WsDep) -> Workspace:
        if ws.demo:
            raise HTTPException(403, "В демо-режиме это недоступно: функция вызывает платные API")
        return ws

    OwnerDep = Annotated[Workspace, Depends(owner_only)]

    def charge(ws: Workspace, action: str) -> None:
        """Count a paid action against the user's daily limit; the owner has no limits."""
        if ws.user is None or accounts is None:
            return
        if not accounts.use(ws.user.id, action, limits.get(action, 0)):
            raise HTTPException(429, "Лимит на сегодня исчерпан — попробуйте завтра")

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

    def me_for(ws: Workspace) -> Me:
        role = "demo" if ws.demo else ("user" if ws.user else "owner")
        return Me(
            role=role,
            auth_enabled=auth.enabled,
            demo_available=demo is not None,
            internals=not public_mode and role != "user",  # клиентам — без стоимости
            registration=accounts is not None,
            providers={name: p.title for name, p in providers.items()} if accounts else {},
            email=ws.user.email if ws.user else None,
            name=ws.user.name if ws.user else "",
        )

    def set_session(response: Response, payload: str) -> None:
        response.set_cookie(
            COOKIE_NAME,
            auth.issue(payload),
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
        )

    def log_in_user(response: Response, user: User) -> Me:
        set_session(response, user_payload(user.id, user.session_version))
        return me_for(user_workspace(user))

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "?"

    def need_accounts() -> Accounts:
        if accounts is None:
            raise HTTPException(404, "Регистрация на этом сайте выключена")
        return accounts

    mail_attempts = Attempts(5, 3600)  # писем с одного адреса в час — против спама чужим людям

    def send_link(request: Request, user: User, purpose: str) -> None:
        if mail_attempts.is_blocked(client_ip(request)):
            raise HTTPException(429, "Слишком много писем. Попробуйте через час")
        mail_attempts.record(client_ip(request))
        token = need_accounts().issue_token(user, purpose)
        if purpose == "verify":
            link = f"{public_url}/api/auth/verify?token={token}"
            subject = "Подтвердите почту — Работа в точку"
            text = (
                "Здравствуйте!\n\nЧтобы закончить регистрацию в «Работе в точку», "
                "откройте ссылку:\n"
                f"{link}\n\nСсылка действует 48 часов. Если вы не регистрировались — "
                "просто удалите это письмо."
            )
        else:
            link = f"{public_url}/#/reset?token={token}"
            subject = "Сброс пароля — Работа в точку"
            text = (
                "Здравствуйте!\n\nЧтобы задать новый пароль, откройте ссылку:\n"
                f"{link}\n\nСсылка действует 2 часа. Если вы не просили сброс — "
                "ничего делать не нужно, пароль останется прежним."
            )
        try:
            mailer.send(user.email or "", subject, text)
        except Exception as exc:
            log.exception("mail to user %s failed", user.id)
            raise HTTPException(502, "Не удалось отправить письмо — попробуйте позже") from exc

    @app.get("/api/auth/me", response_model=Me)
    def me(ws: WsDep):
        return me_for(ws)

    @app.post("/api/auth/login", response_model=Me)
    def login(body: LoginIn, request: Request, response: Response):
        if not auth.enabled:
            return me_for(owner)
        client = client_ip(request)
        if auth.is_blocked(client):
            raise HTTPException(429, "Слишком много попыток. Подождите 5 минут")
        if body.email.strip():
            user = need_accounts().authenticate(body.email, body.password)
            if user is None:
                auth.record_failure(client)
                raise HTTPException(401, "Неверная почта или пароль")
            auth.reset_failures(client)
            if not user.email_verified:
                send_link(request, user, "verify")
                raise HTTPException(403, "Почта не подтверждена — мы отправили письмо ещё раз")
            return log_in_user(response, user)
        if not auth.check_password(body.password):
            auth.record_failure(client)
            raise HTTPException(401, "Неверный пароль")
        auth.reset_failures(client)
        set_session(response, OWNER)
        return me_for(owner)

    @app.post("/api/auth/logout", status_code=204)
    def logout(response: Response):
        response.delete_cookie(COOKIE_NAME)

    @app.post("/api/auth/register")
    def register(body: RegisterIn, request: Request):
        """Аккаунт создаётся неподтверждённым; войти можно после ссылки из письма."""
        if not body.consent:
            raise HTTPException(400, "Нужно согласие на обработку персональных данных")
        try:
            user = need_accounts().register(body.email, body.password)
        except AccountError as exc:
            raise HTTPException(400, str(exc)) from exc
        send_link(request, user, "verify")
        return {"status": "sent", "email": user.email}

    @app.get("/api/auth/verify")
    def verify_email(token: str):
        try:
            user = need_accounts().verify_email(token)
        except AccountError:
            return RedirectResponse("/#/login?error=link", status_code=303)
        response = RedirectResponse("/#/profile", status_code=303)
        log_in_user(response, user)
        return response

    @app.post("/api/auth/forgot")
    def forgot(body: ForgotIn, request: Request):
        """Ответ одинаковый, есть такая почта или нет — чтобы не выдавать чужие адреса."""
        user = need_accounts().find_by_email(body.email)
        if user is not None:
            send_link(request, user, "reset")
        return {"status": "sent"}

    @app.post("/api/auth/reset", response_model=Me)
    def reset(body: ResetIn, response: Response):
        try:
            user = need_accounts().reset_password(body.token, body.password)
        except AccountError as exc:
            raise HTTPException(400, str(exc)) from exc
        return log_in_user(response, user)

    @app.delete("/api/auth/account", status_code=204)
    def delete_account(ws: WsDep, response: Response):
        """Удалить аккаунт и все данные пользователя: резюме, профиль, отклики."""
        if ws.user is None:
            raise HTTPException(403, "Удалить можно только аккаунт пользователя")
        with users_lock:
            if user_engine := user_engines.pop(ws.user.id, None):
                user_engine.dispose()  # иначе Windows не даст удалить jobs.db
            user_jobs.pop(ws.user.id, None)
        shutil.rmtree(users_dir / str(ws.user.id), ignore_errors=True)
        need_accounts().delete(ws.user.id)
        response.delete_cookie(COOKIE_NAME)

    @app.get("/api/auth/oauth/{provider}/start")
    def oauth_start(provider: str):
        if accounts is None or provider not in providers:
            raise HTTPException(404, "Такой способ входа не подключён")
        state, verifier = new_verifier()[:32], new_verifier()
        redirect_uri = f"{public_url}/api/auth/oauth/{provider}/callback"
        response = RedirectResponse(
            providers[provider].authorize_url(redirect_uri, state, verifier), status_code=303
        )
        # state и verifier — в подписанной cookie на 10 минут: защита от подделки ответа
        response.set_cookie(
            OAUTH_COOKIE,
            auth.issue(f"{provider}~{state}~{verifier}", seconds=600),
            max_age=600,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
        )
        return response

    @app.get("/api/auth/oauth/{provider}/callback")
    def oauth_callback(provider: str, request: Request):
        fail = RedirectResponse("/#/login?error=oauth", status_code=303)
        fail.delete_cookie(OAUTH_COOKIE)
        params = dict(request.query_params)
        saved = auth.read(request.cookies.get(OAUTH_COOKIE)) or ""
        name, _, rest = saved.partition("~")
        state, _, verifier = rest.partition("~")
        if (
            accounts is None
            or provider not in providers
            or name != provider
            or not state
            or params.get("state") != state
            or not params.get("code")
        ):
            return fail
        redirect_uri = f"{public_url}/api/auth/oauth/{provider}/callback"
        try:
            with oauth_client() as client:
                found = providers[provider].fetch_user(
                    client, params["code"], verifier, redirect_uri, params
                )
        except (OAuthError, httpx.HTTPError, KeyError) as exc:
            log.warning("oauth %s failed: %s", provider, exc)
            return fail
        user = accounts.oauth_login(provider, found.subject, found.email, found.name)
        response = RedirectResponse("/#/feed", status_code=303)
        response.delete_cookie(OAUTH_COOKIE)
        log_in_user(response, user)
        return response

    @app.get("/api/limits", response_model=dict[str, Limit])
    def get_limits(ws: WsDep):
        """Сколько платных действий осталось сегодня (только у пользователей)."""
        if ws.user is None or accounts is None:
            return {}
        used = accounts.used_today(ws.user.id)
        return {a: Limit(used=used.get(a, 0), limit=n) for a, n in limits.items()}

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

    @app.post("/api/applications/manual", response_model=ManualApplicationOut)
    def add_manual_application(body: ManualApplicationIn, s: SessionDep, ws: OwnerDep):
        url = body.url.strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        title, company = body.title.strip(), body.company.strip()
        if not url and not title:
            raise HTTPException(400, "Вставьте ссылку на вакансию или укажите название")

        ident = identify(url) if url else None
        vacancy = s.get(Vacancy, ident.id) if ident else None
        fetched = vacancy is not None
        if vacancy is None and url:
            charge(ws, "manual")
            try:
                vacancy = vacancy_fetcher(url)
            except Exception as exc:  # сеть, лимиты Exa — не повод терять отклик
                log.warning("manual: could not fetch %s: %s", url, exc)
            fetched = vacancy is not None
        if vacancy is None:
            if not title:
                raise HTTPException(
                    400, "Не удалось загрузить вакансию по ссылке — укажите название вручную"
                )
            if ident:
                vid, source, ext, vurl = ident.id, ident.source, ident.external_id, ident.url
            else:
                ext = hashlib.sha1(f"{title}|{company}".lower().encode()).hexdigest()[:16]
                vid, source, vurl = f"manual:{ext}", "manual", ""
            vacancy = Vacancy(
                id=vid, source=source, external_id=ext, title=title,
                company=company or None, url=vurl,
            )  # fmt: skip
        if s.get(Vacancy, vacancy.id) is None:
            s.add(vacancy)

        application = s.get(Application, vacancy.id) or Application(vacancy_id=vacancy.id)
        application.stage = body.stage
        application.applied_at = body.applied_at or application.applied_at
        if application.applied_at is None and body.stage in SENT_STAGES:
            application.applied_at = date.today()
        if body.notes.strip():
            application.notes = body.notes.strip()
        application.stage_changed_at = application.updated_at = utcnow()
        s.add(application)
        s.commit()
        s.refresh(application)
        return ManualApplicationOut(
            vacancy_id=vacancy.id,
            title=vacancy.title,
            company=vacancy.company,
            fetched=fetched,
            application=ApplicationOut.model_validate(application, from_attributes=True),
        )

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
        charge(ws, "letter")
        letter = generate_cover_letter(
            profile,
            vacancy,
            s.get(Match, vacancy_id),
            llm_factory(),
            tone=body.tone,
            wishes=body.wishes,
            mention_gaps=body.mention_gaps,
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
        if profile.target_roles or profile.search_skills:  # запросы — по выбранному режиму
            profile.search_queries = profile.effective_queries()
        save_profile(profile, ws.profile_path)
        return profile

    @app.post("/api/profile/careers", response_model=Profile)
    def careers(ws: OwnerDep):
        """Подобрать профессии по навыкам (≈ 0,05 ₽). Результат сохраняется в профиле."""
        profile = current_profile(ws)
        if profile is None:
            raise HTTPException(400, "Сначала создайте профиль")
        charge(ws, "careers")
        try:
            profile.careers = suggest_careers(
                profile.skills,
                profile.extra,
                profile.experience_years,
                profile.industries,
                llm_factory(),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        save_profile(profile, ws.profile_path)
        return profile

    def rebuild_from(ws: Workspace, text: str) -> Profile:
        """Профиль из текста резюме: навыки добавляются, ручные правки и профессии остаются."""
        try:
            profile = rebuild_profile(text, current_profile(ws), llm_factory())
        except ResumeError as exc:
            raise HTTPException(400, str(exc)) from exc
        save_profile(profile, ws.profile_path)
        return profile

    @app.post("/api/profile/rebuild", response_model=Profile)
    def rebuild(ws: OwnerDep):
        text = ResumeStore(ws.resume_path).text()
        if not text:
            raise HTTPException(
                400, "Резюме ещё нет: загрузите файл, дайте ссылку или заполните анкету"
            )
        charge(ws, "resume")
        return rebuild_from(ws, text)

    @app.get("/api/resume", response_model=ResumeOut)
    def resume_info(ws: WsDep):
        store = ResumeStore(ws.resume_path)
        return ResumeOut(source=store.source(), form=store.form())

    @app.post("/api/resume/file", response_model=ResumeResult)
    async def upload_resume(request: Request, filename: str, ws: OwnerDep):
        """Файл резюме — телом запроса (без multipart): PDF, DOCX, ODT, RTF, TXT."""
        data = await request.body()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Файл больше 10 МБ — резюме обычно намного меньше")
        try:
            text = extract_text(data, filename)
        except ResumeError as exc:
            raise HTTPException(400, str(exc)) from exc
        charge(ws, "resume")
        profile = rebuild_from(ws, text)
        source = ResumeStore(ws.resume_path).save_text(text, "file", Path(filename).name)
        return ResumeResult(profile=profile, source=source)

    @app.post("/api/resume/link", response_model=ResumeResult)
    def resume_by_link(body: ResumeLinkIn, ws: OwnerDep):
        charge(ws, "resume")
        try:
            text = resume_fetcher(body.url)
        except ResumeError as exc:
            raise HTTPException(400, str(exc)) from exc
        profile = rebuild_from(ws, text)
        source = ResumeStore(ws.resume_path).save_text(text, "link", body.url.strip())
        return ResumeResult(profile=profile, source=source)

    @app.put("/api/resume/form", response_model=ResumeOut)
    def save_resume_form(form: ResumeForm, ws: OwnerDep):
        store = ResumeStore(ws.resume_path)
        store.save_form(form)
        return ResumeOut(source=store.source(), form=form)

    @app.post("/api/resume/form/build", response_model=ResumeResult)
    def build_from_form(form: ResumeForm, ws: OwnerDep):
        """Сохранить анкету и собрать по ней профиль; анкета становится текущим резюме."""
        text = form.to_text()
        if len(text) < 80:
            raise HTTPException(400, "Анкета почти пустая: добавьте опыт работы и навыки")
        store = ResumeStore(ws.resume_path)
        store.save_form(form)
        charge(ws, "resume")
        profile = rebuild_from(ws, text)
        return ResumeResult(profile=profile, source=store.save_text(text, "form", "Анкета"))

    @app.post("/api/resume/form/prefill", response_model=ResumeForm)
    def prefill_form(ws: OwnerDep):
        """Разложить текущее резюме по полям анкеты (≈ 0,1 ₽), чтобы не заполнять с нуля."""
        text = ResumeStore(ws.resume_path).text()
        if not text:
            raise HTTPException(400, "Резюме ещё нет — заполните анкету вручную")
        charge(ws, "resume")
        return form_from_text(text, llm_factory())

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
        charge(ws, "advice")
        advice = generate_advice(
            profile, compute_analytics(s, profile.fingerprint()), llm_factory()
        )
        save_advice(advice, advice_path(ws))
        return advice

    def sources_available() -> dict[str, bool]:
        if available_sources is not None:
            return available_sources()
        settings = get_settings()
        return {
            "exa": bool(settings.exa_api_key),
            "trudvsem": True,  # открытый API без ключа
            "superjob": bool(settings.superjob_api_key),
        }

    @app.get("/api/sources")
    def sources():
        """Какие источники можно включить в «Найти вакансии» (у части нужен ключ в .env)."""
        return sources_available()

    @app.get("/api/refresh")
    def refresh_status(request: Request, ws: WsDep):
        if ws.demo:
            return RefreshState().to_dict()  # журнал владельца гостям не показываем
        state = refresh_job(request, ws).state.to_dict()
        if public_mode or ws.user:
            state["cost_dollars"] = 0  # стоимость — внутренняя кухня, клиентам не показываем
        return state

    @app.post("/api/refresh", status_code=202)
    def refresh(body: RefreshIn, request: Request, ws: OwnerDep):
        unknown = set(body.sources) - set(COLLECTORS)
        if unknown:  # пустой список допустим — только пересчитать оценки, без сбора
            raise HTTPException(400, f"Неизвестные источники: {', '.join(unknown)}")
        missing = [src for src in body.sources if not sources_available().get(src, False)]
        if missing:
            raise HTTPException(400, f"Для источника {', '.join(missing)} нет ключа в .env")
        if current_profile(ws) is None:
            raise HTTPException(400, "Сначала создайте профиль")
        job = refresh_job(request, ws)
        if job.state.running:
            raise HTTPException(409, "Обновление уже идёт")
        if ws.user and sum(j.state.running for j in user_jobs.values()) >= max_parallel_searches:
            raise HTTPException(409, "Сейчас идёт много поисков — попробуйте через пару минут")
        charge(ws, "refresh")
        if not job.start(body.sources):
            raise HTTPException(409, "Обновление уже идёт")
        state = job.state.to_dict()
        if public_mode or ws.user:
            state["cost_dollars"] = 0  # стоимость — внутренняя кухня, клиентам не показываем
        return state

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
    accounts = None
    if auth.enabled and settings.registration_enabled:
        accounts = Accounts(
            create_engine(
                f"sqlite:///{(DATA_DIR / 'accounts.db').as_posix()}",
                connect_args={"check_same_thread": False},
            )
        )
    providers: dict[str, Provider] = {}
    if settings.yandex_client_id:
        providers["yandex"] = Yandex(settings.yandex_client_id, settings.yandex_client_secret)
    if settings.vk_client_id:
        providers["vk"] = VK(settings.vk_client_id)
    mailer: Mailer = LogMailer()
    if settings.smtp_host:
        mailer = SmtpMailer(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
        )
    return create_app(
        auth=auth,
        demo_engine=demo_engine,
        demo_profile_path=DATA_DIR / "demo_profile.json",
        demo_reset_hours=settings.demo_reset_hours,
        cookie_secure=settings.cookie_secure,
        public_mode=settings.public_mode,
        accounts=accounts,
        mailer=mailer,
        providers=providers,
        public_url=settings.public_url,
        limits=settings.limits(),
        max_parallel_searches=settings.max_parallel_searches,
    )


app = create_app_from_settings()
