"""Password hashing, signed session cookies, login lockout, and the auth
dependency used to gate every protected route (and Traefik ForwardAuth)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings
from .db import cursor

_ph = PasswordHasher()
_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="kb-session")


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def set_session(resp: Response, user_id: int) -> None:
    token = _serializer.dumps({"uid": user_id})
    resp.set_cookie(
        settings.COOKIE_NAME, token,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True, secure=settings.COOKIE_SECURE, samesite="strict",
        path="/",
    )


def clear_session(resp: Response) -> None:
    resp.delete_cookie(settings.COOKIE_NAME, path="/")


def _read_session(request: Request) -> int | None:
    tok = request.cookies.get(settings.COOKIE_NAME)
    if not tok:
        return None
    try:
        data = _serializer.loads(tok, max_age=settings.SESSION_MAX_AGE)
        return int(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None


def current_user(request: Request) -> int:
    """FastAPI dependency: 401 unless a valid session cookie is present."""
    uid = _read_session(request)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return uid


def authenticate(email: str, password: str) -> int:
    """Verify credentials with lockout. Returns user_id or raises 401/429."""
    with cursor() as cur:
        cur.execute(
            "SELECT id, password_hash, failed_attempts, locked_until "
            "FROM users WHERE email = %s", (email.lower(),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        uid, pw_hash, failed, locked_until = row

        if locked_until and locked_until > _now():
            raise HTTPException(status_code=429, detail="Account temporarily locked")

        try:
            _ph.verify(pw_hash, password)
        except VerifyMismatchError:
            failed += 1
            lock = (_now() + timedelta(minutes=settings.LOCKOUT_MINUTES)
                    if failed >= settings.MAX_FAILED_ATTEMPTS else None)
            cur.execute(
                "UPDATE users SET failed_attempts=%s, locked_until=%s WHERE id=%s",
                (failed, lock, uid))
            raise HTTPException(status_code=401, detail="Invalid credentials")

        cur.execute(
            "UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=%s",
            (uid,))
        return uid
