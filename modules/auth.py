import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request

from modules.operations import audit
from shared.config import settings
from shared.db import pool
from shared.errors import DomainError

hasher = PasswordHasher()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def seed_local():
    if settings.environment != "local":
        return
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO trade.users(id,email,role,password_hash) VALUES ('local-admin','admin','SUPERUSER',%s) ON CONFLICT DO NOTHING",
            (hasher.hash("admin"),),
        )


def login(email, password):
    if settings.environment == "deployed":
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise DomainError("Production authentication is not configured", "CONFIGURATION", 503)
        try:
            response = httpx.post(
                settings.supabase_url + "/auth/v1/token?grant_type=password",
                headers={"apikey": settings.supabase_anon_key},
                json={"email": email, "password": password},
                timeout=15,
            )
            if response.status_code != 200:
                raise DomainError("Invalid credentials or unavailable account", "AUTH", 401)
            data = response.json()
            user = resolve_supabase(data["access_token"])
            return {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_in": data["expires_in"],
                "user": user,
            }
        except httpx.HTTPError:
            raise DomainError("Authentication service unavailable", "AUTH", 503) from None
    with pool.connection() as conn:
        user = conn.execute("SELECT * FROM trade.users WHERE email=%s", (email,)).fetchone()
        try:
            valid = (
                user and user["password_hash"] and hasher.verify(user["password_hash"], password)
            )
        except VerifyMismatchError:
            valid = False
        if not valid:
            audit(conn, "anonymous", "LOGIN", outcome="DENIED")
        else:
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO trade.sessions VALUES (%s,%s,%s)",
                (digest(token), user["id"], datetime.now(timezone.utc) + timedelta(hours=8)),
            )
            audit(conn, user["id"], "LOGIN")
            return {"access_token": token, "expires_in": 28800, "user": public_user(user)}
    raise DomainError("Invalid credentials", "AUTH", 401)


def public_user(user):
    return {key: user[key] for key in ("id", "email", "role")}


def resolve_supabase(token):
    try:
        response = httpx.get(
            settings.supabase_url + "/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if response.status_code != 200:
            raise DomainError("Session expired; sign in again", "AUTH", 401)
        identity = response.json()
    except httpx.HTTPError:
        raise DomainError("Authentication service unavailable", "AUTH", 503) from None
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO trade.users(id,email,role) VALUES (%s,%s,'USER') ON CONFLICT(id) DO UPDATE SET email=excluded.email",
            (identity["id"], identity["email"]),
        )
        return public_user(
            conn.execute("SELECT * FROM trade.users WHERE id=%s", (identity["id"],)).fetchone()
        )


def current_user(request: Request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token:
        raise DomainError("Sign in to continue", "AUTH", 401)
    if settings.environment == "deployed":
        return resolve_supabase(token)
    with pool.connection() as conn:
        user = conn.execute(
            "SELECT u.* FROM trade.sessions s JOIN trade.users u ON s.user_id=u.id WHERE s.token_hash=%s AND s.expires_at>now()",
            (digest(token),),
        ).fetchone()
        if not user:
            raise DomainError("Session expired; sign in again", "AUTH", 401)
        return public_user(user)


def require_admin(user):
    if user["role"] not in ("ADMIN", "SUPERUSER"):
        raise DomainError("Administrator role required", "FORBIDDEN", 403)


def authorize_owner(user, owner_id):
    if user["role"] == "USER" and user["id"] != owner_id:
        raise DomainError("You do not own this resource", "FORBIDDEN", 403)


def forgot_password(email):
    if settings.environment == "deployed":
        try:
            response = httpx.post(
                settings.supabase_url + "/auth/v1/recover",
                headers={"apikey": settings.supabase_anon_key},
                json={"email": email, "redirect_to": settings.app_url},
                timeout=15,
            )
            if response.status_code >= 500:
                raise DomainError("Password recovery service unavailable", "AUTH", 503)
        except httpx.HTTPError:
            raise DomainError("Password recovery service unavailable", "AUTH", 503) from None
        return {"message": "If the account exists, a recovery email has been requested."}
    token = secrets.token_urlsafe(32)
    with pool.connection() as conn:
        user = conn.execute("SELECT id FROM trade.users WHERE email=%s", (email,)).fetchone()
        if user:
            conn.execute(
                "INSERT INTO trade.reset_tokens VALUES (%s,%s,%s,false)",
                (digest(token), user["id"], datetime.now(timezone.utc) + timedelta(minutes=15)),
            )
            audit(conn, user["id"], "PASSWORD_RECOVERY")
    return {"message": "Local development recovery token (15 minutes).", "local_reset_token": token}


def reset_local(token, password):
    with pool.connection() as conn:
        reset = conn.execute(
            "SELECT * FROM trade.reset_tokens WHERE token_hash=%s AND NOT used AND expires_at>now() FOR UPDATE",
            (digest(token),),
        ).fetchone()
        if not reset:
            raise DomainError("Invalid or expired recovery token", "AUTH", 400)
        conn.execute(
            "UPDATE trade.users SET password_hash=%s WHERE id=%s",
            (hasher.hash(password), reset["user_id"]),
        )
        conn.execute(
            "UPDATE trade.reset_tokens SET used=true WHERE token_hash=%s", (digest(token),)
        )
        conn.execute("DELETE FROM trade.sessions WHERE user_id=%s", (reset["user_id"],))
        audit(conn, reset["user_id"], "PASSWORD_RESET")


def create_local_user(conn, email, password, role):
    if settings.environment != "local":
        raise DomainError("Create deployed users through Supabase Auth", "CONFIGURATION")
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO trade.users VALUES (%s,%s,%s,%s,now())",
        (user_id, email, role, hasher.hash(password)),
    )
    return user_id
