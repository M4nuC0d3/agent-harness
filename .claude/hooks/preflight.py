#!/usr/bin/env python3
"""SessionStart hook — turn a missing sandbox from fail-OPEN into fail-CLOSED.

The sandbox is the real boundary (guard.py is explicitly *not* one). But a
sandbox that cannot start can fail open: on WSL1 or native Windows there is no
Linux sandbox at all, and on Linux/WSL2 the boundary needs `bwrap` + `socat` —
without them the isolation may silently not engage. This hook checks those
prerequisites *before* the agent runs anything and stops the session when the
boundary would be absent, so "no sandbox" is loud instead of silent.

Wiring (same script, three tools):
  * Claude Code — SessionStart   (.claude/settings.json)
  * Codex       — SessionStart   (.codex/hooks.json)
  * Cursor      — sessionStart   (.cursor/hooks.json)

Design choices:
  * Conservative. It BLOCKS only clear-cut cases (WSL1, missing bwrap/socat on
    Linux/WSL2). macOS (Seatbelt) and native Windows are warned, not blocked —
    Codex has a native Windows sandbox, so a hard block there would be a false
    positive we can't rule out from inside a hook.
  * Escape hatch. Set HARNESS_SKIP_PREFLIGHT=1 when the environment is already
    isolated externally (a container, a Codex-cloud runner, CI). Fail-closed by
    default, opt out when you've provided the boundary another way.
  * Fails SAFE on its own bugs. If preflight itself errors, it warns and allows
    — a broken preflight must never brick every session.

Output contract (portable): to stop, emit {"continue": false, ...} on stdout
(honored by Claude Code and Codex SessionStart) and also print the reason to
stderr. Never mix that with exit 2 (a non-zero exit would discard the JSON).

Stdlib only.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys

BWRAP_INSTALL = "sudo apt-get install -y bubblewrap socat"


def _read_event() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def allow(message: str = "") -> None:
    """Let the session start. Optionally surface a non-blocking note."""
    if message:
        out = {"continue": True, "systemMessage": message}
        print(json.dumps(out))
    sys.exit(0)


def block(reason: str) -> None:
    """Stop the session. JSON decision on stdout + reason on stderr; exit 0."""
    print(f"PREFLIGHT BLOCK (.claude/hooks/preflight.py): {reason}", file=sys.stderr)
    out = {
        "continue": False,
        "stopReason": reason,
        "systemMessage": (
            "Sandbox prerequisites not met — refusing to start so the boundary "
            "isn't silently absent. " + reason + " Set HARNESS_SKIP_PREFLIGHT=1 "
            "only if this environment is already isolated externally."
        ),
    }
    print(json.dumps(out))
    sys.exit(0)


def _is_wsl() -> bool:
    for path in ("/proc/sys/kernel/osrelease", "/proc/version"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                if "microsoft" in fh.read().lower():
                    return True
        except OSError:
            pass
    return False


def _is_wsl2() -> bool:
    try:
        with open("/proc/sys/kernel/osrelease", encoding="utf-8", errors="ignore") as fh:
            return "wsl2" in fh.read().lower()
    except OSError:
        return False


def check() -> None:
    if os.environ.get("HARNESS_SKIP_PREFLIGHT"):
        allow()  # caller asserts external isolation

    system = platform.system()

    if system == "Darwin":
        allow("Preflight: macOS — Claude Code/Codex use the built-in Seatbelt sandbox.")

    if system == "Windows":
        # Can't tell from here whether this is Codex (has a native Windows sandbox)
        # or Claude Code (needs WSL2). Warn loudly rather than false-block.
        allow(
            "Preflight WARNING: native Windows. Claude Code has no native-Windows "
            "sandbox — run inside WSL2. (Codex's native Windows sandbox is fine.) "
            "Set HARNESS_SKIP_PREFLIGHT=1 to silence."
        )

    if system == "Linux":
        if _is_wsl() and not _is_wsl2():
            block("WSL1 detected — it has no OS sandbox for these tools. Use WSL2 "
                  "(see the README's Prerequisites: Windows + WSL).")
        missing = [t for t in ("bwrap", "socat") if not shutil.which(t)]
        if missing:
            block(f"missing sandbox dependency: {', '.join(missing)}. Install with "
                  f"`{BWRAP_INSTALL}` (Ubuntu 24.04+: also allow bwrap user "
                  f"namespaces), then restart.")
        allow()  # Linux/WSL2 with bwrap + socat present

    # Unknown platform: don't pretend to know. Warn, don't block.
    allow(f"Preflight WARNING: unrecognized platform '{system}'. Confirm your "
          f"sandbox is active before trusting this run.")


def main() -> int:
    _read_event()
    try:
        check()
    except SystemExit:
        raise
    except Exception as exc:  # never brick a session on preflight's own bug
        print(json.dumps({
            "continue": True,
            "systemMessage": f"Preflight self-check errored ({exc}); continuing. "
                             "Verify your sandbox manually.",
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
