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

  Because exit 1 blocks nothing, an *accidental* exit 1 (an unhandled exception's
  default) is a silent fail-open. main() is therefore wrapped so every path ends
  in a deliberate exit — 0 or 2, never 1. When the guard cannot evaluate a call
  at all (unparseable event, unexpected internal error) it follows
  FAIL_CLOSED_ON_ERROR below rather than crashing.

Concurrency: the per-session counter is a read-modify-write on a shared file, so
parallel hook processes (parallelized sub-agents) could otherwise lose counts or
read a half-written file. check_budget serializes the update under an flock (on
POSIX) and always writes atomically (all platforms) — see _counter_lock /
_atomic_write_json.

Portability: this same script is wired into Claude Code (PreToolUse), Codex
(PreToolUse — identical stdin fields and exit-2-blocks semantics) and Cursor
(beforeShellExecution — the command sits at top-level `command`, and exit 2 also
blocks). `extract_command` reads both shapes, and exit 2 + stderr is the one
blocking signal all three honor, so there is a single copy — see
`.codex/hooks.json`, `.cursor/hooks.json`, and docs/porting-enforcement.md.

Stdlib only. Config is right here — no second file to keep in sync.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl  # POSIX advisory file locks; absent on native Windows
except ImportError:  # pragma: no cover - platform dependent
    fcntl = None

# ── Configuration ──────────────────────────────────────────────────────────

# A stop condition the model cannot ignore. No permission rule can count calls.
# 0 disables. The counter is written atomically and, on POSIX, updated under an
# flock, so concurrent hook processes can't lose counts or read a torn file.
MAX_TOOL_CALLS_PER_SESSION = 400
STATE_DIR = Path(".agent")

# Opt-in accident catcher. NOT a security mechanism — see the module docstring.
# Set to False if you have the sandbox and prefer fewer moving parts.
ACCIDENT_CATCHER = True

# What to do when the guard cannot evaluate an event at all — unparseable JSON,
# or an unexpected internal error.
#   True  -> BLOCK (exit 2) and say why. Matches the harness's fail-closed
#            posture (preflight.py stops the session when the boundary is
#            absent) and is never silent.
#   False -> ALLOW (exit 0) but warn on stderr, so the degradation is visible.
# Trade-off for True: a *systematic* parse failure (e.g. a CLI event-schema
# change) would hard-block every call until a human intervenes or flips this —
# loud and safe, but it can wedge a run. Either way the sandbox and permission
# rules still apply; this hook is not the boundary.
# NOTE: this governs "can't judge the call", not "can't write my bookkeeping
# file". Counter IO errors (e.g. a read-only fs) always fail OPEN, because the
# command itself may be perfectly safe — see check_budget.
FAIL_CLOSED_ON_ERROR = True

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


def extract_command(event: dict) -> str:
    """The shell command, wherever the tool puts it.

    Claude Code / Codex: {"tool_name": "Bash", "tool_input": {"command": ...}}.
    Cursor beforeShellExecution: {"command": ..., "cwd": ..., "sandbox": ...}.
    A non-shell event (a file write, an MCP call) has no command here -> "".
    """
    tool_input = event.get("tool_input") or {}
    return str(tool_input.get("command") or event.get("command") or "")


def block(reason: str) -> None:
    print(f"BLOCKED by .claude/hooks/guard.py: {reason}", file=sys.stderr)
    sys.exit(2)


def allow_silently() -> None:
    sys.exit(0)  # no decision -> normal permission flow


def fail(reason: str) -> None:
    """Deliberate decision when the event can't be evaluated — never exit 1.

    Follows FAIL_CLOSED_ON_ERROR: block (exit 2) and say why, or allow (exit 0)
    with a stderr warning. Both are deliberate; the point is that no code path
    falls through to Python's default exit 1, which blocks nothing.
    """
    if FAIL_CLOSED_ON_ERROR:
        block(
            f"could not evaluate this call: {reason}. Guard is fail-closed "
            "(FAIL_CLOSED_ON_ERROR); set it to False to allow such calls through."
        )
    print(
        f"WARNING from .claude/hooks/guard.py: could not evaluate this call "
        f"({reason}); allowing it (fail-open). The sandbox and permission rules "
        "still apply.",
        file=sys.stderr,
    )
    sys.exit(0)


