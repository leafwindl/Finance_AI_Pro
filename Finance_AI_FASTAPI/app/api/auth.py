from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid
from typing import Annotated

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.core.config import Settings, get_settings
from app.data_gateway.pool import get_pool

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _session_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _create_session(
    response: Response,
    *,
    pool,
    settings: Settings,
    user_id: str,
) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.session_ttl_seconds
    )
    await pool.execute(
        """
        INSERT INTO user_sessions (session_id, user_id, expires_at)
        VALUES ($1, $2, $3)
        """,
        _session_digest(token),
        user_id,
        expires_at,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> dict:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    row = await pool.fetchrow(
        """
        SELECT u.user_id, u.name, u.email
        FROM user_sessions s
        JOIN users u ON u.user_id=s.user_id
        WHERE s.session_id=$1
          AND s.revoked_at IS NULL
          AND s.expires_at > NOW()
        """,
        _session_digest(token),
    )
    if row is None:
        raise HTTPException(status_code=401, detail="登录已过期")
    await pool.execute(
        "UPDATE user_sessions SET last_seen_at=NOW() WHERE session_id=$1",
        _session_digest(token),
    )
    return dict(row)


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> dict:
    name = payload.name.strip()
    email = str(payload.email).strip().lower()
    hashed = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    user_id = uuid.uuid4().hex[:16]
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    "SELECT user_id FROM users WHERE name=$1 OR email=$2",
                    name,
                    email,
                )
                if existing:
                    raise HTTPException(
                        status_code=409, detail="用户名或邮箱已被注册"
                    )

                await connection.execute(
                    """
                    INSERT INTO users (user_id, name, email, password)
                    VALUES ($1,$2,$3,$4)
                    """,
                    user_id,
                    name,
                    email,
                    hashed,
                )
                await _create_session(
                    response,
                    pool=connection,
                    settings=settings,
                    user_id=user_id,
                )
    except asyncpg.UniqueViolationError as exc:
        # 预检查与 INSERT 之间仍可能发生并发注册，由数据库约束兜底。
        raise HTTPException(
            status_code=409, detail="用户名或邮箱已被注册"
        ) from exc
    return {"user": {"user_id": user_id, "name": name, "email": email}}


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> dict:
    row = await pool.fetchrow(
        "SELECT user_id, name, email, password FROM users WHERE name=$1",
        payload.name.strip(),
    )
    if row is None or not bcrypt.checkpw(
        payload.password.encode(), row["password"].encode()
    ):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    await _create_session(
        response, pool=pool, settings=settings, user_id=row["user_id"]
    )
    return {
        "user": {
            "user_id": row["user_id"],
            "name": row["name"],
            "email": row["email"],
        }
    }


@router.get("/me")
async def me(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    return user


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    pool=Depends(get_pool),
) -> dict:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await pool.execute(
            "UPDATE user_sessions SET revoked_at=NOW() WHERE session_id=$1",
            _session_digest(token),
        )
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}
