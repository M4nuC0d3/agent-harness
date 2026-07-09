"""CLI entry point.

    python -m ai.run "Build a CSV-to-JSON converter with tests"
    AI_FORCE_MODEL=mock:mock python -m ai.run "dry run"     # no keys / no network
    python -m ai.run --approve "risky task"                 # ask before executing
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
        description="Async multi-agent harness (planner / worker / evaluator)."
    )
    parser.add_argument("goal", nargs="+", help="The high-level goal to accomplish.")
    parser.add_argument("--config", default=None, help="Path to a config.yaml.")
    parser.add_argument(
        "--approve", action="store_true", help="Require human approval of the plan."
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.approve:
        cfg.require_human_approval = True

    goal = " ".join(args.goal)
    state = asyncio.run(AsyncOrchestrator(cfg).run(goal))

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
