"""Worker: executes one subtask in an isolated context.

A worker starts with only the scoped brief the coordinator hands it (see
ai/context.py), does the work, and returns two things:

  * the full result  — what the evaluator judges and what synthesis uses
  * a short summary   — the distilled recap that flows to downstream sub-agents

Returning a small summary (instead of the whole transcript) is the outbound
half of Anthropic's sub-agent context-isolation pattern: the coordinator's
context accumulates conclusions, not raw output.
"""
from __future__ import annotations

from ..schemas import Task
from ..utils import SUMMARY_MARKER, split_summary
from .base import BaseAgent


class WorkerAgent(BaseAgent):
    role = "worker"

    @property
    def system_prompt(self) -> str:
        return (
            "You are a WORKER agent. You are given exactly one subtask and, "
            "optionally, distilled context from earlier subtasks plus reviewer "
            "feedback from a previous attempt. Produce a correct, complete, "
            "self-contained result for THIS subtask only; do not expand scope. "
            "If feedback is present, fix every point it raises.\n\n"
            f"End your response with a line containing only {SUMMARY_MARKER} "
            "followed by a 1-3 sentence summary of what you produced, written for "
            "a coordinator who will NOT see your full output — capture the key "
            "decisions, outputs, and anything downstream tasks must know."
        )

    async def execute(self, task: Task, context: str = "") -> tuple[str, str]:
        """Return (full_result, worker_summary). Summary is "" if omitted."""
        parts = [f"Subtask:\n{task.goal}"]
        if context:
            parts.append(f"Context (distilled):\n{context}")
        if task.feedback:
            parts.append(f"Reviewer feedback to address:\n{task.feedback}")
        resp = await self.call([{"role": "user", "content": "\n\n".join(parts)}])
        return split_summary(resp.text)
