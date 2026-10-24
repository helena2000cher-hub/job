"""Signed, HttpOnly session cookies for the owner and registered users.

The owner logs in with the password from .env; users — with email + password or Yandex ID / VK ID
(app/accounts.py). Guests see the demo.
"""

import hashlib
import hmac
import time
from collections import defaultdict, deque

COOKIE_NAME = "jm_session"
OAUTH_COOKIE = "jm_oauth"  # state и PKCE-ключ на время входа через Яндекс/VK
SESSION_DAYS = 30
MAX_ATTEMPTS = 5  # неудачных входов
ATTEMPT_WINDOW = 300  # секунд
OWNER = "owner"


class Attempts:
    """Sliding-window counter per client (IP): brute force and mail spam protection."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def is_blocked(self, client: str) -> bool:
        hits = self._hits[client]
        while hits and hits[0] < time.time() - self.window:
            hits.popleft()
        return len(hits) >= self.limit

    def record(self, client: str) -> None:
        self._hits[client].append(time.time())

    def reset(self, client: str) -> None:
        self._hits.pop(client, None)


class Auth:
    def __init__(self, password: str, secret: str) -> None:
        if password and len(secret) < 32:
            raise ValueError("SESSION_SECRET должен быть не короче 32 символов")
        self.enabled = bool(password)
        self._password = password.encode()
        self._secret = secret.encode()
        self._failures = Attempts(MAX_ATTEMPTS, ATTEMPT_WINDOW)

    # --- пароль владельца -----------------------------------------------------------------------

    def check_password(self, password: str) -> bool:
        return hmac.compare_digest(password.encode(), self._password)

    def is_blocked(self, client: str) -> bool:
        return self._failures.is_blocked(client)

    def record_failure(self, client: str) -> None:
        self._failures.record(client)

    def reset_failures(self, client: str) -> None:
        self._failures.reset(client)

    # --- cookie: "<expires>.<payload>.<hmac>" ---------------------------------------------------

    def issue(self, payload: str = OWNER, seconds: int = SESSION_DAYS * 86400) -> str:
        """payload: "owner", "u<id>v<session_version>" or OAuth state — without dots."""
        expires = str(int(time.time()) + seconds)
        return f"{expires}.{payload}.{self._sign(f'{expires}.{payload}', payload)}"

    def read(self, token: str | None) -> str | None:
        """Payload of a valid, unexpired token; None for a forged or old one."""
        if not token or token.count(".") != 2:
            return None
        expires, payload, signature = token.split(".")
        if not hmac.compare_digest(signature, self._sign(f"{expires}.{payload}", payload)):
            return None
        return payload if expires.isdigit() and int(expires) > time.time() else None

    def verify(self, token: str | None) -> bool:
        """Owner session? With login switched off everyone is the owner (local run)."""
        return not self.enabled or self.read(token) == OWNER

    def _sign(self, value: str, payload: str) -> str:
        key = self._secret
        if payload == OWNER:  # пароль входит в ключ: его смена разлогинивает старые сессии
            key += b"|" + hashlib.sha256(self._password).digest()
        return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def user_payload(user_id: int, session_version: int) -> str:
    return f"u{user_id}v{session_version}"


def parse_user_payload(payload: str | None) -> tuple[int, int] | None:
    if not payload or not payload.startswith("u") or "v" not in payload:
        return None
    user_id, _, version = payload[1:].partition("v")
    if not (user_id.isdigit() and version.isdigit()):
        return None
    return int(user_id), int(version)
