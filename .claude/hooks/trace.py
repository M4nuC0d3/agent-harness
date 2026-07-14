#!/usr/bin/env python3
"""PostToolUse trace — deterministic observability.

Appends one JSON line per tool call to `.agent/trace.jsonl`. Because it is a
hook, it runs on *every* matching call regardless of what the model decides to
report; a "keep a trace" instruction in AGENTS.md would not.

PostToolUse cannot undo a call, so this never blocks: it exits 0 unconditionally
and stays silent. A failing trace hook must never break a session.

Read it back with:
    jq -r '"\\(.ts) \\(.tool) \\(.summary)"' .agent/trace.jsonl
    jq -s 'group_by(.tool) | map({tool: .[0].tool, calls: length})' .agent/trace.jsonl

Stdlib only.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(".agent")
TRACE = STATE_DIR / "trace.jsonl"
MAX_SUMMARY = 200


def summarize(event: dict) -> str:
    """One short, greppable line — never the full payload.

    Reads the command from either shape: `tool_input.command` (Claude Code,
    Codex) or top-level `command` (Cursor afterShellExecution).
    """
    tool_input = event.get("tool_input") or {}
    cmd = tool_input.get("command") or event.get("command")
    if cmd:
        return str(cmd)[:MAX_SUMMARY]
    for key in ("file_path", "path", "url", "pattern", "query"):
        if key in tool_input:
            return f"{key}={str(tool_input[key])[:MAX_SUMMARY]}"
        if key in event:
            return f"{key}={str(event[key])[:MAX_SUMMARY]}"
    return ""


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # never break the session on a malformed payload

    # Cursor's shell hook sends no tool_name but does send a top-level command.
    has_cmd = bool((event.get("tool_input") or {}).get("command") or event.get("command"))
    tool = event.get("tool_name") or ("Bash" if has_cmd else "")
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": event.get("session_id", ""),
        "agent": event.get("agent_type") or event.get("subagent_type") or "main",
        "tool": tool,
        "summary": summarize(event),
    }

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with TRACE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass  # read-only fs or no space: silently continue

    sys.exit(0)


if __name__ == "__main__":
    main()
