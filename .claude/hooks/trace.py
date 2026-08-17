#!/usr/bin/env python3
"""PostToolUse trace — deterministic observability.

Appends one JSON line per tool call to `.agent/trace.jsonl`. Because it is a
hook, it runs on *every* matching call regardless of what the model decides to
report; a "keep a trace" instruction in AGENTS.md would not.

PostToolUse cannot undo a call, so this never blocks: it exits 0 unconditionally
and stays silent. A failing trace hook must never break a session.

Each line carries a small, versioned envelope so a trace stays readable by a
consumer that does not know the version that wrote it:

    schema   format version of this line. Bump it when a field changes meaning.
    event    what happened. Only "tool_call" today; other kinds may share the
             file later, so filter on it rather than assuming.
    harness  the harness version that produced the line, from
             .claude-plugin/plugin.json — "unknown" when it cannot be read.
    args     the tool_input KEY NAMES, never their values. Enough to see which
             parameters a call used without persisting secrets or payloads.

The five original fields (ts, session, agent, tool, summary) are unchanged, so
existing jq over old traces keeps working. `session` is the run identifier; no
second one is invented here.

Read it back with:
    jq -r '"\\(.ts) \\(.tool) \\(.summary)"' .agent/trace.jsonl
    jq -s 'group_by(.tool) | map({tool: .[0].tool, calls: length})' .agent/trace.jsonl
    jq -s 'group_by(.harness) | map({harness: .[0].harness, calls: length})' .agent/trace.jsonl

Stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(".agent")
TRACE = STATE_DIR / "trace.jsonl"
MAX_SUMMARY = 200

# The trace is append-only and nothing ever pruned it: on a long-running project
# it grows without bound, and the file that is supposed to make a session
# reviewable becomes the one nobody opens. Roll it over instead — one previous
# generation is kept as trace.jsonl.1 and the older one is dropped. Set to 0 to
# disable rotation and keep the original unbounded behaviour.
MAX_TRACE_BYTES = 5 * 1024 * 1024

# Bump when a field changes meaning — not when one is added. Readers that
# filter on a known schema keep working; readers that ignore it also keep
# working, which is why additions do not bump.
SCHEMA = 1


def harness_version() -> str:
    """The version that produced this line, from the plugin manifest.

    This is the field that makes a trace comparable across harness changes: a
    success rate is meaningless without knowing which harness produced it.

    Resolved from CLAUDE_PLUGIN_ROOT when installed as a plugin, otherwise
    relative to this file (a repo checkout or a `cp -r` install). Every failure
    path returns "unknown" — an unlabelled trace line is worth far more than a
    hook that raises. A copy-install without `.claude-plugin/` is the normal
    case for "unknown", not an error.
    """
    roots = []
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        roots.append(Path(plugin_root))
    roots.append(Path(__file__).resolve().parents[2])

    for root in roots:
        try:
            raw = (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError):
            continue
        version = data.get("version") if isinstance(data, dict) else None
        if isinstance(version, str) and version:
            return version
    return "unknown"


def input_keys(event: dict) -> list[str]:
    """Parameter NAMES of the call — deliberately never their values.

    `summary` already records a command or one identifying path. This adds the
    shape of the call (which parameters were set) without turning the trace
    into a store of tool payloads and secrets.
    """
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    return sorted(str(key) for key in tool_input)


def summarize(event: dict) -> str:
    """One short, greppable line — never the full payload.

    Reads the command from either shape: `tool_input.command` (Claude Code,
    Codex) or a top-level `command`.
    """
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    cmd = tool_input.get("command") or event.get("command")
    if cmd:
        return str(cmd)[:MAX_SUMMARY]
    for key in ("file_path", "path", "url", "pattern", "query"):
        if key in tool_input:
            return f"{key}={str(tool_input[key])[:MAX_SUMMARY]}"
        if key in event:
            return f"{key}={str(event[key])[:MAX_SUMMARY]}"
    return ""


def _rotate_if_large() -> None:
    """Roll trace.jsonl over to trace.jsonl.1 once it passes MAX_TRACE_BYTES.

    os.replace is atomic, so a concurrent reader sees either generation whole,
    never a truncated file. Every failure is swallowed: losing a rotation is a
    housekeeping problem, breaking a session is not. Rotation is checked before
    the append rather than after, so the cap is a floor — a line may push the
    file slightly past it, which is cheaper than stat-ing twice.
    """
    if MAX_TRACE_BYTES <= 0:
        return
    try:
        if TRACE.stat().st_size < MAX_TRACE_BYTES:
            return
        os.replace(str(TRACE), str(TRACE) + ".1")
    except OSError:
        pass


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # never break the session on a malformed payload

    # Some shell hooks send no tool_name but do send a top-level command.
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    has_cmd = bool(tool_input.get("command") or event.get("command"))
    tool = event.get("tool_name") or ("Bash" if has_cmd else "")
    # The first five keys are the original format and stay byte-identical; the
    # rest is the versioned envelope. Order matters only for human readability.
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": event.get("session_id", ""),
        "agent": event.get("agent_type") or event.get("subagent_type") or "main",
        "tool": tool,
        "summary": summarize(event),
        "schema": SCHEMA,
        "event": "tool_call",
        "harness": harness_version(),
        "args": input_keys(event),
    }

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _rotate_if_large()
        with TRACE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass  # read-only fs or no space: silently continue

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        # The docstring promises this hook never breaks a session. Without this
        # net that promise held only for unparseable stdin: a parseable event
        # of an unexpected shape raised, and an unhandled exception exits 1.
        # The deliberate sys.exit(0) in main() raises SystemExit, which is not
        # an Exception and passes straight through.
        sys.exit(0)
