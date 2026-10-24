"""User accounts: email + password or Yandex ID / VK ID. Stored in their own database.

Accounts live in data/accounts.db; each user's job search (vacancies, profile, resume) lives in
its own folder data/users/<id>/ — see the user Workspace in app/api/main.py.
"""

import hashlib
import hmac
import re
import secrets
import time
from datetime import date

from sqlalchemy.engine import Engine
from sqlalchemy.orm import registry
from sqlmodel import Field, Session, SQLModel, select

MIN_PASSWORD = 8
VERIFY_HOURS = 48
RESET_HOURS = 2
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(ValueError):
    """Message is shown to the user as is."""


class AccountsBase(SQLModel, registry=registry()):
    """Own metadata: account tables must not appear in every workspace database."""


class User(AccountsBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str | None = Field(default=None, unique=True, index=True)  # в нижнем регистре
    email_verified: bool = False
    password_hash: str = ""  # пусто — входит только через Яндекс/VK
    name: str = ""
    session_version: int = 0  # +1 при смене пароля: старые cookie перестают работать
    created_at: int = Field(default_factory=lambda: int(time.time()))


class OAuthIdentity(AccountsBase, table=True):
    provider: str = Field(primary_key=True)  # yandex | vk
    subject: str = Field(primary_key=True)  # id пользователя у провайдера
    user_id: int = Field(index=True)


class EmailToken(AccountsBase, table=True):
    token_hash: str = Field(primary_key=True)  # сам токен не храним — только хеш
    user_id: int = Field(index=True)
    purpose: str  # verify | reset
    expires_at: int


class Usage(AccountsBase, table=True):
    """Paid actions per user per day — for the daily limits."""

    user_id: int = Field(primary_key=True)
    day: date = Field(primary_key=True)
    action: str = Field(primary_key=True)
    count: int = 0


# --- пароли: scrypt из стандартной библиотеки -----------------------------------------------------

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    actual = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p)
    )
    return hmac.compare_digest(actual.hex(), digest)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL.match(email) or len(email) > 254:
        raise AccountError("Проверьте адрес почты")
    return email


def _check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AccountError(f"Пароль — не короче {MIN_PASSWORD} символов")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        AccountsBase.metadata.create_all(engine)

    def _session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)

    def get(self, user_id: int) -> User | None:
        with self._session() as s:
            return s.get(User, user_id)

    def find_by_email(self, email: str) -> User | None:
        with self._session() as s:
            return s.exec(select(User).where(User.email == email.strip().lower())).first()

    # --- почта и пароль -------------------------------------------------------------------------

    def register(self, email: str, password: str) -> User:
        """New unverified account. An unverified one with the same email is taken over."""
        email = normalize_email(email)
        _check_new_password(password)
        with self._session() as s:
            user = s.exec(select(User).where(User.email == email)).first()
            if user and user.email_verified:
                raise AccountError("Эта почта уже зарегистрирована — войдите или сбросьте пароль")
            user = user or User(email=email)
            user.password_hash = hash_password(password)
            s.add(user)
            s.commit()
            return user

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.find_by_email(email)
        if user is None or not user.password_hash:
            hash_password(password)  # то же время ответа, что и при неверном пароле
            return None
        return user if check_password(password, user.password_hash) else None

    def issue_token(self, user: User, purpose: str) -> str:
        token = secrets.token_urlsafe(32)
        hours = VERIFY_HOURS if purpose == "verify" else RESET_HOURS
        with self._session() as s:
            s.add(
                EmailToken(
                    token_hash=_token_hash(token),
                    user_id=user.id,
                    purpose=purpose,
                    expires_at=int(time.time()) + hours * 3600,
                )
            )
            s.commit()
        return token

    def _consume(self, s: Session, token: str, purpose: str, once: bool = True) -> User:
        row = s.get(EmailToken, _token_hash(token))
        if row is None or row.purpose != purpose or row.expires_at < time.time():
            raise AccountError("Ссылка устарела или уже использована — запросите новую")
        if once:
            s.delete(row)
        user = s.get(User, row.user_id)
        if user is None:
            raise AccountError("Аккаунт не найден")
        return user

    def verify_email(self, token: str) -> User:
        with self._session() as s:
            # Ссылка многоразовая до срока: почтовики сами открывают ссылки из писем при проверке,
            # и одноразовая сгорела бы раньше, чем человек на неё нажмёт.
            user = self._consume(s, token, "verify", once=False)
            user.email_verified = True
            s.add(user)
            s.commit()
            return user

    def reset_password(self, token: str, password: str) -> User:
        _check_new_password(password)
        with self._session() as s:
            user = self._consume(s, token, "reset")
            user.password_hash = hash_password(password)
            user.email_verified = True  # ссылка пришла на эту почту — значит, она настоящая
            user.session_version += 1
            s.add(user)
            s.commit()
            return user

    # --- Яндекс ID и VK ID ----------------------------------------------------------------------

    def oauth_login(self, provider: str, subject: str, email: str | None, name: str) -> User:
        """Find the user by provider id; else link by (verified) email; else create one."""
        email = email.strip().lower() if email else None
        with self._session() as s:
            identity = s.get(OAuthIdentity, (provider, subject))
            if identity and (user := s.get(User, identity.user_id)):
                return user
            user = s.exec(select(User).where(User.email == email)).first() if email else None
            if user is None:
                user = User(email=email, email_verified=email is not None, name=name)
            elif not user.email_verified:
                # Кто-то начал регистрацию на эту почту, но не подтвердил — пароль сбрасываем:
                # почту подтвердил провайдер, и аккаунт теперь принадлежит её владельцу.
                user.email_verified, user.password_hash = True, ""
                user.session_version += 1
            user.name = user.name or name
            s.add(user)
            s.flush()
            s.add(OAuthIdentity(provider=provider, subject=subject, user_id=user.id))
            s.commit()
            return user

    # --- удаление и лимиты ----------------------------------------------------------------------

    def delete(self, user_id: int) -> None:
        with self._session() as s:
            for model in (OAuthIdentity, EmailToken, Usage):
                for row in s.exec(select(model).where(model.user_id == user_id)):
                    s.delete(row)
            if user := s.get(User, user_id):
                s.delete(user)
            s.commit()

    def use(self, user_id: int, action: str, limit: int) -> bool:
        """Count one paid action; False if today's limit is already reached."""
        with self._session() as s:
            key = (user_id, date.today(), action)
            row = s.get(Usage, key) or Usage(user_id=user_id, day=key[1], action=action)
            if row.count >= limit:
                return False
            row.count += 1
            s.add(row)
            s.commit()
            return True

    def used_today(self, user_id: int) -> dict[str, int]:
        with self._session() as s:
            rows = s.exec(select(Usage).where(Usage.user_id == user_id, Usage.day == date.today()))
            return {row.action: row.count for row in rows}
