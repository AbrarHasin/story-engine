"""SQLAlchemy ORM models — users, personalities, stories, runs, payments."""
import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey,
    JSON, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base
import enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class StoryStatus(str, enum.Enum):
    pending    = "pending"
    running    = "running"
    completed  = "completed"
    failed     = "failed"

class PlanTier(str, enum.Enum):
    free       = "free"
    pro        = "pro"
    enterprise = "enterprise"

class PaymentStatus(str, enum.Enum):
    initiated  = "initiated"
    confirmed  = "confirmed"
    failed     = "failed"
    cancelled  = "cancelled"


# ── User ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:            Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:         Mapped[str]        = mapped_column(String(255), unique=True, nullable=False, index=True)
    name:          Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))   # nullable for dev user / OAuth users
    plan:          Mapped[PlanTier]   = mapped_column(SAEnum(PlanTier), default=PlanTier.free)
    stories_this_month: Mapped[int] = mapped_column(Integer, default=0)
    quota_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_tokens_used:  Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow)

    personalities: Mapped[list["Personality"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    stories:       Mapped[list["Story"]]       = relationship(back_populates="user", cascade="all, delete-orphan")
    payments:      Mapped[list["Payment"]]     = relationship(back_populates="user")


# ── Personality ───────────────────────────────────────────────────────────────

class Personality(Base):
    __tablename__ = "personalities"

    id:           Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:      Mapped[uuid.UUID]  = mapped_column(ForeignKey("users.id"), nullable=False)
    name:         Mapped[str]        = mapped_column(String(100), nullable=False)
    voice:        Mapped[str | None] = mapped_column(Text)           # e.g. "pirate", "professor"
    tone:         Mapped[str | None] = mapped_column(String(100))    # e.g. "humorous", "serious"
    reading_level:Mapped[str | None] = mapped_column(String(50))     # e.g. "beginner", "expert"
    banned_words: Mapped[list]       = mapped_column(JSON, default=list)
    locale:       Mapped[str]        = mapped_column(String(10), default="en")
    is_default:   Mapped[bool]       = mapped_column(Boolean, default=False)
    created_at:   Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:   Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="personalities")


# ── Story ─────────────────────────────────────────────────────────────────────

class Story(Base):
    __tablename__ = "stories"

    id:              Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:         Mapped[uuid.UUID]   = mapped_column(ForeignKey("users.id"), nullable=False)
    personality_id:  Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personalities.id"))

    # Input
    topic:           Mapped[str]         = mapped_column(Text, nullable=False)
    tonality:        Mapped[str]         = mapped_column(String(100), default="neutral")
    audience:        Mapped[str]         = mapped_column(String(100), default="general")
    length:          Mapped[str]         = mapped_column(String(50), default="medium")  # short/medium/long
    locale:          Mapped[str]         = mapped_column(String(10), default="en")

    # Output sections (populated by graph nodes)
    research:        Mapped[str | None]  = mapped_column(Text)
    light_side:      Mapped[str | None]  = mapped_column(Text)
    dark_side:       Mapped[str | None]  = mapped_column(Text)
    facts:           Mapped[str | None]  = mapped_column(Text)
    narrative:       Mapped[str | None]  = mapped_column(Text)
    final_output:    Mapped[str | None]  = mapped_column(Text)

    # Meta
    status:          Mapped[StoryStatus] = mapped_column(SAEnum(StoryStatus), default=StoryStatus.pending)
    tokens_input:    Mapped[int]         = mapped_column(Integer, default=0)
    tokens_output:   Mapped[int]         = mapped_column(Integer, default=0)
    cost_usd:        Mapped[float]       = mapped_column(Float, default=0.0)
    langgraph_run_id:Mapped[str | None]  = mapped_column(String(255))   # for Langfuse trace link
    created_at:      Mapped[datetime]    = mapped_column(DateTime, default=datetime.utcnow)
    completed_at:    Mapped[datetime | None] = mapped_column(DateTime)

    # pgvector embedding for semantic cache / RAG
    embedding:       Mapped[list | None] = mapped_column(Vector(384))

    user: Mapped["User"] = relationship(back_populates="stories")


# ── Payment ───────────────────────────────────────────────────────────────────

class Payment(Base):
    __tablename__ = "payments"

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:        Mapped[uuid.UUID]    = mapped_column(ForeignKey("users.id"), nullable=False)
    tran_id:        Mapped[str]          = mapped_column(String(255), unique=True, nullable=False)   # SSLCommerz tran_id
    val_id:         Mapped[str | None]   = mapped_column(String(255))                               # SSLCommerz val_id
    amount:         Mapped[float]        = mapped_column(Float, nullable=False)
    currency:       Mapped[str]          = mapped_column(String(10), default="BDT")
    plan:           Mapped[PlanTier]     = mapped_column(SAEnum(PlanTier))
    status:         Mapped[PaymentStatus]= mapped_column(SAEnum(PaymentStatus), default=PaymentStatus.initiated)
    ipn_payload:    Mapped[dict | None]  = mapped_column(JSON)
    created_at:     Mapped[datetime]     = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at:   Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="payments")
