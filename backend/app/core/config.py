from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Story Engine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    # "production" enables the startup guard in app.core.prod_guard
    APP_ENV: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_PUBLIC_URL: str = "http://localhost:8080"  # public base for gateway callback URLs
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3001"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://storyengine:changeme@localhost:5432/storyengine"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # LLM provider selection — "anthropic" (Claude API) or "local" (Docker Model Runner)
    LLM_PROVIDER: str = "anthropic"

    # LLM — local model via OpenAI-compatible endpoint (Docker Model Runner).
    # From the host: http://localhost:12434/engines/v1
    # From a compose service with a `models:` block these are auto-injected.
    LOCAL_LLM_BASE_URL: str = "http://localhost:12434/engines/v1"
    LOCAL_LLM_MODEL: str = "ai/gemma3:4B"
    LOCAL_LLM_API_KEY: str = "docker"  # DMR ignores the key; client requires one
    LOCAL_LLM_TIMEOUT_SECONDS: int = 300  # local inference can be slow on CPU

    # LLM resilience — applied to every model call, both providers.
    # Retries use the provider SDK's exponential backoff with jitter.
    LLM_TIMEOUT_SECONDS: float = 60.0  # per request (local uses LOCAL_LLM_TIMEOUT_SECONDS)
    LLM_MAX_RETRIES: int = 2           # retries after the first attempt

    # LLM — Claude API
    ANTHROPIC_API_KEY: str = ""
    LITELLM_BASE_URL: str = "http://localhost:4000"

    # Langfuse — free OSS observability (replaces LangSmith)
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "http://localhost:3000"

    # SSLCommerz
    SSLCOMMERZ_STORE_ID: str = ""
    SSLCOMMERZ_STORE_PASS: str = ""
    SSLCOMMERZ_SANDBOX: bool = True

    # Auth
    AUTH0_DOMAIN: str = ""
    AUTH0_CLIENT_ID: str = ""
    AUTH0_CLIENT_SECRET: str = ""
    JWT_SECRET_KEY: str = "changeme-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Model aliases (resolved by LiteLLM proxy or direct)
    MODEL_ROUTER: str = "claude-haiku-5-5"               # cheap, routing/sub-agents ($0.10/$0.50 per 1M)
    MODEL_WRITER: str = "claude-haiku-5-5"               # story writer ($0.10/$0.50 per 1M)
    MODEL_SYNTHESIZER: str = "claude-haiku-5-5"          # critic editor ($0.10/$0.50 per 1M)
    MODEL_PREMIUM: str = "claude-opus-4-6"               # premium plan only

    # Quotas and rate limits (issue #9). Plan limit = completed stories per month; 0 = unlimited.
    PLAN_LIMIT_FREE: int = 10
    PLAN_LIMIT_PRO: int = 200
    PLAN_LIMIT_ENTERPRISE: int = 0
    RATE_LIMIT_PER_MINUTE: int = 5   # generate calls per user per minute; 0 disables

    # Semantic cache (pgvector near-duplicate lookup before generation)
    SEMANTIC_CACHE_ENABLED: bool = False
    SEMANTIC_CACHE_THRESHOLD: float = 0.92   # min cosine similarity for a hit
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"  # local, free
    EMBEDDING_DIM: int = 384                 # must match stories.embedding (migration 0003)

    # Token limits per node
    MAX_TOKENS_RESEARCH: int = 300
    MAX_TOKENS_LIGHT: int = 250
    MAX_TOKENS_DARK: int = 250
    MAX_TOKENS_FACTS: int = 200
    MAX_TOKENS_WRITER: int = 1500
    MAX_TOKENS_SYNTHESIZER: int = 1500  # must be >= MAX_TOKENS_WRITER


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