def _flock_ex(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)


def _flock_un(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _counter_lock():
    """Serialize the counter read-modify-write across concurrent hook processes.

    On POSIX this is a real advisory lock (fcntl.flock) on a dedicated lock file,
    released automatically when the fd closes or the process dies — so there is
    no stale-lock problem. Without fcntl (native Windows) it is a no-op: the
    atomic replace in _atomic_write_json still prevents torn reads, but two
    truly-simultaneous increments there could lose one count. That is acceptable
    — the budget is a soft stop condition, not a boundary, and native Windows is
    not the supported platform (the README requires WSL2).

    A *separate* .lock file is used, not the counter itself, because the counter
    is replaced atomically (a new inode) — a lock held on the old inode would not
    protect the new file. Never raises: a locking/IO failure must not block a
    tool call.
    """
    lock_path = STATE_DIR / "tool_calls.lock"
    fd = None
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        _flock_ex(fd)
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            fd = None
    try:
        yield
    finally:
        if fd is not None:
            try:
                _flock_un(fd)
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass


def _read_counts(counter: Path) -> dict:
    """Current counts, or {} for first-run / corrupt content.

    A missing file (first call) or unparseable content (corruption, or a legacy
    format) resets to {} — harmless, the count simply restarts. Any *other*
    OSError (e.g. a transient read error) is left to propagate, so we skip this
    update rather than clobber a good file with {}.
    """
    try:
        data = json.loads(counter.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON so a concurrent reader never sees a partial file.

    Write a unique temp file in the same directory, then os.replace() — an atomic
    rename on both POSIX and Windows. Same-directory keeps the rename on one
    filesystem (a cross-device rename is not atomic). The temp file is closed
    before the rename so it also works on Windows.
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp_name, str(path))
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def check_budget(session_id: str) -> None:
    if MAX_TOOL_CALLS_PER_SESSION <= 0 or not session_id:
        return
    counter = STATE_DIR / "tool_calls.json"
    n = 0
    try:
        with _counter_lock():
            counts = _read_counts(counter)
            try:
                current = int(counts.get(session_id, 0))
            except (TypeError, ValueError):
                current = 0  # corrupt entry -> restart this session's count
            n = current + 1
            counts[session_id] = n
            if len(counts) > 50:  # keep the file bounded across many sessions
                counts = dict(list(counts.items())[-50:])
                counts[session_id] = n
            _atomic_write_json(counter, counts)
    except OSError:
        return  # read-only fs / bookkeeping IO error -> never block on bookkeeping

    if n > MAX_TOOL_CALLS_PER_SESSION:
        block(
            f"tool-call budget exhausted ({n} > {MAX_TOOL_CALLS_PER_SESSION} this "
            "session). Stop and report progress to the human instead of continuing."
        )


def check_accidents(cmd: str) -> None:
    # Runs whenever there is a command to inspect. Tool name is unreliable across
    # tools (Cursor's shell hook sends none), but only shell execs carry a
    # command, so a non-empty `cmd` is the signal — file writes and MCP calls
    # land here with cmd == "" and fall through untouched.
    if not ACCIDENT_CATCHER or not cmd:
        return
    for pattern in ACCIDENT_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            block(
                f"command matches a denied pattern ({pattern}): {cmd[:130]}. "
                "This is an accident catcher, not a boundary — if you meant it, ask."
            )


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        fail(f"invalid event JSON ({exc.__class__.__name__})")
        return  # fail() never returns; kept explicit for readers
    if not isinstance(event, dict):
        fail("event JSON was not an object")
        return

    check_budget(str(event.get("session_id", "")))
    check_accidents(extract_command(event))
    allow_silently()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        # Last-resort net: a bug must not become an accidental exit 1 (which
        # blocks nothing). The deliberate exits from block()/allow_silently()/
        # fail() raise SystemExit, which is NOT an Exception and passes straight
        # through this handler.
        fail(f"unexpected error ({exc.__class__.__name__})")
