"""Gemini via the google-genai SDK.

Minimal adapter — verify the exact async surface against the SDK version you
install; it moves fast. Billed against your Gemini API key / Cloud billing
account (the Gemini consumer subscription does not cover API calls), though a
free tier exists. For the subscription path, see providers/cli.py.
"""
from __future__ import annotations

import os

from ..schemas import LLMResponse
from .base import Provider


class GoogleProvider(Provider):
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
