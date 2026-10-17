"""
Auth endpoints — register, login, refresh, me.

POST /api/v1/auth/register  → create account
POST /api/v1/auth/login     → get JWT tokens
POST /api/v1/auth/refresh   → refresh access token
GET  /api/v1/auth/me        → current user info
"""
import logging
from pydantic import BaseModel, EmailStr, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.core.limits import plan_limit, stories_this_month
from app.models.db import User

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    plan: str
    stories_this_month: int
    plan_limit: int  # 0 = unlimited
    total_tokens_used: int
    created_at: str

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201, summary="Create account")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user with email and password."""
    # Check if email already taken
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=req.email,
        name=req.name,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("User registered: %s", req.email)

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse, summary="Login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email and password, receive JWT tokens."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse, summary="Refresh token")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for new access + refresh tokens."""
    from jose import JWTError

    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    import uuid
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", summary="Current user info")
async def me(user: User = Depends(get_current_user)):
    """Return the authenticated user's profile.

    `stories_this_month` is 0 once a new calendar month (UTC) has started, even
    before the stored counter is reset by the next generation. `plan_limit` 0 = unlimited.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "plan": user.plan.value,
        "stories_this_month": stories_this_month(user),
        "plan_limit": plan_limit(user.plan),
        "total_tokens_used": user.total_tokens_used,
        "created_at": user.created_at.isoformat(),
    }
