#!/usr/bin/env python3
"""PostToolUse hook: auto-format the file that was just written.

Wired in .claude/settings.json for Write|Edit|MultiEdit. This is a *convenience*,
deliberately best-effort and NON-BLOCKING: a missing or failing formatter never
blocks the tool call (always exits 0). The authoritative formatters run in the
build — Prettier and Spotless in `verify` — this just keeps the working tree
tidy between edits. Remove the PostToolUse entry to disable it.

Formatters, only if present on PATH:
  frontend/**  .ts .html .scss .css .js .json  -> prettier (`npx --no-install prettier`)
  backend/**   .java                            -> google-java-format (if installed)

Note: for Java, Spotless in `./mvnw verify` is the source of truth. google-java-
format here only approximates it (fine if your Spotless uses that style; adjust
this hook if it doesn't). Running Maven per-write would be too slow for a hook.
"""
import json
import os
import shutil
import subprocess
import sys

FRONTEND_EXTS = {".ts", ".html", ".scss", ".css", ".js", ".mjs", ".json"}


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

    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0

    path = (payload.get("tool_input") or {}).get("file_path")
    if not path or not os.path.isfile(path):
        return 0

    rel = path.replace("\\", "/")
    ext = os.path.splitext(rel)[1].lower()

    if "/frontend/" in rel or rel.startswith("frontend/"):
        if ext in FRONTEND_EXTS and shutil.which("npx"):
            _run(["npx", "--no-install", "prettier", "--write", path])
        return 0

    if ("/backend/" in rel or rel.startswith("backend/")) and ext == ".java":
        if shutil.which("google-java-format"):
            _run(["google-java-format", "-i", path])
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
