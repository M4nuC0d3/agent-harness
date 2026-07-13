#!/usr/bin/env python3
"""PreToolUse hook — only what permission rules and the sandbox cannot express.

Layering (as Anthropic documents it):

  sandbox      OS-level isolation of Bash and its children. The boundary. Holds
               even when a prompt injection bypasses the model's judgment.
  permissions  declarative allow/ask/deny. Reliable for paths, domains, tools.
  this hook    a session budget, plus an OPT-IN accident catcher.

What this hook deliberately does NOT do:

  * Guard file writes. `Write`/`Edit` expose exactly the same surface to a hook
    as to an `Edit(./.env)` deny rule, so the rule is the better tool. Neither
    covers a subprocess that opens the file itself — only the sandbox does.
  * Pretend to be a security boundary. The bash denylist below is regex over a
    command string. `devbox run rm -rf ~`, `eval "$(...)"`, or a two-line Python
    script defeat it. It catches accidents, not adversaries.

Contract:
  * event JSON on stdin (tool_name, tool_input, session_id, …)
  * exit 0              -> no decision; normal permission flow applies
  * exit 2 + stderr     -> BLOCK; stderr goes back to the model
  * exit 0 + stdout JSON-> structured decision (allow / deny / ask)
  Never mix: on exit 2 stdout JSON is ignored, and exit 1 blocks nothing.

Config: policy.json beside this file, generated from agents/policy.toml.
Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = HERE / "policy.json"


def block(reason: str) -> None:
    print(f"BLOCKED by agents/policy.toml: {reason}", file=sys.stderr)
    sys.exit(2)


def ask(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def allow_silently() -> None:
    sys.exit(0)  # no decision -> normal permission flow


def load_policy() -> dict:
    """Fail CLOSED. A guard that silently stops guarding is worse than one that
    stops the agent: the human keeps believing they are protected."""
    try:
        return json.loads(POLICY.read_text(encoding="utf-8"))
    except FileNotFoundError:
        block(
            f"enforcement policy not found at {POLICY}. Run `python agents/sync.py` "
            "to regenerate it, or remove the PreToolUse hook from .claude/settings.json."
        )
    except (json.JSONDecodeError, OSError) as exc:
        block(f"enforcement policy at {POLICY} is unreadable ({exc}). Refusing to run unguarded.")
    return {}  # unreachable


def matches(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return p
    return None


def check_budget(policy: dict, session_id: str) -> None:
    """Per-session tool-call ceiling — a stop condition the model cannot ignore.
    There is no permission rule for 'how many calls have you made'."""
    budget = policy.get("budget", {})
    ceiling = int(budget.get("max_tool_calls_per_session", 0))
    if ceiling <= 0 or not session_id:
        return
    state_dir = Path(budget.get("state_dir", ".agent"))
    counter = state_dir / "tool_calls.json"

    try:
        counts = json.loads(counter.read_text(encoding="utf-8"))
        if not isinstance(counts, dict):
            counts = {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        counts = {}

    n = int(counts.get(session_id, 0)) + 1
    counts[session_id] = n
    if len(counts) > 50:  # keep the file bounded across many sessions
        counts = dict(list(counts.items())[-50:])
        counts[session_id] = n

    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        counter.write_text(json.dumps(counts), encoding="utf-8")
    except OSError:
        return  # read-only fs: never block on bookkeeping

    if n > ceiling:
        block(
            f"tool-call budget exhausted ({n} > {ceiling} this session). "
            "Stop and report progress to the human instead of continuing."
        )


def check_accidents(policy: dict, tool: str, tool_input: dict) -> None:
    """Opt-in denylist. See the module docstring: accidents, not adversaries."""
    cfg = policy.get("bash", {})
    if not cfg.get("enabled", False) or tool != "Bash":
        return
    cmd = str(tool_input.get("command", ""))
    if hit := matches(cfg.get("deny", []), cmd):
        block(
            f"command matches a denied pattern ({hit}): {cmd[:140]}. "
            "This is an accident catcher, not a boundary — if you meant it, ask the human."
        )


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        allow_silently()

    policy = load_policy()
    check_budget(policy, str(event.get("session_id", "")))
    check_accidents(policy, event.get("tool_name", ""), event.get("tool_input", {}) or {})
    allow_silently()


if __name__ == "__main__":
    main()
