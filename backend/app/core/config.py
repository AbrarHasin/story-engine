from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Story Engine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3001"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://storyengine:changeme@localhost:5432/storyengine"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # LLM
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
    MODEL_ROUTER: str = "claude-haiku-4-5-20251001"      # cheap, routing/sub-agents
    MODEL_WRITER: str = "claude-sonnet-4-6"              # story writer
    MODEL_SYNTHESIZER: str = "claude-sonnet-4-6"         # synthesizer/editor
    MODEL_PREMIUM: str = "claude-opus-4-6"               # premium plan only

    # Token limits per node
    MAX_TOKENS_RESEARCH: int = 300
    MAX_TOKENS_LIGHT: int = 250
    MAX_TOKENS_DARK: int = 250
    MAX_TOKENS_FACTS: int = 200
    MAX_TOKENS_WRITER: int = 1500
    MAX_TOKENS_SYNTHESIZER: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
