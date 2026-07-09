"""Context isolation for sub-agents.

Anthropic's context-engineering guidance (see ai/README.md for the link) is that
a sub-agent should start with a *clean, minimal* context window — only what its
subtask needs — and hand back a short, distilled summary rather than its full
working transcript. That keeps the coordinator's context full of conclusions
instead of raw output, which measurably improves multi-step performance.

This module builds the scoped context a worker is given and compacts a worker's
output into the summary that flows downstream.

    build_context(goal, task, done_tasks)  -> the small brief the worker sees
    compact(full_result, worker_summary)   -> the ~summary_target the coord keeps
"""
from __future__ import annotations

from dataclasses import dataclass

from .schemas import ContextPolicy, Task
from .utils import approx_tokens, truncate_tokens


@dataclass
class ContextConfig:
    """Knobs for how tightly sub-agent context is scoped."""

    policy: ContextPolicy = ContextPolicy.SCOPED
    # Target size of each sub-agent's distilled summary (Anthropic reports
    # ~1-2k tokens works well; default smaller since our subtasks are small).
    summary_target_tokens: int = 400
    # Hard cap on the assembled brief handed to a worker.
    max_context_tokens: int = 2000

    @classmethod
    def from_dict(cls, d: dict) -> "ContextConfig":
        return cls(
            policy=ContextPolicy(str(d.get("policy", "scoped")).lower()),
            summary_target_tokens=int(d.get("summary_target_tokens", 400)),
            max_context_tokens=int(d.get("max_context_tokens", 2000)),
        )


class ContextManager:
    """Decides what a sub-agent sees and how its output is compacted."""

    def __init__(self, config: ContextConfig | None = None) -> None:
        self.cfg = config or ContextConfig()

    # -- inbound: what the worker is allowed to see --------------------------
    def build_context(self, goal: str, task: Task, done: list[Task]) -> str:
        """Assemble the minimal brief for ``task`` given already-finished tasks.

        Only *summaries* of upstream tasks are included (never their full
        output), and the whole thing is capped at ``max_context_tokens``.
        """
        policy = self.cfg.policy
        if policy is ContextPolicy.NONE:
            return ""
        if policy is ContextPolicy.MINIMAL:
            return f"Overall goal: {goal}"

        by_id = {t.id: t for t in done}
        # SCOPED: only this task's declared dependencies. If it declares none,
        # fall back to every finished task so a flat plan still shares context.
        if policy is ContextPolicy.SCOPED:
            upstream = [by_id[d] for d in task.depends_on if d in by_id] or done
            use_summary = True
        else:  # FULL
            upstream = done
            use_summary = False

        parts = [f"Overall goal: {goal}"]
        for t in upstream:
            snippet = (t.summary if use_summary else t.result) or t.summary or ""
            if snippet:
                parts.append(f"From an earlier subtask ({t.goal}):\n{snippet}")
        brief = "\n\n".join(parts)
        return truncate_tokens(brief, self.cfg.max_context_tokens)

    # -- outbound: compact a worker result into a downstream summary ---------
    def compact(self, full_result: str, worker_summary: str = "") -> str:
        """Return the short summary the coordinator keeps for this task.

        Prefers the summary the worker produced itself (its own compaction);
        otherwise deterministically truncates the full result as a fallback.
        """
        target = self.cfg.summary_target_tokens
        if worker_summary:
            return truncate_tokens(worker_summary, target)
        return truncate_tokens(full_result, target)

    def would_truncate(self, text: str) -> bool:
        return approx_tokens(text) > self.cfg.max_context_tokens
