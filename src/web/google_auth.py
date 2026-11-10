"""Google sign-in for the JSON API: the web (danielalonso.dev/cazachollos) sends the Google ID token as a Bearer.

Same checks as Mea culpa: signature with Google's public keys, `aud` == GOOGLE_CLIENT_ID, issuer, expiry and a
verified email. People are identified by a hash of `sub`; the `sub` itself is never stored.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass(frozen=True)
class GoogleUser:
    id: str  # sha256 of the Google sub
    email: str | None
    name: str | None


Verifier = Callable[[str], dict[str, Any]]


def user_id(sub: str) -> str:
    return hashlib.sha256(f"cazachollos:{sub}".encode()).hexdigest()


class _CachingRequest:
    """google-auth transport that keeps Google's certificates for an hour instead of downloading them every time."""

    def __init__(self) -> None:
        from google.auth.transport.requests import Request as GoogleRequest

        self._inner = GoogleRequest()
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def __call__(self, url: str, method: str = "GET", **kwargs: Any) -> Any:
        if method == "GET":
            with self._lock:
                hit = self._cache.get(url)
            if hit and time.monotonic() - hit[0] < 3600:
                return hit[1]
        response = self._inner(url, method=method, **kwargs)
        if method == "GET" and getattr(response, "status", 0) == 200:
            with self._lock:
                self._cache[url] = (time.monotonic(), response)
        return response


def google_verifier(client_id: str) -> Verifier:
    from google.oauth2 import id_token

    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is required")
    transport = _CachingRequest()

    def verify(token: str) -> dict[str, Any]:
        return id_token.verify_oauth2_token(token, transport, audience=client_id, clock_skew_in_seconds=10)

    return verify


def validate_claims(claims: dict[str, Any], client_id: str) -> GoogleUser:
    if claims.get("aud") != client_id:
        raise ValueError("aud")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("iss")
    if float(claims.get("exp", 0)) < time.time() - 10:
        raise ValueError("exp")
    if claims.get("email_verified") is not True:
        raise ValueError("email not verified")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise ValueError("sub")
    email = claims.get("email")
    name = claims.get("given_name") or claims.get("name")
    return GoogleUser(
        id=user_id(sub),
        email=email.strip().lower()[:320] if isinstance(email, str) else None,
        name=str(name)[:60] if name else None,
    )


def user_dependency(verifier: Verifier, client_id: str) -> Callable[[Request], GoogleUser]:
    def current_user(request: Request) -> GoogleUser:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip() or len(token) > 4096:
            raise HTTPException(401, "Inicia sesión con Google")
        try:
            return validate_claims(verifier(token.strip()), client_id)
        except Exception as exc:  # noqa: BLE001 - any verification failure is a 401
            raise HTTPException(401, "Sesión no válida o caducada") from exc

    return current_user
