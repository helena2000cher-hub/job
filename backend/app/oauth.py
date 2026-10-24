"""Sign-in with Yandex ID and VK ID: OAuth 2.0 authorization code flow with PKCE.

Yandex ID: https://yandex.ru/dev/id/doc/ru/ — oauth.yandex.ru/authorize → /token →
login.yandex.ru/info.
VK ID: https://id.vk.ru/about/business/go/docs/ — id.vk.ru/authorize → /oauth2/auth (с device_id из
callback) → /oauth2/user_info. Endpoints follow the official @vkid/sdk.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

TIMEOUT = 15


class OAuthError(Exception):
    pass


@dataclass(frozen=True)
class OAuthUser:
    subject: str
    email: str | None
    name: str


def new_verifier() -> str:
    return secrets.token_urlsafe(48)


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise OAuthError(f"HTTP {response.status_code}: ответ не JSON") from exc
    if response.is_error or "error" in data:
        raise OAuthError(str(data.get("error_description") or data.get("error") or data))
    return data


class Yandex:
    name = "yandex"
    title = "Яндекс ID"

    def __init__(self, client_id: str, client_secret: str = "") -> None:
        self.client_id, self.client_secret = client_id, client_secret

    def authorize_url(self, redirect_uri: str, state: str, verifier: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "login:email login:info",
            "state": state,
            "code_challenge": challenge(verifier),
            "code_challenge_method": "S256",
        }
        return "https://oauth.yandex.ru/authorize?" + urlencode(params)

    def fetch_user(
        self, client: httpx.Client, code: str, verifier: str, redirect_uri: str, params: dict
    ) -> OAuthUser:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "code_verifier": verifier,
        }
        if self.client_secret:
            form["client_secret"] = self.client_secret
        token = _json(client.post("https://oauth.yandex.ru/token", data=form))["access_token"]
        info = _json(
            client.get(
                "https://login.yandex.ru/info",
                params={"format": "json"},
                headers={"Authorization": f"OAuth {token}"},
            )
        )
        name = info.get("real_name") or info.get("display_name") or info.get("login") or ""
        return OAuthUser(subject=str(info["id"]), email=info.get("default_email"), name=name)


class VK:
    name = "vk"
    title = "VK ID"
    base = "https://id.vk.ru"

    def __init__(self, client_id: str) -> None:
        self.client_id = client_id

    def authorize_url(self, redirect_uri: str, state: str, verifier: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "email",
            "state": state,
            "code_challenge": challenge(verifier),
            "code_challenge_method": "s256",
        }
        return f"{self.base}/authorize?" + urlencode(params)

    def fetch_user(
        self, client: httpx.Client, code: str, verifier: str, redirect_uri: str, params: dict
    ) -> OAuthUser:
        device_id = params.get("device_id")
        if not device_id:
            raise OAuthError("VK ID не передал device_id")
        token = _json(
            client.post(
                f"{self.base}/oauth2/auth",
                params={
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": verifier,
                    "state": params.get("state", ""),
                    "device_id": device_id,
                },
                data={"code": code},
            )
        )["access_token"]
        user = _json(
            client.post(
                f"{self.base}/oauth2/user_info",
                params={"client_id": self.client_id},
                data={"access_token": token},
            )
        )["user"]
        name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
        return OAuthUser(subject=str(user["user_id"]), email=user.get("email") or None, name=name)


Provider = Yandex | VK


def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)
