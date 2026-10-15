"""LLM provider adapter system.

Switch between the Claude API and a local LLM (Docker Model Runner, e.g.
ai/gemma4:E4B) via the LLM_PROVIDER setting — no changes to graph nodes needed.

    LLM_PROVIDER=anthropic  → Claude API (per-role models: haiku/sonnet)
    LLM_PROVIDER=local      → any OpenAI-compatible endpoint
                              (Docker Model Runner exposes /engines/v1)

Nodes only call `get_adapter().chat(role, max_tokens, temperature)` and never
import a provider SDK directly.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.state import TokenUsage
from app.core.config import settings

logger = logging.getLogger(__name__)

# Roles a graph node can request. Each provider maps roles to concrete models.
ROLES = ("router", "writer", "synthesizer", "premium")


class LLMAdapter(ABC):
    """Provider-agnostic chat-model factory."""

    name: str = "base"

    @abstractmethod
    def chat(self, role: str, max_tokens: int, temperature: float) -> BaseChatModel:
        """Return a LangChain chat model for the given role."""

    @abstractmethod
    def model_name(self, role: str) -> str:
        """Concrete model id used for the given role."""

    @abstractmethod
    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimated USD cost of one call."""

    def info(self) -> dict:
        """Safe-to-expose description of the active provider (no secrets)."""
        return {
            "provider": self.name,
            "models": {role: self.model_name(role) for role in ROLES},
        }


class AnthropicAdapter(LLMAdapter):
    """Claude API via langchain-anthropic."""

    name = "anthropic"

    _ROLE_MODELS = {
        "router":      lambda: settings.MODEL_ROUTER,
        "writer":      lambda: settings.MODEL_WRITER,
        "synthesizer": lambda: settings.MODEL_SYNTHESIZER,
        "premium":     lambda: settings.MODEL_PREMIUM,
    }

    def model_name(self, role: str) -> str:
        return self._ROLE_MODELS.get(role, self._ROLE_MODELS["writer"])()

    def chat(self, role: str, max_tokens: int, temperature: float) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic
        from pydantic import SecretStr

        return ChatAnthropic(  # type: ignore[call-arg]
            model=self.model_name(role),
            api_key=SecretStr(settings.ANTHROPIC_API_KEY),
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        rates = {  # USD per 1M tokens (input, output)
            settings.MODEL_ROUTER:      (1.00,  5.00),
            settings.MODEL_WRITER:      (3.00, 15.00),
            settings.MODEL_SYNTHESIZER: (3.00, 15.00),
            settings.MODEL_PREMIUM:     (5.00, 25.00),
        }
        in_rate, out_rate = rates.get(model, (3.00, 15.00))
        return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


class LocalModelAdapter(LLMAdapter):
    """Local LLM via any OpenAI-compatible server.

    Designed for Docker Model Runner (https://docs.docker.com/ai/model-runner/),
    which serves pulled models (e.g. ai/gemma4:E4B) on an OpenAI-compatible
    endpoint. When run through docker-compose `models:`, the endpoint and model
    name are injected as LOCAL_LLM_BASE_URL / LOCAL_LLM_MODEL.
    """

    name = "local"

    @property
    def base_url(self) -> str:
        url = settings.LOCAL_LLM_BASE_URL.rstrip("/")
        # Docker Model Runner injects ".../engines" or ".../engines/v1/";
        # the OpenAI client needs the ".../v1" base.
        if not url.endswith("/v1"):
            url = f"{url}/v1"
        return url

    def model_name(self, role: str) -> str:
        # One local model serves every role.
        return settings.LOCAL_LLM_MODEL

    def chat(self, role: str, max_tokens: int, temperature: float) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(  # type: ignore[call-arg]
            model=self.model_name(role),
            base_url=self.base_url,
            api_key=SecretStr(settings.LOCAL_LLM_API_KEY or "docker"),
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=settings.LOCAL_LLM_TIMEOUT_SECONDS,
            max_retries=1,
        )

    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return 0.0  # local inference is free

    def info(self) -> dict:
        return {**super().info(), "base_url": self.base_url}


_ADAPTERS: dict[str, type[LLMAdapter]] = {
    "anthropic": AnthropicAdapter,
    "local":     LocalModelAdapter,
}

_active: LLMAdapter | None = None


def get_adapter() -> LLMAdapter:
    """Return the adapter selected by settings.LLM_PROVIDER (cached)."""
    global _active
    if _active is None:
        provider = settings.LLM_PROVIDER.strip().lower()
        adapter_cls = _ADAPTERS.get(provider)
        if adapter_cls is None:
            logger.warning("Unknown LLM_PROVIDER=%r — falling back to 'anthropic'", provider)
            adapter_cls = AnthropicAdapter
        _active = adapter_cls()
        logger.info("LLM adapter active: %s (%s)", _active.name, _active.info().get("models"))
    return _active


def reset_adapter() -> None:
    """Drop the cached adapter (used by tests / runtime provider switches)."""
    global _active
    _active = None


def extract_usage(response: Any, model: str, adapter: LLMAdapter | None = None) -> TokenUsage:
    """Provider-agnostic token accounting for a LangChain AIMessage."""
    adapter = adapter or get_adapter()
    in_t = out_t = 0

    usage = getattr(response, "usage_metadata", None)  # LangChain standard field
    if usage:
        in_t = usage.get("input_tokens", 0) or 0
        out_t = usage.get("output_tokens", 0) or 0
    else:
        meta = getattr(response, "response_metadata", None) or {}
        u = meta.get("usage") or meta.get("token_usage") or {}
        in_t = u.get("input_tokens") or u.get("prompt_tokens") or 0
        out_t = u.get("output_tokens") or u.get("completion_tokens") or 0

    return TokenUsage(
        input_tokens=in_t,
        output_tokens=out_t,
        cost_usd=adapter.cost_usd(model, in_t, out_t),
    )
