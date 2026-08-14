#!/usr/bin/env python3
"""PostToolUse hook: auto-format the file that was just written.

Wired in .claude/settings.json for Write|Edit|MultiEdit. This is a *convenience*,
deliberately best-effort and NON-BLOCKING: a missing or failing formatter never
blocks the tool call (always exits 0). The authoritative formatters run in the
build — this just keeps the working tree tidy between edits. Remove the
PostToolUse entry to disable it.

The script is stack-agnostic; **which** formatter runs where is project data and
lives in `.claude/format.map.json` (see the `$comment` in that file). That split
is the point: adopting this harness for another stack means editing one JSON
file, not patching a hook. A missing or malformed map disables formatting
silently — the same failure mode as a missing formatter.
"""
import json
import os
import shutil
import subprocess
import sys

MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "format.map.json")


def _rules():
    try:
        with open(MAP, encoding="utf-8") as fh:
            return json.load(fh).get("rules", [])
    except Exception:
        return []


def _run(cmd):
    """Run a formatter, swallowing every error — a hook must not block a write."""
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # Wired for Claude Code (Write|Edit|MultiEdit); a payload with no tool_name
    # is accepted too. Codex has no file-write hooks, so it never reaches here —
    # the formatters in the build cover that path.
    tool = payload.get("tool_name")
    if tool and tool not in ("Write", "Edit", "MultiEdit"):
        return 0

    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or payload.get("file_path") or payload.get("path")
    if not path or not os.path.isfile(path):
        return 0

    rel = path.replace("\\", "/")
    ext = os.path.splitext(rel)[1].lower()

    for rule in _rules():
        prefix = rule.get("prefix", "")
        if prefix and not (rel.startswith(prefix) or ("/" + prefix) in rel):
            continue
        exts = rule.get("extensions") or []
        if exts and ext not in exts:
            continue
        needs = rule.get("requires")
        if needs and not shutil.which(needs):
            return 0
        cmd = [a.replace("{file}", path) for a in rule.get("command", [])]
        if cmd:
            _run(cmd)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
