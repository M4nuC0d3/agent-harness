"""Provider-agnostic model layer.

Every provider implements ``async def complete(...) -> LLMResponse``.
``get_provider(spec)`` returns a cached provider instance for a ModelSpec.

This is where you plug in vendors. Implemented:
  - anthropic  (real, via the official SDK)
  - openai     (real, via the official SDK)
  - local      (real, any OpenAI-compatible server: Ollama / vLLM / LM Studio)
  - google     (real-ish; verify against the current google-genai SDK)
  - mock       (offline, no keys / no network — for tests and dry runs)

All SDK imports are lazy, so the harness loads and runs (with the mock
provider) even if you have not installed any vendor SDK.
"""
from __future__ import annotations

import asyncio
import os
from typing import Type

from .schemas import LLMResponse, ModelSpec


class Provider:
    name = "base"

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic  # pip install anthropic

            self._client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        return self._client

    async def complete(self, *, system, messages, model, temperature, max_tokens) -> LLMResponse:
        client = self._get_client()
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or None,
            messages=messages,
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=model,
            provider=self.name,
            raw=resp,
        )


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # pip install openai

            self._client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        return self._client

    async def complete(self, *, system, messages, model, temperature, max_tokens) -> LLMResponse:
        client = self._get_client()
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        resp = await client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,  # some newer models want max_completion_tokens
        )
        text = resp.choices[0].message.content or ""
        u = resp.usage
        return LLMResponse(
            text=text,
            input_tokens=getattr(u, "prompt_tokens", 0),
            output_tokens=getattr(u, "completion_tokens", 0),
            model=model,
            provider=self.name,
            raw=resp,
        )


class LocalOpenAIProvider(OpenAIProvider):
    """Any OpenAI-compatible endpoint: Ollama, vLLM, LM Studio, etc.

    Configure via LOCAL_OPENAI_BASE_URL (default http://localhost:11434/v1).
    """

    name = "local"

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=os.environ.get("LOCAL_OPENAI_BASE_URL", "http://localhost:11434/v1"),
                api_key=os.environ.get("LOCAL_OPENAI_API_KEY", "not-needed"),
            )
        return self._client


class GoogleProvider(Provider):
    """Gemini via the google-genai SDK. Minimal adapter — verify the exact
    async surface against the SDK version you install (it moves fast)."""

    name = "google"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai  # pip install google-genai

            self._client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
        return self._client

    async def complete(self, *, system, messages, model, temperature, max_tokens) -> LLMResponse:
        client = self._get_client()
        prompt = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
        resp = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "system_instruction": system or None,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        text = resp.text or ""
        um = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text=text,
            input_tokens=getattr(um, "prompt_token_count", 0) if um else 0,
            output_tokens=getattr(um, "candidates_token_count", 0) if um else 0,
            model=model,
            provider=self.name,
            raw=resp,
        )


class MockProvider(Provider):
    """Offline provider for tests and dry runs. No API key, no network.

    It returns small, structure-aware canned responses so the full loop
    (plan -> execute -> evaluate) runs end to end without any vendor.
    """

    name = "mock"

    async def complete(self, *, system, messages, model, temperature, max_tokens) -> LLMResponse:
        await asyncio.sleep(0)  # yield control, behave like a real async call
        sys_l = (system or "").lower()
        last = messages[-1]["content"] if messages else ""

        if "planner" in sys_l:
            text = '{"tasks": ["Analyze the request", "Draft a solution", "Write the final answer"]}'
        elif "evaluator" in sys_l:
            text = '{"passed": true, "score": 0.9, "feedback": "Meets the definition of done (mock)."}'
        else:
            text = f"[mock:{model}] Result for: {last[:160]}"

        return LLMResponse(
            text=text,
            input_tokens=len((sys_l + last).split()),
            output_tokens=len(text.split()),
            model=model,
            provider=self.name,
            raw=None,
        )


_PROVIDER_CLASSES: dict[str, Type[Provider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
    "local": LocalOpenAIProvider,
    "mock": MockProvider,
}
_PROVIDERS: dict[str, Provider] = {}


def get_provider(spec: ModelSpec) -> Provider:
    """Return a cached provider instance for the given spec's provider name."""
    key = spec.provider
    if key not in _PROVIDERS:
        if key not in _PROVIDER_CLASSES:
            raise ValueError(
                f"Unknown provider '{key}'. Known: {sorted(_PROVIDER_CLASSES)}. "
                "Register your own with register_provider()."
            )
        _PROVIDERS[key] = _PROVIDER_CLASSES[key]()
    return _PROVIDERS[key]


def register_provider(name: str, provider: Provider) -> None:
    """Plug in a custom provider at runtime (e.g. Azure, Bedrock, a router)."""
    _PROVIDERS[name] = provider
    _PROVIDER_CLASSES[name] = type(provider)
