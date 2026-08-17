#!/usr/bin/env python3
"""PostToolUse hook: auto-format the file that was just written.

Wired in .claude/settings.json for Write|Edit|MultiEdit. This is a *convenience*,
deliberately best-effort and NON-BLOCKING: a missing or failing formatter never
blocks the tool call (always exits 0). The authoritative formatters run in the
build — this just keeps the working tree tidy between edits. Remove the
PostToolUse entry to disable it.

The script is stack-agnostic and owns no stack knowledge at all: **which**
formatter runs where is project data, read from the map at
`$CLAUDE_PROJECT_DIR/.claude/format.map.json`. Adopting this harness for another
stack means writing one JSON file, never patching this hook — `test_docs.py`
asserts that by keeping this file's string literals to a closed vocabulary and
by failing if any value from a map appears in this source.

The map is resolved against the *project*, never against `__file__`. Under a
plugin install `__file__` sits in the plugin cache, so a map next to this script
would be the harness author's map rather than the consumer's — the demo's
prefixes would silently drive formatting in a project that never asked for them.
A missing or malformed map disables formatting silently, the same failure mode as
a missing formatter. Paths are matched relative to the project root, so a rule
can never reach outside it. `example/.claude/format.map.json` shows the shape.
"""
import json
import os
import shutil
import subprocess
import sys

MAP = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), ".claude", "format.map.json")


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

    # The payload carries an ABSOLUTE path, so a prefix can only mean something
    # once the path is made relative to the project. Getting this wrong is not
    # cosmetic: matching a prefix against the absolute path needs an unanchored
    # substring test, and then "frontend/" also means vendor/legacy/frontend/ and
    # every node_modules copy of it, while "" reaches files outside the project
    # entirely. Anchored, a prefix means exactly what the map says it does.
    root = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    try:
        rel = os.path.relpath(os.path.abspath(path), root).replace("\\", "/")
    except ValueError:          # different drive on Windows — not our tree
        return 0
    if rel.startswith("../"):   # outside the project — not ours to touch
        return 0
    ext = os.path.splitext(rel)[1].lower()

    for rule in _rules():
        prefix = rule.get("prefix", "")
        if prefix and not rel.startswith(prefix):
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
