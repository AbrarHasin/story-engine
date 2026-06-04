"""Pydantic request/response schemas."""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.db import StoryStatus, PlanTier


# ── Story ─────────────────────────────────────────────────────────────────────

class StoryGenerateRequest(BaseModel):
    topic:          str  = Field(..., min_length=3, max_length=500, examples=["The rise of AI agents"])
    tonality:       str  = Field("neutral", examples=["humorous", "serious", "inspirational"])
    audience:       str  = Field("general", examples=["general", "children", "experts", "executives"])
    length:         str  = Field("medium", pattern="^(short|medium|long)$")
    locale:         str  = Field("en", examples=["en", "bn", "ar"])
    personality_id: Optional[UUID] = None
    include_light:  bool = True
    include_dark:   bool = True
    include_facts:  bool = True

class StoryResponse(BaseModel):
    id:           UUID
    topic:        str
    tonality:     str
    audience:     str
    status:       StoryStatus
    light_side:   Optional[str]
    dark_side:    Optional[str]
    facts:        Optional[str]
    narrative:    Optional[str]
    final_output: Optional[str]
    tokens_input: int
    tokens_output: int
    cost_usd:     float
    created_at:   datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Personality ───────────────────────────────────────────────────────────────

class PersonalityCreate(BaseModel):
    name:          str  = Field(..., min_length=1, max_length=100)
    voice:         Optional[str] = None
    tone:          Optional[str] = None
    reading_level: Optional[str] = None
    banned_words:  list[str]    = Field(default_factory=list)
    locale:        str          = "en"
    is_default:    bool         = False

class PersonalityUpdate(PersonalityCreate):
    name: Optional[str] = None

class PersonalityResponse(PersonalityCreate):
    id:         UUID
    user_id:    UUID
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentInitiateRequest(BaseModel):
    plan: PlanTier = Field(..., examples=["pro", "enterprise"])

class PaymentInitiateResponse(BaseModel):
    payment_url: str
    tran_id:     str
    amount:      float
    currency:    str = "BDT"

PLAN_PRICES_BDT = {
    PlanTier.pro:        499.0,
    PlanTier.enterprise: 1499.0,
}


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:   str
    version:  str
    db:       str
    redis:    str
    langfuse: str
