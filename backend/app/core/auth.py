"""
JWT authentication — simple email/password for dev, swappable for Auth0 in prod.

Usage in endpoints:
    from app.core.auth import get_current_user, get_optional_user

    @router.get("/protected")
    async def protected(user: User = Depends(get_current_user)):
        ...

    @router.get("/optional")
    async def optional(user: User | None = Depends(get_optional_user)):
        ...
"""
import uuid
import logging
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.db import User

logger = logging.getLogger(__name__)

# ── Password hashing (bcrypt directly — passlib is broken with bcrypt>=5) ───

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT tokens ───────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a longer-lived refresh token."""
    expire = datetime.utcnow() + timedelta(days=30)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ── FastAPI dependencies ─────────────────────────────────────────────────────

async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Require authenticated user. In dev mode (DEBUG=True or no JWT_SECRET changed),
    falls back to the seeded dev user so the app works without login.
    """
    # Dev mode fallback: if no token and using default secret, return dev user
    if token is None:
        if settings.JWT_SECRET_KEY == "changeme-in-production":
            user = await db.get(User, DEV_USER_ID)
            if user:
                return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_optional_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Same as get_current_user but returns None instead of 401."""
    if token is None:
        if settings.JWT_SECRET_KEY == "changeme-in-production":
            return await db.get(User, DEV_USER_ID)
        return None

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        return None

    return await db.get(User, user_id)
