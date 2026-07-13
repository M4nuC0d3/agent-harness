#!/usr/bin/env python3
"""PreToolUse hook — only what permission rules and the sandbox cannot express.

Layering (as Anthropic documents it):

  sandbox      OS-level isolation of Bash and its children. THE boundary. Holds
               even when a prompt injection bypasses the model's judgment.
  permissions  declarative allow/ask/deny in .claude/settings.json. Reliable for
               paths, domains and whole tools.
  this hook    a session budget, plus an opt-in accident catcher.

What this hook deliberately does NOT do:

  * Guard file writes. `Write`/`Edit` expose the same surface to a hook as to an
    `Edit(./.env)` deny rule, so the rule is the better tool. Neither covers a
    subprocess that opens the file itself — only the sandbox does.
  * Pretend to be a security boundary. ACCIDENT_PATTERNS below is regex over a
    command string. `devbox run rm -rf ~`, `eval "$(...)"`, or a two-line Python
    script defeat it. It catches accidents, not adversaries. Never let it be the
    reason you skip the sandbox.

Contract:
  * event JSON on stdin (tool_name, tool_input, session_id, …)
  * exit 0               -> no decision; the normal permission flow applies
  * exit 2 + stderr      -> BLOCK; stderr goes back to the model
  * exit 0 + stdout JSON -> structured decision
  Never mix: on exit 2 stdout JSON is ignored, and exit 1 blocks nothing.

Stdlib only. Config is right here — no second file to keep in sync.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────

# A stop condition the model cannot ignore. No permission rule can count calls.
# 0 disables.
MAX_TOOL_CALLS_PER_SESSION = 400
STATE_DIR = Path(".agent")

# Opt-in accident catcher. NOT a security mechanism — see the module docstring.
# Set to False if you have the sandbox and prefer fewer moving parts.
ACCIDENT_CATCHER = True

# Deny only catastrophic targets. `rm -rf node_modules` is handled by the
# `Bash(rm -rf:*)` *ask* rule in settings.json: a guard that blocks everyday
# work gets switched off, and then it protects nothing.
ACCIDENT_PATTERNS = [
    r"\brm\s+-\S*[rf]\S*\s+\*",                 # rm -rf *
    r"\brm\b[^;&|]*\s(/|~|\$HOME)/?(\s|$)",     # rm whose target is / ~ $HOME
    r"git\s+push\b.*--force(-with-lease)?\b.*\b(main|master)\b",
    r"--no-verify",                             # skipping hooks / CI checks
    r"\bchmod\s+777\b",
    r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE)\b",
    r"\bmkfs\b|\bdd\s+if=.*of=/dev/",
    r"curl\b[^|]*\|\s*(ba)?sh",                 # curl | sh
    r">\s*\.env",                               # clobbering secrets
]

# ───────────────────────────────────────────────────────────────────────────


def block(reason: str) -> None:
    print(f"BLOCKED by .claude/hooks/guard.py: {reason}", file=sys.stderr)
    sys.exit(2)


def allow_silently() -> None:
    sys.exit(0)  # no decision -> normal permission flow


def check_budget(session_id: str) -> None:
    if MAX_TOOL_CALLS_PER_SESSION <= 0 or not session_id:
        return
    counter = STATE_DIR / "tool_calls.json"
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
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        counter.write_text(json.dumps(counts), encoding="utf-8")
    except OSError:
        return  # read-only fs: never block on bookkeeping

    if n > MAX_TOOL_CALLS_PER_SESSION:
        block(
            f"tool-call budget exhausted ({n} > {MAX_TOOL_CALLS_PER_SESSION} this "
            "session). Stop and report progress to the human instead of continuing."
        )


def check_accidents(tool: str, tool_input: dict) -> None:
    if not ACCIDENT_CATCHER or tool != "Bash":
        return
    cmd = str(tool_input.get("command", ""))
    for pattern in ACCIDENT_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            block(
                f"command matches a denied pattern ({pattern}): {cmd[:130]}. "
                "This is an accident catcher, not a boundary — if you meant it, ask."
            )


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        allow_silently()

    check_budget(str(event.get("session_id", "")))
    check_accidents(event.get("tool_name", ""), event.get("tool_input", {}) or {})
    allow_silently()


if __name__ == "__main__":
    main()
