"""CLI entry point.

    python -m ai.run "Build a CSV-to-JSON converter with tests"
    AI_FORCE_MODEL=mock:mock python -m ai.run "dry run"        # no keys / no network
    python -m ai.run --approve "risky task"                    # gate the plan only
    python -m ai.run --interactive "refactor module X"         # gate plan + results + final
    python -m ai.run --interactive --results always "…"        # review every result
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# Optional: auto-load a .env file if python-dotenv is installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

from .config import load_config
from .loop import AsyncOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Async multi-agent harness (planner / worker / evaluator) "
        "with human-in-the-loop checkpoints and sub-agent context isolation."
    )
    parser.add_argument("goal", nargs="+", help="The high-level goal to accomplish.")
    parser.add_argument("--config", default=None, help="Path to a config.yaml.")
    parser.add_argument(
        "--interactive", action="store_true",
        help="Turn on human checkpoints (plan + results + final).",
    )
    parser.add_argument(
        "--approve", action="store_true",
        help="Interactive plan checkpoint only (shorthand).",
    )
    parser.add_argument(
        "--results", choices=["off", "on_fail", "always"], default=None,
        help="When to ask about a subtask result (implies --interactive).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress lines.")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.approve:
        cfg.hitl.mode = "interactive"
        cfg.hitl.plan = True
    if args.results is not None:
        cfg.hitl.mode = "interactive"
        cfg.hitl.results = args.results
    if args.interactive:
        cfg.hitl.mode = "interactive"
        cfg.hitl.plan = True
        cfg.hitl.final = True
        if args.results is None and cfg.hitl.results == "off":
            cfg.hitl.results = "on_fail"

    goal = " ".join(args.goal)
    orch = AsyncOrchestrator(cfg, show_progress=not args.quiet)
    state = asyncio.run(orch.run(goal))

    line = "=" * 70
    print(f"\n{line}")
    print(f"RUN {state.id}  |  {state.stopped_reason}")
    print(
        f"tokens: in={state.usage.input_tokens} "
        f"out={state.usage.output_tokens} calls={state.usage.calls}"
    )
    print(line)
    print(state.final_output or "(no output)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
