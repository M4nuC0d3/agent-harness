"""Common machinery shared by every sub-agent."""
from __future__ import annotations

import asyncio
import random
from typing import Optional

from ..providers import get_provider
from ..observability import Trace, get_logger
from ..schemas import LLMResponse, ModelSpec, Usage


class BaseAgent:
    """Base class for all sub-agents.

    Responsibilities kept here so each concrete agent stays tiny:
      - holds its own ModelSpec (the per-agent model knob)
      - one model call with timeout, retries and exponential backoff
      - records token usage into the shared Usage accumulator

    Subclasses provide ``system_prompt`` and a task-specific method.
    """

    role: str = "agent"

    def __init__(
        self,
        spec: ModelSpec,
        usage: Usage,
        trace: Optional[Trace] = None,
        max_retries: int = 3,
        request_timeout: float = 120.0,
    ) -> None:
        self.spec = spec
        self.usage = usage
        self.trace = trace
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self.log = get_logger()

    @property
    def system_prompt(self) -> str:
        return "You are a helpful assistant."

    async def call(self, messages: list[dict]) -> LLMResponse:
        """One model call: timeout + retries/backoff, updates shared usage."""
        provider = get_provider(self.spec)
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await asyncio.wait_for(
                    provider.complete(
                        system=self.system_prompt,
                        messages=messages,
                        model=self.spec.model,
                        temperature=self.spec.temperature,
                        max_tokens=self.spec.max_tokens,
                    ),
                    timeout=self.request_timeout,
                )
                self.usage.add(resp.input_tokens, resp.output_tokens)
                if self.trace:
                    self.trace.event(
                        "model_call",
                        role=self.role,
                        provider=self.spec.provider,
                        model=self.spec.model,
                        attempt=attempt,
                        in_tokens=resp.input_tokens,
                        out_tokens=resp.output_tokens,
                    )
                return resp
            except Exception as exc:  # noqa: BLE001 - resilience boundary
                if attempt > self.max_retries:
                    if self.trace:
                        self.trace.event(
                            "model_error", role=self.role, error=str(exc), attempt=attempt
                        )
                    raise
                backoff = min(2 ** attempt + random.random(), 30.0)
                self.log.warning(
                    "%s call failed (attempt %d/%d): %s -> retry in %.1fs",
                    self.role,
                    attempt,
                    self.max_retries,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
