"""Offline provider for tests and dry runs. No API key, no network, no cost."""
from __future__ import annotations

import asyncio

from ..schemas import LLMResponse
from .base import Provider


class MockProvider(Provider):
    """Returns small, structure-aware canned responses so the full loop
    (plan -> waves -> execute -> evaluate) runs end to end without any vendor."""

    name = "mock"

    async def complete(self, *, system, messages, model, temperature, max_tokens) -> LLMResponse:
        await asyncio.sleep(0)  # yield control, behave like a real async call
        sys_l = (system or "").lower()
        last = messages[-1]["content"] if messages else ""

        if "planner" in sys_l:
            # Two independent subtasks (run in parallel), then one that depends
            # on both — exercises dependency waves + scoped context downstream.
            text = (
                '{"tasks": ['
                '{"id": "t1", "goal": "Research the inputs and constraints", "depends_on": []},'
                '{"id": "t2", "goal": "Draft the core solution", "depends_on": []},'
                '{"id": "t3", "goal": "Write the final answer", "depends_on": ["t1", "t2"]}'
                "]}"
            )
        elif "evaluator" in sys_l:
            text = '{"passed": true, "score": 0.9, "feedback": "Meets the definition of done (mock)."}'
        else:
            # Worker: include the ===SUMMARY=== marker so the compaction /
            # context-isolation path is exercised offline.
            body = f"[mock:{model}] Result for: {last[:160]}"
            text = f"{body}\n\n===SUMMARY===\nProduced a mock result for the subtask."

        return LLMResponse(
            text=text,
            input_tokens=len((sys_l + last).split()),
            output_tokens=len(text.split()),
            model=model,
            provider=self.name,
            raw=None,
        )
