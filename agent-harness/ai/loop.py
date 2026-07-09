"""The coordinator loop.

    plan  ->  (execute workers concurrently  ->  evaluate  ->  revise)*  ->  synthesize

Termination is guaranteed by the Budget (tokens / wall-clock / iterations) and
by max_revisions_per_task. Nothing here can loop forever.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from pathlib import Path
from typing import Callable, Optional

from .agents.evaluator import EvaluatorAgent
from .agents.planner import PlannerAgent
from .agents.worker import WorkerAgent
from .config import HarnessConfig, load_config
from .observability import Trace, get_logger
from .schemas import Evaluation, RunState, Task, TaskStatus


class AsyncOrchestrator:
    def __init__(self, config: Optional[HarnessConfig] = None) -> None:
        self.cfg = config or load_config()
        self.log = get_logger()

    # -- agent factories -----------------------------------------------------
    # Workers/evaluators are created per task so concurrent tasks get their own
    # instances; the factories close over config + the shared usage counter.
    def _factories(self, state: RunState, trace: Trace):
        planner = PlannerAgent(self.cfg.model_for("planner"), state.usage, trace)

        def make_worker() -> WorkerAgent:
            return WorkerAgent(self.cfg.model_for("worker"), state.usage, trace)

        def make_evaluator() -> EvaluatorAgent:
            return EvaluatorAgent(
                self.cfg.model_for("evaluator"),
                state.usage,
                trace,
                pass_threshold=self.cfg.pass_threshold,
            )

        return planner, make_worker, make_evaluator

    # -- per-task inner loop: execute -> evaluate -> revise ------------------
    async def _run_task(
        self,
        task: Task,
        context: str,
        make_worker: Callable[[], WorkerAgent],
        make_evaluator: Callable[[], EvaluatorAgent],
        state: RunState,
        trace: Trace,
        sem: asyncio.Semaphore,
    ) -> Task:
        async with sem:  # bound how many workers run at once
            worker = make_worker()
            evaluator = make_evaluator()
            while True:
                stop = state.budget.exceeded(state.usage)
                if stop:
                    task.status = TaskStatus.FAILED
                    task.error = stop
                    return task

                state.budget.iterations += 1
                task.attempts += 1
                task.status = TaskStatus.RUNNING

                with trace.span("task", task_id=task.id, attempt=task.attempts):
                    try:
                        task.result = await worker.execute(task, context=context)
                    except Exception as exc:  # worker gave up after its own retries
                        task.status = TaskStatus.FAILED
                        task.error = f"worker failed: {exc}"
                        return task
                    ev: Evaluation = await evaluator.evaluate(task, task.result)
                    task.score = ev.score

                trace.event(
                    "evaluation",
                    task_id=task.id,
                    passed=ev.passed,
                    score=ev.score,
                    feedback=ev.feedback[:300],
                )

                if ev.passed:
                    task.status = TaskStatus.DONE
                    task.feedback = None
                    return task

                if task.attempts > state.budget.max_revisions_per_task:
                    # Out of revision rounds: keep the best-effort result.
                    task.status = TaskStatus.NEEDS_REVISION
                    task.feedback = ev.feedback
                    return task

                task.feedback = ev.feedback  # feed back into the next attempt

    # -- top-level run -------------------------------------------------------
    async def run(self, goal: str) -> RunState:
        state = RunState(goal=goal)
        # Fresh budget counters per run, but the configured limits.
        state.budget = dataclasses.replace(
            self.cfg.budget, started_at=time.monotonic(), iterations=0
        )
        trace = Trace(state.id, out_dir=self.cfg.runs_dir)
        trace.event(
            "run_start",
            goal=goal,
            models={r: s.label() for r, s in self.cfg.models.items()},
        )
        planner, make_worker, make_evaluator = self._factories(state, trace)

        # 1) PLAN
        with trace.span("plan"):
            state.budget.iterations += 1
            try:
                state.tasks = await planner.plan(goal)
            except Exception as exc:
                state.stopped_reason = f"planning failed: {exc}"
                trace.event("run_end", reason=state.stopped_reason)
                return state
        trace.event("plan_ready", n_tasks=len(state.tasks), tasks=[t.goal for t in state.tasks])

        # 2) HUMAN-IN-THE-LOOP approval gate (optional)
        if self.cfg.require_human_approval and not self._approve_plan(state.tasks):
            state.stopped_reason = "plan rejected by human"
            trace.event("run_end", reason=state.stopped_reason)
            return state

        # 3) EXECUTE + EVALUATE (concurrent, bounded)
        # Simple model: independent subtasks run in parallel. For real
        # dependencies, group tasks into waves by `depends_on` and gather per
        # wave, threading each wave's output into the next wave's context.
        sem = asyncio.Semaphore(self.cfg.max_concurrency)
        context = f"Overall goal: {goal}"
        results = await asyncio.gather(
            *[
                self._run_task(t, context, make_worker, make_evaluator, state, trace, sem)
                for t in state.tasks
            ]
        )
        state.tasks = list(results)

        # 4) SYNTHESIZE
        state.final_output = self._synthesize(state)
        state.stopped_reason = state.budget.exceeded(state.usage) or "completed"
        trace.event(
            "run_end",
            reason=state.stopped_reason,
            in_tokens=state.usage.input_tokens,
            out_tokens=state.usage.output_tokens,
            calls=state.usage.calls,
        )
        self._persist(state)
        return state

    # -- helpers -------------------------------------------------------------
    def _approve_plan(self, tasks: list[Task]) -> bool:
        print("\nProposed plan:")
        for i, t in enumerate(tasks, 1):
            print(f"  {i}. {t.goal}")
        try:
            return input("Approve plan? [y/N] ").strip().lower() == "y"
        except EOFError:
            return True  # non-interactive session: auto-approve

    def _synthesize(self, state: RunState) -> str:
        chunks = []
        for i, t in enumerate(state.tasks, 1):
            header = f"## Subtask {i}: {t.goal}  ({t.status.value}, score={t.score})"
            chunks.append(header + "\n" + (t.result or t.error or "(no result)"))
        return "\n\n".join(chunks)

    def _persist(self, state: RunState) -> None:
        path = Path(self.cfg.runs_dir) / f"{state.id}.result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state.to_dict(), indent=2, default=str), encoding="utf-8")


async def run_goal(goal: str, config: Optional[HarnessConfig] = None) -> RunState:
    """Convenience entry point for programmatic use."""
    return await AsyncOrchestrator(config).run(goal)
