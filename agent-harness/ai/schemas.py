"""Core data structures shared across the harness.

Everything here is a plain dataclass so a whole run can be serialized to JSON
for checkpointing, resuming, or feeding into a trace viewer.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_REVISION = "needs_revision"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Usage:
    """Token accounting, aggregated across every model call in a run."""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    """Normalized response every provider returns, regardless of vendor."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    raw: Any = None


@dataclass
class ModelSpec:
    """Which model a given agent should use. THIS is the steerable knob.

    provider: "anthropic" | "openai" | "google" | "local" | "mock" | <custom>
    """

    provider: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 4096

    @classmethod
    def from_dict(cls, d: dict) -> "ModelSpec":
        return cls(
            provider=d["provider"],
            model=d["model"],
            temperature=float(d.get("temperature", 0.2)),
            max_tokens=int(d.get("max_tokens", 4096)),
        )

    def label(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class Task:
    """One unit of work produced by the planner and executed by a worker."""

    goal: str
    id: str = field(default_factory=lambda: _new_id("task"))
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    result: Optional[str] = None
    feedback: Optional[str] = None  # last evaluator feedback, fed back on revision
    score: Optional[float] = None
    attempts: int = 0
    error: Optional[str] = None


@dataclass
class Evaluation:
    """The critic's verdict on a worker result."""

    passed: bool
    score: float  # 0.0 - 1.0
    feedback: str
    raw: Any = None


@dataclass
class Budget:
    """Hard limits. The loop stops as soon as any of these is exceeded.

    This is what guarantees termination: no combination of agents can run
    forever, because tokens / wall-clock / iterations are all capped.
    """

    max_tokens: int = 200_000
    max_wall_seconds: float = 600.0
    max_iterations: int = 20  # total agent invocations across the whole run
    max_revisions_per_task: int = 2  # evaluator -> worker retry rounds

    started_at: float = field(default_factory=time.monotonic)
    iterations: int = 0

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def exceeded(self, usage: Usage) -> Optional[str]:
        """Return a human-readable reason if a limit is hit, else None."""
        if usage.total_tokens >= self.max_tokens:
            return f"token budget exceeded ({usage.total_tokens}/{self.max_tokens})"
        if self.elapsed() >= self.max_wall_seconds:
            return f"time budget exceeded ({self.elapsed():.0f}s/{self.max_wall_seconds:.0f}s)"
        if self.iterations >= self.max_iterations:
            return f"iteration budget exceeded ({self.iterations}/{self.max_iterations})"
        return None


@dataclass
class RunState:
    """Everything about a single run. Serializable for checkpoint/resume."""

    goal: str
    id: str = field(default_factory=lambda: _new_id("run"))
    tasks: list[Task] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    budget: Budget = field(default_factory=Budget)
    final_output: Optional[str] = None
    stopped_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "tasks": [asdict(t) for t in self.tasks],
            "usage": asdict(self.usage),
            "final_output": self.final_output,
            "stopped_reason": self.stopped_reason,
        }
