#!/usr/bin/env python3
"""SessionStart hook — turn a missing sandbox from fail-OPEN into fail-CLOSED.

The sandbox is the real boundary (guard.py is explicitly *not* one). But a
sandbox that cannot start can fail open: on WSL1 or native Windows there is no
Linux sandbox at all, and on Linux/WSL2 the boundary needs `bwrap` + `socat` —
without them the isolation may silently not engage. This hook checks those
prerequisites *before* the agent runs anything and stops the session when the
boundary would be absent, so "no sandbox" is loud instead of silent.

On Linux it does not stop at "is bwrap installed". Installed and working are
different questions, so the check *runs* bwrap once — see probe_bwrap.

What this hook CANNOT see, and must not be read as covering: the wrapper the
Bash tool itself uses. Preflight is a SessionStart hook — a direct child of the
CLI, outside the sandbox path. On the machine this repo was developed on, the
probe exits 0 while every real Bash call dies at `/proc/self/uid_map`, because
whatever differs (nesting, capabilities, how the CLI invokes bwrap) is not
reachable from here. Two consequences, both deliberate:

  * The success message says explicitly what it does not prove. A green
    preflight is evidence about bwrap, not a certificate for the boundary.
  * That failure mode is loud on its own — the first Bash call fails visibly.
    The danger there is not a silent fail-open but the opposite pairing:
    sandboxed commands all die while `sandbox.excludedCommands` entries still
    run, with no boundary at all. That is guard.py's chaining check's job, not
    this file's.

Wiring (same script, three tools):
  * Claude Code — SessionStart   (.claude/settings.json)
  * Codex       — SessionStart   (.codex/hooks.json)
  * Cursor      — sessionStart   (.cursor/hooks.json)

Design choices:
  * Conservative. It BLOCKS only clear-cut cases (WSL1, missing bwrap/socat, or
    a bwrap that runs and definitively fails). macOS (Seatbelt) and native Windows are warned, not blocked —
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
import subprocess
import sys

BWRAP_INSTALL = "sudo apt-get install -y bubblewrap socat"

# What the probe runs. This has to resemble what Claude Code's sandbox actually
# does, or a green probe means nothing.
#
# The first version of this probe was `bwrap --ro-bind / / --dev /dev true`, and
# it was wrong: it never asks for the namespaces the real wrapper needs. A
# network allowlist requires `--unshare-net`, which requires a user namespace,
# and it is the user namespace that gets refused. The weak form passed on a
# machine where every real Bash call died at `/proc/self/uid_map` — a green
# light for a boundary that was not there. That is the same fail-open this file
# exists to prevent, just moved one step later.
#
# So: probe the STRONG form. On failure, fall back to the WEAK form purely to
# classify the failure, because "no namespaces at all" and "namespaces work but
# unsharing is refused" have different causes and different fixes.
PROBE_STRONG = ["bwrap", "--unshare-all", "--ro-bind", "/", "/", "--dev", "/dev", "true"]
PROBE_WEAK = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "true"]
PROBE_TIMEOUT_S = 10

# Set to False to skip the probe but keep the presence checks — e.g. if a future
# bwrap rejects this invocation for an unrelated reason and you need a session
# now. HARNESS_SKIP_PREFLIGHT=1 still disables everything.
PROBE_SANDBOX = True


def _run(cmd):
    """(returncode | None, first stderr line). None means we could not tell."""
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=PROBE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, f"no answer within {PROBE_TIMEOUT_S}s"
    except (OSError, ValueError) as exc:
        return None, f"could not run it ({exc.__class__.__name__})"
    err = (proc.stderr or b"").decode("utf-8", "replace").strip()
    return proc.returncode, (err.splitlines()[0][:160] if err else "")


def probe_bwrap():
    """Can bwrap create the sandbox this harness relies on? -> (state, detail).

    `shutil.which("bwrap")` answers a different question than "is there a
    boundary", and so does a bwrap invocation that skips the namespaces the real
    wrapper uses. Probe the strong form; classify with the weak one.

    Three outcomes, deliberately not two:
      True   the strong probe exited 0 -> the sandbox can be built
      False  it ran and exited non-zero -> it definitively cannot; BLOCK
      None   we could not tell (timeout, OSError, probe disabled) -> warn.
             Blocking on "unknown" would wedge a slow or unusual machine, and
             this file already warns rather than blocks for macOS and native
             Windows: refuse only a clear-cut absence.
    """
    if not PROBE_SANDBOX:
        return None, "probe disabled (PROBE_SANDBOX = False)"

    rc, err = _run(PROBE_STRONG)
    if rc is None:
        return None, err
    if rc == 0:
        return True, ""

    # It failed. Does anything work, or only the unsharing?
    weak_rc, _ = _run(PROBE_WEAK)
    if weak_rc == 0:
        detail = (
            f"`{' '.join(PROBE_STRONG)}` exited {rc} ({err or 'no stderr'}), but "
            f"`{' '.join(PROBE_WEAK)}` succeeds. So bwrap runs — what is refused "
            "is creating the namespaces. That points at a nested sandbox or "
            "container that does not grant nested user/network namespaces, "
            "rather than a kernel-wide restriction."
        )
    else:
        detail = (
            f"`{' '.join(PROBE_STRONG)}` exited {rc} ({err or 'no stderr'}), and "
            "the plain form fails too — bwrap cannot create a user namespace at "
            "all here."
        )
    return False, detail


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
        # Installed is not the same as working. This is the case this whole file
        # exists for and the one a `which` check misses: bwrap present, but
        # unable to create its user namespace. See probe_bwrap.
        ok, detail = probe_bwrap()
        if ok is False:
            block(
                "bwrap is installed but cannot build the sandbox, so the "
                f"boundary would be absent. {detail} Check from OUTSIDE the "
                "agent session, AS THE SAME USER it runs as — a broken sandbox "
                "means the agent's own Bash cannot run its own diagnosis, and a "
                "probe run as a different user proves nothing: "
                "`cat /proc/sys/user/max_user_namespaces`, `cat /proc/self/uid_map`, "
                "`systemd-detect-virt`, `bwrap --version`."
            )
        if ok is None:
            allow(f"Preflight WARNING: could not determine whether bwrap works "
                  f"({detail}). The boundary may be absent — verify with "
                  f"`{' '.join(PROBE_STRONG)}` before trusting this run.")
        # Say so out loud, and say what it does NOT prove. The success path used
        # to be silent, which made "the probe ran and passed" indistinguishable
        # from "the hook never ran" — and an absent hook is the likelier of the
        # two, since a missing `python3` makes every hook here no-op without a
        # word. Silence must never be evidence of a boundary.
        allow("Preflight OK: bwrap builds an isolated namespace when invoked "
              "from here (exit 0). This does NOT prove the wrapper the Bash "
              "tool uses works — preflight runs outside it and cannot reach it. "
              "If Bash calls still die at /proc/self/uid_map, see the README's "
              "*Known issue: bwrap*. If you do not see this line at session "
              "start, the hook did not run — check that `python3` is on PATH.")

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
