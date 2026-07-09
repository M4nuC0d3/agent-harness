"""Planner: turns a high-level goal into subtasks, optionally with dependencies.

This is the orchestrator side of Anthropic's *orchestrator-workers* pattern:
a central model decides the subtasks dynamically (they are not hard-coded), and
may declare a dependency graph so independent work runs in parallel while
dependent work waits for — and is given a distilled summary of — its inputs.
"""
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
            "list of concrete, independently executable subtasks (prefer 2-6). "
            "Each subtask must be self-contained with an obvious definition of done. "
            "Mark dependencies so independent subtasks can run in parallel and "
            "dependent ones wait for their inputs. Return ONLY JSON of the form: "
            '{"tasks": [{"id": "t1", "goal": "...", "depends_on": []}, '
            '{"id": "t2", "goal": "...", "depends_on": ["t1"]}]}. '
            "Use short ids like t1, t2. depends_on may be empty. No prose, no markdown."
        )

    async def plan(self, goal: str, feedback: str | None = None) -> list[Task]:
        user = f"Goal:\n{goal}"
        if feedback:
            # Re-planning after a human asked for changes at the plan checkpoint.
            user += f"\n\nRevise the plan per this feedback:\n{feedback}"
        resp = await self.call([{"role": "user", "content": user}])
        try:
            data = extract_json(resp.text)
        except ValueError:
            return [Task(goal=goal)]  # fall back: whole goal as one task

        raw = data.get("tasks") if isinstance(data, dict) else data
        if not isinstance(raw, list) or not raw:
            return [Task(goal=goal)]

        tasks: list[Task] = []
        id_map: dict[str, str] = {}
        for item in raw:
            if isinstance(item, dict):
                t = Task(goal=str(item.get("goal", "")).strip())
                if item.get("id"):
                    id_map[str(item["id"])] = t.id
                t._raw_deps = [str(d) for d in item.get("depends_on", [])]  # type: ignore[attr-defined]
            else:  # backward-compatible flat form: ["subtask a", "subtask b"]
                t = Task(goal=str(item).strip())
                t._raw_deps = []  # type: ignore[attr-defined]
            if t.goal:
                tasks.append(t)

        # Resolve planner-supplied ids (t1, t2, …) to the real Task ids.
        for t in tasks:
            t.depends_on = [id_map[d] for d in getattr(t, "_raw_deps", []) if d in id_map]
            if hasattr(t, "_raw_deps"):
                delattr(t, "_raw_deps")
        return tasks or [Task(goal=goal)]
