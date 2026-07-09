"""Async multi-agent harness: a planner/coordinator that delegates to worker
sub-agents, gates their output through an evaluator, isolates each sub-agent's
context, and adds human-in-the-loop checkpoints.

Choose which model each agent runs on via config.yaml — including whether a role
goes over an API key (billed per token) or a vendor agent CLI (drawing on your
subscription). See ai/providers/.
"""
from .config import HarnessConfig, HitlConfig, load_config
from .context import ContextConfig, ContextManager
from .hitl import AutoReviewer, CLIReviewer, ReviewAction, ReviewDecision, Reviewer
from .loop import AsyncOrchestrator, run_goal
from .providers import Provider, get_provider, known_providers, register_provider
from .schemas import ContextPolicy, ModelSpec, RunState, Task

__all__ = [
    "AsyncOrchestrator",
    "run_goal",
    "HarnessConfig",
    "HitlConfig",
    "ContextConfig",
    "ContextManager",
    "ContextPolicy",
    "Reviewer",
    "AutoReviewer",
    "CLIReviewer",
    "ReviewAction",
    "ReviewDecision",
    "Provider",
    "get_provider",
    "register_provider",
    "known_providers",
    "ModelSpec",
    "RunState",
    "Task",
]
