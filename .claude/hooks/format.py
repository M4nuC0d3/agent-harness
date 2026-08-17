#!/usr/bin/env python3
"""PostToolUse hook: auto-format the files that were just written.

Wired in `.claude/settings.json` (Write|Edit|MultiEdit) and in `.codex/hooks.json`
(apply_patch). This is a *convenience*, deliberately best-effort and
NON-BLOCKING: a missing or failing formatter never blocks the tool call (always
exits 0). The authoritative formatters run in the build — this just keeps the
working tree tidy between edits. Remove the PostToolUse entry to disable it.

The script is stack-agnostic and owns no stack knowledge at all: **which**
formatter runs where is project data, read from the map at
`<project>/.claude/format.map.json`. Adopting this harness for another stack
means writing one JSON file, never patching this hook — `test_docs.py` asserts
that by keeping this file's string literals to a closed vocabulary and by failing
if any value from a map appears in this source.

Two shapes of the same event, one script, the same reason `guard.py` reads two:
Claude Code names the file in `tool_input.file_path`, one file per call. Codex
routes every edit through `apply_patch` and puts the patch envelope in
`tool_input.command`, which can name several files at once and reports
`tool_name: "apply_patch"` whatever the matcher said. Both are parsed here; a
payload naming no readable file formats nothing.

The map and the prefixes both resolve against the *project*, never against
`__file__`: under a plugin install `__file__` sits in the install cache, so a map
found next to this script would be the harness author's rather than the
consumer's, and the demo's prefixes would silently drive formatting in a project
that never asked for them. `CLAUDE_PROJECT_DIR` is Claude Code's; Codex does not
set it, so the git root is the fallback — the session's working directory is not,
because Codex may be started from a subdirectory and then every prefix in the map
would miss. A missing or malformed map disables formatting silently, the same
failure mode as a missing formatter, and a path outside the project is never
touched. `example/.claude/format.map.json` shows the shape.
"""
import json
import os
import re
import shutil
import subprocess
import sys

# Codex's patch envelope. Delete needs no formatting; a move is formatted at its
# destination, which is what "Move to" carries.
PATCH_TARGET = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)
PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+)$", re.M)


def _project_root():
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return os.path.abspath(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return os.path.abspath(out.stdout.strip())
    except Exception:
        pass
    return os.path.abspath(".")


def _rules(root):
    try:
        with open(os.path.join(root, ".claude", "format.map.json"), encoding="utf-8") as fh:
            return json.load(fh).get("rules", [])
    except Exception:
        return []


def _candidates(payload, root):
    """Every file this event may have written, in either tool's shape."""
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        ti = {}

    named = ti.get("file_path") or payload.get("file_path") or payload.get("path")
    if named:
        return [named]

    # Codex: the envelope arrives as a string, or as argv with the patch inside.
    command = ti.get("command") or payload.get("command")
    if isinstance(command, (list, tuple)):
        command = "\n".join(str(a) for a in command)
    if not isinstance(command, str):
        return []

    found = PATCH_TARGET.findall(command) + PATCH_MOVE.findall(command)
    # Envelope paths are relative to the workspace, and quoting is the caller's.
    return [os.path.join(root, p.strip().strip('"').strip("'")) for p in found]


def _relative(path, root):
    """Project-relative, forward-slashed, or None if outside the project.

    A prefix only means something once the path is relative to the project.
    Matching against the absolute path would need an unanchored substring test,
    and then "frontend/" also means vendor/legacy/frontend/ and every
    node_modules copy of it, while "" reaches files outside the project.
    """
    try:
        rel = os.path.relpath(os.path.abspath(path), root).replace("\\", "/")
    except ValueError:          # different drive on Windows — not our tree
        return None
    return None if rel.startswith("../") else rel


def _run(cmd):
    """Run a formatter, swallowing every error — a hook must not block a write."""
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception:
        pass


def _format(path, rel, rules):
    ext = os.path.splitext(rel)[1].lower()
    for rule in rules:
        prefix = rule.get("prefix", "")
        if prefix and not rel.startswith(prefix):
            continue
        exts = rule.get("extensions") or []
        if exts and ext not in exts:
            continue
        needs = rule.get("requires")
        if needs and not shutil.which(needs):
            return
        cmd = [a.replace("{file}", path) for a in rule.get("command", [])]
        if cmd:
            _run(cmd)
        return


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # Registered per tool for the write events only. Codex reports apply_patch
    # even when the matcher said Edit or Write, so all four are accepted; a
    # payload with no tool_name is accepted too.
    tool = payload.get("tool_name")
    if tool and tool not in ("Write", "Edit", "MultiEdit", "apply_patch"):
        return 0

    root = _project_root()
    rules = _rules(root)
    if not rules:
        return 0

    for path in _candidates(payload, root):
        if not os.path.isfile(path):
            continue
        rel = _relative(path, root)
        if rel is not None:
            _format(path, rel, rules)
    return 0


if __name__ == "__main__":
    sys.exit(main())
