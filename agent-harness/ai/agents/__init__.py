"""Sub-agents. Each one is a small class over BaseAgent with its own
system prompt and its own ModelSpec (so each can run on a different model)."""
from .base import BaseAgent
from .evaluator import EvaluatorAgent
from .planner import PlannerAgent
from .worker import WorkerAgent

__all__ = ["BaseAgent", "PlannerAgent", "WorkerAgent", "EvaluatorAgent"]
