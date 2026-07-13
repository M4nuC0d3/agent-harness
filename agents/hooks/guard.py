#!/usr/bin/env python3
"""PreToolUse guard — the deterministic layer under the model.

Instructions in AGENTS.md are context: they lower the *probability* of an
accident. This hook lowers the *possibility*. It runs before the permission
check on every matching tool call, so a `deny` here holds even in bypass mode
(`--dangerously-skip-permissions`). A hook can tighten policy, never loosen it:
an `allow` from a hook cannot override a `deny` rule in settings.

Contract (Claude Code / Agent SDK hooks):
  * event JSON arrives on stdin (tool_name, tool_input, session_id, …)
  * exit 0            -> no decision; the normal permission flow applies
  * exit 2 + stderr   -> BLOCK the tool call; stderr is fed back to the model
  * exit 0 + stdout JSON -> structured decision (allow / deny / ask)
  Never mix the two: on exit 2 any stdout JSON is ignored, and exit 1 blocks
  nothing (the classic footgun). This hook uses exit 2 + stderr for blocks and
  stdout JSON for `ask`.

Config comes from policy.json next to this file, generated from
agents/policy.toml. Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = HERE / "policy.json"

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def block(reason: str) -> None:
    """Block the tool call. stderr goes back to the model as an error."""
    print(f"BLOCKED by agents/policy.toml: {reason}", file=sys.stderr)
    sys.exit(2)


def ask(reason: str) -> None:
    """Escalate to the human via the normal permission prompt."""
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
    stops the agent: the human keeps believing they are protected. If the policy
    is missing or unparseable, block everything and say exactly how to fix it."""
    try:
        return json.loads(POLICY.read_text(encoding="utf-8"))
    except FileNotFoundError:
        block(
            f"enforcement policy not found at {POLICY}. "
            "Run `python agents/sync.py` to regenerate it, or remove the "
            "PreToolUse hook from .claude/settings.json to disable enforcement."
        )
    except (json.JSONDecodeError, OSError) as exc:
        block(f"enforcement policy at {POLICY} is unreadable ({exc}). Refusing to run unguarded.")
    return {}  # unreachable; keeps type checkers happy


def matches(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return p
    return None


def check_budget(policy: dict, session_id: str) -> None:
    """Per-session tool-call ceiling: a stop condition the model cannot ignore."""
    ceiling = int(policy.get("budget", {}).get("max_tool_calls_per_session", 0))
    if ceiling <= 0 or not session_id:
        return
    state_dir = Path(policy.get("budget", {}).get("state_dir", ".agent"))
    counter = state_dir / "tool_calls.json"

    try:
        counts = json.loads(counter.read_text(encoding="utf-8"))
        if not isinstance(counts, dict):
            counts = {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        counts = {}

    n = int(counts.get(session_id, 0)) + 1
    counts[session_id] = n
    # Keep the file from growing without bound across many sessions.
    if len(counts) > 50:
        counts = dict(list(counts.items())[-50:])
        counts[session_id] = n

    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        counter.write_text(json.dumps(counts), encoding="utf-8")
    except OSError:
        return  # read-only fs: don't block on bookkeeping

    if n > ceiling:
        block(
            f"tool-call budget exhausted ({n} > {ceiling} this session). "
            "Stop and report progress to the human instead of continuing."
        )


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        allow_silently()

    policy = load_policy()
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}

    check_budget(policy, str(event.get("session_id", "")))

    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if hit := matches(policy.get("bash", {}).get("deny", []), cmd):
            block(f"command matches a denied pattern ({hit}): {cmd[:160]}")
        if hit := matches(policy.get("bash", {}).get("ask", []), cmd):
            ask(f"Irreversible or side-effecting command (matched {hit}). Approve?")

    elif tool in WRITE_TOOLS:
        path = str(tool_input.get("file_path", "") or tool_input.get("path", ""))
        if hit := matches(policy.get("files", {}).get("protected", []), path):
            block(f"'{path}' is a protected path (matched {hit}). Writes are refused.")

    allow_silently()


if __name__ == "__main__":
    main()
