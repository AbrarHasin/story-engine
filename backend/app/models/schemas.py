"""Pydantic request/response schemas."""
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.core.safety import check_prompt_text
from app.models.db import StoryStatus, PlanTier

LOCALE_PATTERN = r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$"


# ── Story ─────────────────────────────────────────────────────────────────────

class StoryGenerateRequest(BaseModel):
    topic:          str  = Field(..., min_length=3, max_length=500, examples=["The rise of AI agents"])
    tonality:       str  = Field("neutral", min_length=1, max_length=40, examples=["humorous", "serious", "inspirational"])
    audience:       str  = Field("general", min_length=1, max_length=40, examples=["general", "children", "experts", "executives"])
    length:         str  = Field("medium", pattern="^(short|medium|long)$")
    locale:         str  = Field("en", pattern=LOCALE_PATTERN, examples=["en", "bn", "ar"])
    personality_id: Optional[UUID] = None
    include_light:  bool = True
    include_dark:   bool = True
    include_facts:  bool = True

    @field_validator("topic", "tonality", "audience")
    @classmethod
    def _no_prompt_injection(cls, v: str, info: ValidationInfo) -> str:
        return check_prompt_text(v, info.field_name or "field") or v

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

class PersonalityBase(BaseModel):
    name:          str  = Field(..., min_length=1, max_length=100)
    voice:         Optional[str] = None
    tone:          Optional[str] = None
    reading_level: Optional[str] = None
    banned_words:  list[str]    = Field(default_factory=list)
    locale:        str          = "en"
    is_default:    bool         = False


class PersonalityCreate(PersonalityBase):
    """Input only: length limits and injection checks do not apply to stored rows."""
    voice:         Optional[str] = Field(None, max_length=1000)
    tone:          Optional[str] = Field(None, max_length=200)
    reading_level: Optional[str] = Field(None, max_length=100)
    banned_words:  list[str]    = Field(default_factory=list, max_length=100)

    @field_validator("name", "voice", "tone", "reading_level")
    @classmethod
    def _no_prompt_injection(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        # Personality text is compiled into the writer's system prompt.
        return check_prompt_text(v, info.field_name or "field")

    @field_validator("banned_words")
    @classmethod
    def _banned_words_clean(cls, v: list[str]) -> list[str]:
        return [check_prompt_text(w, "banned_words") or "" for w in v if w and w.strip()]

class PersonalityUpdate(PersonalityCreate):
    name: Optional[str] = None  # type: ignore[assignment]

class PersonalityResponse(PersonalityBase):
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
