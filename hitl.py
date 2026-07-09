"""Human-in-the-loop checkpoints.

Anthropic's guidance on agents: let a human "pause for feedback at checkpoints
or when encountering blockers", and keep hard stopping conditions. This module
turns that into concrete, swappable gates the orchestrator calls at three points:

    review_plan    after planning, before any work starts
    review_result  after the evaluator scores a subtask
    review_final   before the synthesized answer is accepted

Plus ``confirm(...)`` — a yes/no gate to put in front of irreversible actions
(deletes, force-push, migrations, side-effecting tool calls).

Two implementations ship here:
    AutoReviewer  approves everything (non-interactive default / CI / tests)
    CLIReviewer   asks the human on the terminal; falls back to approve if
                  stdin is not interactive (EOF), so it never hangs a pipe.

Swap in your own (a web UI, Slack approval, a queue) by subclassing Reviewer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .schemas import Evaluation, RunState, Task


class ReviewAction(str, Enum):
    APPROVE = "approve"   # accept as-is and continue
    REVISE = "revise"     # send back with feedback (re-plan / re-run)
    EDIT = "edit"         # human replaced the content (plan only)
    ABORT = "abort"       # stop the whole run


@dataclass
class ReviewDecision:
    action: ReviewAction
    feedback: Optional[str] = None      # guidance for REVISE
    tasks: Optional[list[Task]] = None  # replacement plan for EDIT
    note: Optional[str] = None

    # convenience constructors
    @classmethod
    def approve(cls) -> "ReviewDecision":
        return cls(ReviewAction.APPROVE)

    @classmethod
    def revise(cls, feedback: str) -> "ReviewDecision":
        return cls(ReviewAction.REVISE, feedback=feedback)

    @classmethod
    def edit(cls, tasks: list[Task]) -> "ReviewDecision":
        return cls(ReviewAction.EDIT, tasks=tasks)

    @classmethod
    def abort(cls, note: str = "aborted by human") -> "ReviewDecision":
        return cls(ReviewAction.ABORT, note=note)


class Reviewer:
    """Base reviewer. The default behaviour is fully automatic (approve all),
    so a run with HITL enabled but this reviewer still completes unattended."""

    def review_plan(self, tasks: list[Task]) -> ReviewDecision:
        return ReviewDecision.approve()

    def review_result(self, task: Task, evaluation: Evaluation) -> ReviewDecision:
        return ReviewDecision.approve()

    def review_final(self, state: RunState) -> ReviewDecision:
        return ReviewDecision.approve()

    def confirm(self, description: str) -> bool:
        return True


class AutoReviewer(Reviewer):
    """Explicit name for the non-interactive default."""


@dataclass
class CLIReviewer(Reviewer):
    """Interactive terminal reviewer. Reads single-key choices from stdin.

    On EOFError (stdin is a non-interactive pipe) every gate auto-approves, so
    enabling HITL never deadlocks an automated run.
    """

    max_preview_chars: int = 600

    def _ask(self, prompt: str, choices: str, default: str) -> str:
        try:
            raw = input(f"{prompt} [{choices}] (default {default}): ").strip().lower()
        except EOFError:
            print(f"  (non-interactive stdin -> auto '{default}')")
            return default
        return raw or default

    def _read_multiline(self, prompt: str) -> list[str]:
        print(prompt + " (one per line; blank line to finish)")
        lines: list[str] = []
        while True:
            try:
                line = input("  > ").strip()
            except EOFError:
                break
            if not line:
                break
            lines.append(line)
        return lines

    # -- gates ---------------------------------------------------------------
    def review_plan(self, tasks: list[Task]) -> ReviewDecision:
        print("\n--- HUMAN CHECKPOINT: plan ---")
        for i, t in enumerate(tasks, 1):
            deps = f"  (after: {', '.join(t.depends_on)})" if t.depends_on else ""
            print(f"  {i}. {t.goal}{deps}")
        choice = self._ask("Approve plan?", "a=approve / e=edit / r=revise / b=abort", "a")
        if choice.startswith("a"):
            return ReviewDecision.approve()
        if choice.startswith("e"):
            new = self._read_multiline("Enter the replacement subtasks")
            return ReviewDecision.edit([Task(goal=g) for g in new]) if new else ReviewDecision.approve()
        if choice.startswith("r"):
            try:
                fb = input("  Feedback for the planner: ").strip()
            except EOFError:
                fb = ""
            return ReviewDecision.revise(fb or "Revise the plan.")
        return ReviewDecision.abort("plan rejected by human")

    def review_result(self, task: Task, evaluation: Evaluation) -> ReviewDecision:
        verdict = "PASS" if evaluation.passed else "FAIL"
        print(f"\n--- HUMAN CHECKPOINT: result of '{task.goal}' ---")
        print(f"  evaluator: {verdict}  score={evaluation.score:.2f}")
        if evaluation.feedback:
            print(f"  feedback: {evaluation.feedback[:self.max_preview_chars]}")
        preview = (task.result or "")[:self.max_preview_chars]
        print(f"  result preview:\n    {preview.replace(chr(10), chr(10) + '    ')}")
        choice = self._ask("Accept this result?", "a=accept / r=revise / b=abort", "a")
        if choice.startswith("a"):
            return ReviewDecision.approve()
        if choice.startswith("r"):
            try:
                fb = input("  Extra guidance (blank = reuse evaluator feedback): ").strip()
            except EOFError:
                fb = ""
            return ReviewDecision.revise(fb or evaluation.feedback or "Please revise.")
        return ReviewDecision.abort("result rejected by human")

    def review_final(self, state: RunState) -> ReviewDecision:
        print("\n--- HUMAN CHECKPOINT: final output ---")
        preview = (state.final_output or "")[: self.max_preview_chars * 2]
        print(preview)
        choice = self._ask("Accept final output?", "a=accept / r=request changes / b=abort", "a")
        if choice.startswith("a"):
            return ReviewDecision.approve()
        if choice.startswith("r"):
            try:
                fb = input("  What should change? ").strip()
            except EOFError:
                fb = ""
            return ReviewDecision.revise(fb or "Please improve the weakest subtask.")
        return ReviewDecision.abort("final output rejected by human")
