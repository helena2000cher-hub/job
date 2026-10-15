"""Single-owner password login with a signed, HttpOnly session cookie.

No user table: the site has one owner (password from .env); everyone else sees the demo.
"""

import hashlib
import hmac
import time
from collections import defaultdict, deque

COOKIE_NAME = "jm_session"
SESSION_DAYS = 30
MAX_ATTEMPTS = 5  # неудачных входов
ATTEMPT_WINDOW = 300  # секунд


class Auth:
    def __init__(self, password: str, secret: str) -> None:
        if password and len(secret) < 32:
            raise ValueError("SESSION_SECRET должен быть не короче 32 символов")
        self.enabled = bool(password)
        self._password = password.encode()
        self._secret = secret.encode()
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    # --- пароль -----------------------------------------------------------------------------

    def check_password(self, password: str) -> bool:
        return hmac.compare_digest(password.encode(), self._password)

    def is_blocked(self, client: str) -> bool:
        attempts = self._failures[client]
        while attempts and attempts[0] < time.time() - ATTEMPT_WINDOW:
            attempts.popleft()
        return len(attempts) >= MAX_ATTEMPTS

    def record_failure(self, client: str) -> None:
        self._failures[client].append(time.time())

    def reset_failures(self, client: str) -> None:
        self._failures.pop(client, None)

    # --- cookie: "<expires>.<hmac>" ---------------------------------------------------------

    def issue(self) -> str:
        expires = str(int(time.time()) + SESSION_DAYS * 86400)
        return f"{expires}.{self._sign(expires)}"

    def verify(self, token: str | None) -> bool:
        if not self.enabled:
            return True  # вход выключен — все владельцы (локальный запуск)
        if not token or "." not in token:
            return False
        expires, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, self._sign(expires)):
            return False
        return expires.isdigit() and int(expires) > time.time()

    def _sign(self, value: str) -> str:
        # Пароль входит в ключ: смена пароля разлогинивает все старые сессии.
        key = self._secret + b"|" + hashlib.sha256(self._password).digest()
        return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
