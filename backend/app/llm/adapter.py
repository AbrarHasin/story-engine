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
from typing import TYPE_CHECKING, Any

from app.agents.state import TokenUsage
from app.core.config import settings

if TYPE_CHECKING:  # langchain is imported lazily: /llm/config must not need it (story-api image)
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import SystemMessage

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

    def system_message(self, text: str) -> SystemMessage:
        """System prompt message. Providers may add caching hints; default is plain."""
        from langchain_core.messages import SystemMessage

        return SystemMessage(content=text)

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

        model = self.model_name(role)
        extra: dict = {}
        if model.startswith(("claude-haiku-5", "claude-sonnet-5")):
            # 5.x models reject non-default sampling params and think by default
            # (thinking tokens bill as output and would eat the small max_tokens caps).
            extra["thinking"] = (
                {"type": "disabled"} if model.startswith("claude-haiku-5")
                else {"type": "between_tools"}
            )
        else:
            extra["temperature"] = temperature

        return ChatAnthropic(  # type: ignore[call-arg]
            model=model,
            api_key=SecretStr(settings.ANTHROPIC_API_KEY),
            max_tokens=max_tokens,
            **extra,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    def system_message(self, text: str) -> SystemMessage:
        from langchain_core.messages import SystemMessage

        # Anthropic prompt caching: mark the system block (incl. personality)
        # as an ephemeral cache breakpoint.
        return SystemMessage(content=[
            {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}},
        ])

    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        rates = {  # USD per 1M tokens (input, output), list price
            "claude-haiku-5-5":           (0.10,  0.50),
            "claude-sonnet-5-5":          (2.00, 10.00),
            "claude-haiku-4-5-20251001":  (1.00,  5.00),
            "claude-sonnet-4-6":          (3.00, 15.00),
            "claude-opus-4-6":            (5.00, 25.00),
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
            max_retries=settings.LLM_MAX_RETRIES,
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


def classify_llm_error(exc: BaseException) -> tuple[str, str]:
    """Map a model-call failure to a stable (code, client-safe message).

    Never includes the raw exception text, which can carry URLs or keys.
    """
    import asyncio

    import anthropic
    import httpx
    import openai

    if isinstance(exc, (
        anthropic.APITimeoutError, openai.APITimeoutError,
        httpx.TimeoutException, asyncio.TimeoutError, TimeoutError,
    )):
        return "llm_timeout", "The language model timed out. Please try again."
    if isinstance(exc, (
        anthropic.APIConnectionError, openai.APIConnectionError,
        anthropic.RateLimitError, openai.RateLimitError,
        anthropic.InternalServerError, openai.InternalServerError,
    )):
        return "llm_unavailable", "The language model is temporarily unavailable. Please try again."
    return "internal_error", "Story generation failed. Please try again."
