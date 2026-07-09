"""OpenAI, plus any OpenAI-compatible endpoint (Ollama / vLLM / LM Studio).

Both are billed against an API key — a ChatGPT subscription does not cover API
calls. For the subscription path, see providers/cli.py.
"""
from __future__ import annotations

import os

from ..schemas import LLMResponse
from .base import Provider


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
