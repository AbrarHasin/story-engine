"""LLM adapter unit tests — no network, no model calls."""
from types import SimpleNamespace

import pytest

from app.agents.nodes import _json_loads
from app.core.config import settings
from app.llm import (
    AnthropicAdapter,
    LocalModelAdapter,
    extract_usage,
    get_adapter,
    reset_adapter,
)


@pytest.fixture(autouse=True)
def _fresh_adapter():
    reset_adapter()
    yield
    reset_adapter()


def test_get_adapter_local(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "local")
    assert isinstance(get_adapter(), LocalModelAdapter)


def test_get_adapter_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", " Anthropic ")
    assert isinstance(get_adapter(), AnthropicAdapter)


def test_get_adapter_unknown_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "nonsense")
    assert isinstance(get_adapter(), AnthropicAdapter)


def test_adapter_is_cached(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "local")
    assert get_adapter() is get_adapter()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("http://localhost:12434/engines/v1", "http://localhost:12434/engines/v1"),
        ("http://localhost:12434/engines/v1/", "http://localhost:12434/engines/v1"),
        ("http://model-runner.docker.internal/engines", "http://model-runner.docker.internal/engines/v1"),
    ],
)
def test_local_base_url_normalised(monkeypatch, raw, expected):
    monkeypatch.setattr(settings, "LOCAL_LLM_BASE_URL", raw)
    assert LocalModelAdapter().base_url == expected


def test_local_info_and_cost(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_LLM_MODEL", "ai/gemma3:4B")
    a = LocalModelAdapter()
    info = a.info()
    assert info["provider"] == "local"
    assert set(info["models"].values()) == {"ai/gemma3:4B"}
    assert info["base_url"].endswith("/v1")
    assert a.cost_usd("ai/gemma3:4B", 10_000, 10_000) == 0.0


def test_anthropic_role_models_and_cost():
    a = AnthropicAdapter()
    assert a.model_name("router") == settings.MODEL_ROUTER
    assert a.model_name("writer") == settings.MODEL_WRITER
    assert a.model_name("unknown-role") == settings.MODEL_WRITER
    # 1M in + 1M out at writer rates (3 + 15)
    assert a.cost_usd(settings.MODEL_WRITER, 1_000_000, 1_000_000) == pytest.approx(18.0)


def test_extract_usage_standard_metadata():
    resp = SimpleNamespace(usage_metadata={"input_tokens": 12, "output_tokens": 34}, response_metadata={})
    u = extract_usage(resp, "m", LocalModelAdapter())
    assert (u["input_tokens"], u["output_tokens"], u["cost_usd"]) == (12, 34, 0.0)


def test_extract_usage_openai_fallback():
    resp = SimpleNamespace(
        usage_metadata=None,
        response_metadata={"token_usage": {"prompt_tokens": 5, "completion_tokens": 7}},
    )
    u = extract_usage(resp, "m", LocalModelAdapter())
    assert (u["input_tokens"], u["output_tokens"]) == (5, 7)


def test_extract_usage_anthropic_fallback_costs():
    resp = SimpleNamespace(
        usage_metadata=None,
        response_metadata={"usage": {"input_tokens": 1_000_000, "output_tokens": 0}},
    )
    u = extract_usage(resp, settings.MODEL_ROUTER, AnthropicAdapter())
    assert u["input_tokens"] == 1_000_000
    assert u["cost_usd"] == pytest.approx(1.0)


def test_extract_usage_missing_metadata():
    u = extract_usage(SimpleNamespace(), "m", LocalModelAdapter())
    assert (u["input_tokens"], u["output_tokens"]) == (0, 0)


@pytest.mark.parametrize(
    "text,expected",
    [
        ('["a", "b"]', ["a", "b"]),
        ('```json\n["a", "b"]\n```', ["a", "b"]),
        ('Sure! Here you go:\n["a", "b"]\nHope that helps.', ["a", "b"]),
        ('{"route": "quick"}', {"route": "quick"}),
        ('Answer: {"route": "full"}', {"route": "full"}),
    ],
)
def test_json_loads_tolerant(text, expected):
    assert _json_loads(text) == expected


def test_json_loads_raises_on_garbage():
    with pytest.raises(ValueError):
        _json_loads("no json here at all")
