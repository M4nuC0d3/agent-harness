#!/usr/bin/env python3
"""Behavioural tests for the SessionStart hook.

The case that matters is the one a `which` check cannot see: bwrap installed,
on PATH, and unable to create its user namespace. That combination started
sessions with no boundary while preflight reported everything fine — the exact
fail-open the hook exists to prevent.

These tests never touch real bwrap. Each case puts a fake `bwrap` and `socat`
first on PATH, so the probe's three outcomes (works / definitively fails /
unknown) are exercised deterministically on any machine.

    python3 .claude/hooks/test_preflight.py .claude/hooks/preflight.py

Linux-only by design: on macOS and Windows preflight returns before it ever
reaches the probe, so the suite skips itself there rather than assert nothing.

Stdlib only.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PREFLIGHT = Path(sys.argv[1] if len(sys.argv) > 1 else "preflight.py").resolve()

# Real symptom from the README's reproduction, so a regression reads like the
# bug report rather than like a test fixture.
UID_MAP_ERROR = "apply-seccomp: write /proc/self/uid_map: Operation not permitted"

# `case` on the args, so a fake can succeed for one form and fail for the other.
FAKE = {
    # Everything works.
    "works": "#!/bin/sh\nexit 0\n",
    # Nothing works — no user namespaces at all.
    "broken": f'#!/bin/sh\necho "{UID_MAP_ERROR}" >&2\nexit 1\n',
    # THE regression this file exists for: the plain form succeeds, the form the
    # real sandbox needs does not. The first probe I wrote tested only the plain
    # form and called this machine healthy.
    "weak_only": f"""#!/bin/sh
for a in "$@"; do
  if [ "$a" = "--unshare-all" ]; then
    echo "{UID_MAP_ERROR}" >&2
    exit 1
  fi
done
exit 0
""",
    "hangs": f"#!/bin/sh\nexec {shutil.which('sleep') or '/bin/sleep'} 60\n",
}


def run_preflight(bwrap_body: str | None, socat: bool = True) -> dict:
    """Run preflight with a synthetic PATH. Returns its stdout decision."""
    with tempfile.TemporaryDirectory() as tmp:
        binder = Path(tmp)
        if bwrap_body is not None:
            (binder / "bwrap").write_text(bwrap_body)
            (binder / "bwrap").chmod(0o755)
        if socat:
            (binder / "socat").write_text("#!/bin/sh\nexit 0\n")
            (binder / "socat").chmod(0o755)
        env = {**os.environ, "PATH": str(binder)}
        env.pop("HARNESS_SKIP_PREFLIGHT", None)
        proc = subprocess.run(
            [sys.executable, str(PREFLIGHT)], input="{}",
            capture_output=True, text=True, env=env, timeout=90,
        )
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"_unparseable": proc.stdout[:200]}


def check(label: str, ok: bool, why: str = "") -> bool:
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}" + ("" if ok else f" — {why}"))
    return ok


def main() -> int:
    if platform.system() != "Linux":
        print(f"  [skip] not Linux ({platform.system()}) — preflight returns "
              "before the probe on this platform")
        return 0

    failures = []

    def expect(label: str, decision: dict, should_continue: bool, needle: str = ""):
        ok = decision.get("continue", True) is should_continue
        if ok and needle:
            blob = json.dumps(decision)
            ok = needle.lower() in blob.lower()
        if not ok:
            failures.append(label)
        check(label, ok, f"got {json.dumps(decision)[:160]}")

    print("The probe's three outcomes:")
    # bwrap runs and exits 0 -> a boundary can be created -> start the session.
    d = run_preflight(FAKE["works"])
    expect("working bwrap starts the session", d, True)
    # Silence used to mean either "passed" or "never ran". It must not.
    expect("...and says so, so an absent hook is distinguishable from a green one",
           d, True, "Preflight OK")

    # THE case. bwrap is present, so `which` is satisfied; it fails at namespace
    # setup. Preflight must stop the session and quote the real error, because a
    # session that starts here has no boundary at all.
    d = run_preflight(FAKE["broken"])
    expect("bwrap that is installed but broken STOPS the session", d, False)
    expect("...and the block names the actual failure", d, False, "uid_map")
    expect("...and says nothing works, not just the unsharing", d, False,
           "at all")
    expect("...and tells you to check as the same user, outside the session",
           d, False, "SAME USER")

    # The regression. Plain bwrap works; the namespaces the real wrapper needs
    # do not. A probe that only tries the plain form reports a healthy machine
    # while every Bash call dies at /proc/self/uid_map.
    d = run_preflight(FAKE["weak_only"])
    expect("bwrap that works plainly but cannot unshare STOPS the session", d, False)
    expect("...and says the plain form succeeds, so the cause is the unsharing",
           d, False, "succeeds")
    expect("...and points at a nested sandbox rather than a kernel restriction",
           d, False, "nested")

    # Indeterminate -> warn, don't block. Blocking on "unknown" would wedge a
    # slow machine, and preflight's stated posture is to refuse only clear-cut
    # absences (it warns rather than blocks on macOS and native Windows too).
    expect("a hanging bwrap warns but does not block",
           run_preflight(FAKE["hangs"]), True, "could not determine")

    print("\nThe presence checks still hold:")
    expect("no bwrap at all blocks", run_preflight(None), False, "missing sandbox")
    expect("no socat blocks",
           run_preflight(FAKE["works"], socat=False), False, "missing sandbox")

    print("\nThe escape hatch still works:")
    env_decision = subprocess.run(
        [sys.executable, str(PREFLIGHT)], input="{}", capture_output=True,
        text=True, env={**os.environ, "HARNESS_SKIP_PREFLIGHT": "1", "PATH": ""},
        timeout=30,
    )
    ok = env_decision.stdout.strip() == "" or json.loads(
        env_decision.stdout).get("continue", True) is True
    if not ok:
        failures.append("HARNESS_SKIP_PREFLIGHT")
    check("HARNESS_SKIP_PREFLIGHT=1 allows even with an empty PATH", ok,
          f"got {env_decision.stdout[:120]}")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        return 1
    print("preflight fails closed on a broken sandbox, not just a missing one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
