"""Load and validate config.yaml into typed objects.

The config maps each agent *role* to a ModelSpec. That mapping is the whole
point of "steuerbar welche Modelle" — change YAML (or one env var), not code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .schemas import Budget, ModelSpec

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")


@dataclass
class HarnessConfig:
    models: dict[str, ModelSpec]  # role -> ModelSpec
    budget: Budget
    pass_threshold: float = 0.7
    max_concurrency: int = 4
    require_human_approval: bool = False
    runs_dir: str = "runs"

    def model_for(self, role: str) -> ModelSpec:
        """ModelSpec for a role, falling back to the required 'default' role."""
        return self.models.get(role) or self.models["default"]


def _apply_env_override(models: dict[str, ModelSpec]) -> None:
    """Global override: AI_FORCE_MODEL="provider:model" forces every agent
    onto one model. Handy for cost ceilings, compliance, or a dry run
    (AI_FORCE_MODEL="mock:mock"). Mirrors Claude Code's
    CLAUDE_CODE_SUBAGENT_MODEL, which does the same for native subagents.
    """
    forced = os.environ.get("AI_FORCE_MODEL")
    if not forced:
        return
    provider, _, model = forced.partition(":")
    for spec in models.values():
        if provider:
            spec.provider = provider
        if model:
            spec.model = model


def load_config(path: Optional[os.PathLike | str] = None) -> HarnessConfig:
    if yaml is None:
        raise RuntimeError("PyYAML is required: pip install pyyaml")
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    raw_models = data.get("models", {})
    models = {role: ModelSpec.from_dict(spec) for role, spec in raw_models.items()}
    if "default" not in models:
        raise ValueError("config.yaml 'models' must define a 'default' role")
    _apply_env_override(models)

    b = data.get("budget", {})
    budget = Budget(
        max_tokens=int(b.get("max_tokens", 200_000)),
        max_wall_seconds=float(b.get("max_wall_seconds", 600)),
        max_iterations=int(b.get("max_iterations", 20)),
        max_revisions_per_task=int(b.get("max_revisions_per_task", 2)),
    )

    loop = data.get("loop", {})
    return HarnessConfig(
        models=models,
        budget=budget,
        pass_threshold=float(loop.get("pass_threshold", 0.7)),
        max_concurrency=int(loop.get("max_concurrency", 4)),
        require_human_approval=bool(loop.get("require_human_approval", False)),
        runs_dir=str(loop.get("runs_dir", "runs")),
    )
