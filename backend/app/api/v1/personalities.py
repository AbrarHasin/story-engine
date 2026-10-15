"""CRUD for Personalities (named presets: voice, tone, reading level, banned words)."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.db import Personality, User
from app.models.schemas import PersonalityCreate, PersonalityUpdate, PersonalityResponse

router = APIRouter(prefix="/personalities", tags=["Personalities"])


async def _get_owned(db: AsyncSession, pid: uuid.UUID, user: User) -> Personality | None:
    """Return the personality only if it belongs to `user`; callers 404 on None."""
    p = await db.get(Personality, pid)
    if p is None or p.user_id != user.id:
        return None
    return p


@router.post("/", response_model=PersonalityResponse, status_code=201, summary="Create personality")
async def create_personality(
    body: PersonalityCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = Personality(user_id=user.id, **body.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@router.get("/", response_model=list[PersonalityResponse], summary="List personalities")
async def list_personalities(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Personality).where(Personality.user_id == user.id).order_by(Personality.created_at)
    )
    return result.scalars().all()


@router.get("/{pid}", response_model=PersonalityResponse, summary="Get personality")
async def get_personality(
    pid: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_owned(db, pid, user)
    if not p:
        raise HTTPException(404, "Personality not found")
    return p


@router.put("/{pid}", response_model=PersonalityResponse, summary="Update personality")
async def update_personality(
    pid: uuid.UUID,
    body: PersonalityUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_owned(db, pid, user)
    if not p:
        raise HTTPException(404, "Personality not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return p


@router.delete("/{pid}", status_code=204, summary="Delete personality")
async def delete_personality(
    pid: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_owned(db, pid, user)
    if not p:
        raise HTTPException(404, "Personality not found")
    await db.delete(p)
    await db.commit()
