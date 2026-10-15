"""Startup guard: refuse to boot in production with dev-default or missing secrets."""
from urllib.parse import urlparse

from app.core.config import Settings

PRODUCTION_ENVS = {"production", "prod"}
KNOWN_DEV_JWT_SECRETS = {
    "changeme",
    "changeme-in-production",
    "change-me-in-production-please",
    "secret",
}
KNOWN_DEV_DB_PASSWORDS = {"", "changeme", "postgres", "password", "storyengine"}
MIN_JWT_SECRET_LENGTH = 32


class UnsafeProductionConfig(RuntimeError):
    """Raised at startup when production config uses dev defaults or is missing."""


def _is_dev_langfuse_key(value: str) -> bool:
    return "story-engine-dev" in value or value.endswith("-dev")


def production_config_problems(s: Settings) -> list[str]:
    """Return human-readable problems (names only, never secret values)."""
    problems: list[str] = []

    if s.LLM_PROVIDER != "anthropic":
        problems.append("LLM_PROVIDER must be explicitly 'anthropic' in production")
    elif not s.ANTHROPIC_API_KEY:
        problems.append("ANTHROPIC_API_KEY is missing")

    # Langfuse is optional (production runs with tracing off); if set, it must be real
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        if _is_dev_langfuse_key(getattr(s, name)):
            problems.append(f"{name} is a dev default (unset it to run without tracing)")
    if bool(s.LANGFUSE_PUBLIC_KEY) != bool(s.LANGFUSE_SECRET_KEY):
        problems.append("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set together or not at all")

    if s.DB_BACKEND == "dataapi":
        # credentials live in Secrets Manager; DATABASE_URL is unused
        if not s.DATAAPI_RESOURCE_ARN.startswith("arn:"):
            problems.append("DATAAPI_RESOURCE_ARN is missing")
        if not s.DATAAPI_SECRET_ARN.startswith("arn:"):
            problems.append("DATAAPI_SECRET_ARN is missing")
    else:
        db_password = urlparse(s.DATABASE_URL).password or ""
        if db_password.lower() in KNOWN_DEV_DB_PASSWORDS:
            problems.append("DATABASE_URL password is missing or a dev default")

    jwt = s.JWT_SECRET_KEY
    if jwt.lower() in KNOWN_DEV_JWT_SECRETS or len(jwt) < MIN_JWT_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET_KEY is a dev default or shorter than {MIN_JWT_SECRET_LENGTH} chars"
        )

    return problems


def assert_production_safe(s: Settings) -> None:
    """No-op outside production; raises UnsafeProductionConfig inside it."""
    if s.APP_ENV.lower() not in PRODUCTION_ENVS:
        return
    problems = production_config_problems(s)
    if problems:
        raise UnsafeProductionConfig(
            "Refusing to start in production: " + "; ".join(problems)
        )
