import pytest

from app.core.config import Settings
from app.core.prod_guard import UnsafeProductionConfig, assert_production_safe

GOOD = dict(
    APP_ENV="production",
    LLM_PROVIDER="anthropic",
    ANTHROPIC_API_KEY="sk-ant-test",
    LANGFUSE_PUBLIC_KEY="pk-lf-prod-abc123",
    LANGFUSE_SECRET_KEY="sk-lf-prod-def456",
    DATABASE_URL="postgresql+asyncpg://storyengine:S0me-Long-Rand0m@postgres:5432/storyengine",
    JWT_SECRET_KEY="x" * 48,
)


def make(**over) -> Settings:
    return Settings(_env_file=None, **{**GOOD, **over})


def test_good_production_config_passes():
    assert_production_safe(make())


def test_non_production_skips_guard():
    assert_production_safe(
        Settings(_env_file=None, APP_ENV="development", JWT_SECRET_KEY="changeme")
    )


@pytest.mark.parametrize(
    "over,needle",
    [
        ({"JWT_SECRET_KEY": "change-me-in-production-please"}, "JWT_SECRET_KEY"),
        ({"JWT_SECRET_KEY": "short"}, "JWT_SECRET_KEY"),
        ({"LANGFUSE_PUBLIC_KEY": ""}, "LANGFUSE_PUBLIC_KEY"),
        ({"LANGFUSE_SECRET_KEY": "sk-lf-story-engine-dev"}, "LANGFUSE_SECRET_KEY"),
        (
            {"DATABASE_URL": "postgresql+asyncpg://storyengine:changeme@postgres:5432/storyengine"},
            "DATABASE_URL",
        ),
        (
            {"DATABASE_URL": "postgresql+asyncpg://storyengine@postgres:5432/storyengine"},
            "DATABASE_URL",
        ),
        ({"LLM_PROVIDER": "local"}, "LLM_PROVIDER"),
        ({"ANTHROPIC_API_KEY": ""}, "ANTHROPIC_API_KEY"),
    ],
)
def test_unsafe_production_config_refused(over, needle):
    with pytest.raises(UnsafeProductionConfig) as exc:
        assert_production_safe(make(**over))
    assert needle in str(exc.value)


def test_error_never_leaks_secret_values():
    with pytest.raises(UnsafeProductionConfig) as exc:
        assert_production_safe(make(JWT_SECRET_KEY="changeme"))
    assert "changeme" not in str(exc.value)
