"""Worker: executes one subtask. On a revision round it also receives the
evaluator's feedback and must address it."""
from __future__ import annotations

from ..schemas import Task
from .base import BaseAgent


class WorkerAgent(BaseAgent):
    role = "worker"

    @property
    def system_prompt(self) -> str:
        return (
            "You are a WORKER agent. You are given exactly one subtask and, "
            "optionally, reviewer feedback from a previous attempt plus context "
            "from earlier subtasks. Produce a correct, complete, self-contained "
            "result for this subtask only. If feedback is present, fix every "
            "point it raises."
        )

    async def execute(self, task: Task, context: str = "") -> str:
        parts = [f"Subtask:\n{task.goal}"]
        if context:
            parts.append(f"Context:\n{context}")
        if task.feedback:
            parts.append(f"Reviewer feedback to address:\n{task.feedback}")
        resp = await self.call([{"role": "user", "content": "\n\n".join(parts)}])
        return resp.text.strip()
