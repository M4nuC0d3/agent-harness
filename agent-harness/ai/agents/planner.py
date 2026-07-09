"""Planner: turns a high-level goal into an ordered list of subtasks."""
from __future__ import annotations

from ..schemas import Task
from ..utils import extract_json
from .base import BaseAgent


class PlannerAgent(BaseAgent):
    role = "planner"

    @property
    def system_prompt(self) -> str:
        return (
            "You are the PLANNER. Decompose the user's goal into a short, ordered "
            "list of concrete, independently executable subtasks. Prefer 2-6 "
            "subtasks. Each subtask must be self-contained and have an obvious "
            "definition of done. Return ONLY JSON of the form "
            '{"tasks": ["subtask 1", "subtask 2", ...]}. No prose, no markdown.'
        )

    async def plan(self, goal: str) -> list[Task]:
        resp = await self.call([{"role": "user", "content": f"Goal:\n{goal}"}])
        data = extract_json(resp.text)
        subtasks = data.get("tasks") if isinstance(data, dict) else data
        if not isinstance(subtasks, list) or not subtasks:
            # Robust fallback: treat the whole goal as a single task.
            return [Task(goal=goal)]
        return [Task(goal=str(s)) for s in subtasks]
