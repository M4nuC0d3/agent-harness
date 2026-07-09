"""The coordinator loop (orchestrator-workers + evaluator-optimizer).

    plan -> [human check] -> for each wave: (workers ‖ -> evaluate -> [human check] -> revise)* -> synthesize -> [human check]

Two Anthropic patterns, made concrete:
  * orchestrator-workers  — a planner splits the goal; workers run the subtasks,
    grouped into dependency *waves* so independent work runs in parallel.
  * evaluator-optimizer   — every result is scored by a critic and sent back with
    feedback until it passes or the revision budget runs out.

On top of that:
  * context isolation — each worker gets only a scoped brief (summaries of its
    dependencies), and returns a distilled summary that flows downstream.
  * human-in-the-loop — optional checkpoints at plan / result / final.

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
from .context import ContextManager
from .hitl import AutoReviewer, CLIReviewer, ReviewAction, Reviewer
from .observability import Trace, get_logger
from .schemas import Evaluation, RunState, Task, TaskStatus


class AsyncOrchestrator:
    def __init__(
        self,
        config: Optional[HarnessConfig] = None,
        reviewer: Optional[Reviewer] = None,
        show_progress: bool = True,
    ) -> None:
        self.cfg = config or load_config()
        # Pick the reviewer: explicit > interactive-from-config > automatic.
        self.reviewer = reviewer or (
            CLIReviewer() if self.cfg.hitl.interactive else AutoReviewer()
        )
        self.ctx = ContextManager(self.cfg.context)
        self.show_progress = show_progress
        self.log = get_logger()

    def _say(self, msg: str) -> None:
        if self.show_progress:
            print(msg)

    # -- agent factories -----------------------------------------------------
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

    # -- HITL helpers --------------------------------------------------------
    def _result_gate_active(self, passed: bool) -> bool:
        if not self.cfg.hitl.interactive:
            return False
        mode = self.cfg.hitl.results
        return mode == "always" or (mode == "on_fail" and not passed)

    async def _review(self, lock: asyncio.Lock, fn, *args):
        """Serialize (blocking) human prompts so concurrent tasks don't interleave."""
        async with lock:
            return fn(*args)

    # -- dependency waves ----------------------------------------------------
    @staticmethod
    def _waves(tasks: list[Task]) -> list[list[Task]]:
        """Group tasks into execution waves by depends_on (topological)."""
        done: set[str] = set()
        remaining = list(tasks)
        waves: list[list[Task]] = []
        while remaining:
            ready = [t for t in remaining if all(d in done for d in t.depends_on)]
            if not ready:  # cycle / dangling dep: run whatever is left together
                ready = remaining
            waves.append(ready)
            done.update(t.id for t in ready)
            remaining = [t for t in remaining if t not in ready]
        return waves

    # -- per-task inner loop: execute -> evaluate -> (human) -> revise -------
    async def _run_task(
        self,
        task: Task,
        context: str,
        make_worker: Callable[[], WorkerAgent],
        make_evaluator: Callable[[], EvaluatorAgent],
        state: RunState,
        trace: Trace,
        sem: asyncio.Semaphore,
        review_lock: asyncio.Lock,
        control: dict,
    ) -> Task:
        async with sem:  # bound how many workers run at once
            worker = make_worker()
            evaluator = make_evaluator()
            while True:
                if control.get("abort"):
                    return task
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
                        result, summary = await worker.execute(task, context=context)
                    except Exception as exc:  # worker gave up after its own retries
                        task.status = TaskStatus.FAILED
                        task.error = f"worker failed: {exc}"
                        return task
                    task.result = result
                    task.summary = self.ctx.compact(result, summary)
                    ev: Evaluation = await evaluator.evaluate(task, result)
                    task.score = ev.score

                trace.event(
                    "evaluation", task_id=task.id, passed=ev.passed,
                    score=ev.score, feedback=ev.feedback[:300],
                )

                # Optional human checkpoint on this result.
                if self._result_gate_active(ev.passed):
                    decision = await self._review(
                        review_lock, self.reviewer.review_result, task, ev
                    )
                    if decision.action is ReviewAction.ABORT:
                        control["abort"] = decision.note or "aborted by human"
                        task.status = TaskStatus.NEEDS_REVISION
                        return task
                    if decision.action is ReviewAction.APPROVE:
                        task.status = TaskStatus.DONE  # human overrides the critic
                        task.feedback = None
                        self._say(f"  ✓ {task.goal}  (human-approved, score={ev.score:.2f})")
                        return task
                    if decision.action is ReviewAction.REVISE:
                        task.feedback = decision.feedback
                        if task.attempts > state.budget.max_revisions_per_task:
                            task.status = TaskStatus.NEEDS_REVISION
                            return task
                        self._say(f"  ↻ {task.goal}  (human asked for changes)")
                        continue

                if ev.passed:
                    task.status = TaskStatus.DONE
                    task.feedback = None
                    self._say(f"  ✓ {task.goal}  (score={ev.score:.2f})")
                    return task

                if task.attempts > state.budget.max_revisions_per_task:
                    task.status = TaskStatus.NEEDS_REVISION
                    task.feedback = ev.feedback
                    self._say(f"  ✗ {task.goal}  (needs revision, score={ev.score:.2f})")
                    return task

                task.feedback = ev.feedback  # feed back into the next attempt
                self._say(f"  ↻ {task.goal}  (revising, score={ev.score:.2f})")

    # -- top-level run -------------------------------------------------------
    async def run(self, goal: str) -> RunState:
        state = RunState(goal=goal)
        state.budget = dataclasses.replace(
            self.cfg.budget, started_at=time.monotonic(), iterations=0
        )
        trace = Trace(state.id, out_dir=self.cfg.runs_dir)
        trace.event(
            "run_start", goal=goal,
            models={r: s.label() for r, s in self.cfg.models.items()},
            context_policy=self.cfg.context.policy.value,
            hitl=self.cfg.hitl.mode,
        )
        planner, make_worker, make_evaluator = self._factories(state, trace)
        review_lock = asyncio.Lock()
        control: dict = {"abort": None}

        # 1) PLAN (+ optional human checkpoint, with one bounded re-plan) -----
        replanned = False
        while True:
            with trace.span("plan"):
                state.budget.iterations += 1
                try:
                    fb = control.pop("plan_feedback", None)
                    state.tasks = await planner.plan(goal, feedback=fb)
                except Exception as exc:
                    state.stopped_reason = f"planning failed: {exc}"
                    trace.event("run_end", reason=state.stopped_reason)
                    return state
            self._say(f"\nPLAN: {len(state.tasks)} subtask(s)")
            for i, t in enumerate(state.tasks, 1):
                self._say(f"  {i}. {t.goal}")
            trace.event("plan_ready", n_tasks=len(state.tasks),
                        tasks=[t.goal for t in state.tasks])

            if not (self.cfg.hitl.interactive and self.cfg.hitl.plan):
                break
            decision = await self._review(review_lock, self.reviewer.review_plan, state.tasks)
            if decision.action is ReviewAction.APPROVE:
                break
            if decision.action is ReviewAction.EDIT and decision.tasks:
                state.tasks = decision.tasks
                trace.event("plan_edited", n_tasks=len(state.tasks))
                break
            if decision.action is ReviewAction.REVISE and not replanned:
                control["plan_feedback"] = decision.feedback
                replanned = True
                continue  # re-plan once with the human's feedback
            if decision.action is ReviewAction.ABORT:
                state.stopped_reason = decision.note or "plan rejected by human"
                trace.event("run_end", reason=state.stopped_reason)
                return state
            break  # e.g. revise requested a second time: proceed with current plan

        # 2) EXECUTE wave by wave (parallel within a wave, scoped context) ----
        waves = self._waves(state.tasks)
        self._say(f"Running in {len(waves)} wave(s), up to {self.cfg.max_concurrency} in parallel.")
        trace.event("waves", n=len(waves), sizes=[len(w) for w in waves])
        sem = asyncio.Semaphore(self.cfg.max_concurrency)

        for wi, wave in enumerate(waves, 1):
            if control.get("abort"):
                break
            self._say(f"\nWAVE {wi}: {', '.join(t.goal for t in wave)}")
            done_tasks = [t for t in state.tasks if t.status == TaskStatus.DONE]
            await asyncio.gather(*[
                self._run_task(
                    t, self.ctx.build_context(goal, t, done_tasks),
                    make_worker, make_evaluator, state, trace, sem, review_lock, control,
                )
                for t in wave
            ])

        # 3) SYNTHESIZE -------------------------------------------------------
        state.final_output = self._synthesize(state)

        # 4) FINAL human checkpoint (+ one bounded re-open of the weakest task)
        if control.get("abort"):
            state.stopped_reason = control["abort"]
        elif self.cfg.hitl.interactive and self.cfg.hitl.final:
            decision = await self._review(review_lock, self.reviewer.review_final, state)
            if decision.action is ReviewAction.ABORT:
                state.stopped_reason = decision.note or "final rejected by human"
            elif decision.action is ReviewAction.REVISE:
                await self._reopen_weakest(decision.feedback, state, trace,
                                           make_worker, make_evaluator, sem, review_lock, control)
                state.final_output = self._synthesize(state)
                state.stopped_reason = state.budget.exceeded(state.usage) or "completed (revised)"
            else:
                state.stopped_reason = "completed"
        if not state.stopped_reason:
            state.stopped_reason = state.budget.exceeded(state.usage) or "completed"

        trace.event(
            "run_end", reason=state.stopped_reason,
            in_tokens=state.usage.input_tokens, out_tokens=state.usage.output_tokens,
            calls=state.usage.calls,
        )
        self._persist(state)
        return state

    # -- helpers -------------------------------------------------------------
    async def _reopen_weakest(self, feedback, state, trace, make_worker,
                              make_evaluator, sem, review_lock, control) -> None:
        """Re-run the lowest-scoring task once with the human's final feedback."""
        candidates = [t for t in state.tasks if t.status != TaskStatus.FAILED]
        if not candidates:
            return
        target = min(candidates, key=lambda t: (t.score if t.score is not None else 0.0))
        target.feedback = (feedback or "Improve this result.")
        target.attempts = 0  # grant a fresh revision round for the human ask
        target.status = TaskStatus.PENDING
        self._say(f"\nRe-opening weakest subtask on human request: {target.goal}")
        done_tasks = [t for t in state.tasks if t.status == TaskStatus.DONE and t is not target]
        ctx = self.ctx.build_context(state.goal, target, done_tasks)
        await self._run_task(target, ctx, make_worker, make_evaluator,
                             state, trace, sem, review_lock, control)

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
