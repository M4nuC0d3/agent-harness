"""Anthropic (Claude) via the official SDK. Billed against your API key."""
from __future__ import annotations

import os

from ..schemas import LLMResponse
from .base import Provider


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
