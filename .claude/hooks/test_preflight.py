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
# The default above is relative to the CURRENT directory, so running this suite
# from the repo root without an argument points it at a path that does not
# exist. That failure is loud but deeply misleading: `python3 <missing>.py`
# exits 2, so every exit-code assertion below fails at once and the suite reads
# like the hook is broken rather than like the invocation is wrong. Cost a
# real debugging session once. Fail here instead, before any assertion runs.
if not PREFLIGHT.is_file():
    sys.exit(
        f"no hook at {PREFLIGHT}\n"
        f"Pass the path explicitly:\n"
        f"    python3 {sys.argv[0]} .claude/hooks/preflight.py"
    )


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



WORKING_BWRAP = "#!/bin/sh\nexit 0\n"

# A project settings.json that carries the boundary, and two that do not.
POLICY_FIXTURES = {
    "complete": {
        "sandbox": {"enabled": True, "allowUnsandboxedCommands": False},
        "permissions": {"deny": [
            "Read(./.env)", "Read(./secrets/**)",
            "Bash(curl:*)", "Bash(wget:*)", "Bash(sudo:*)",
        ]},
    },
    # The plugin-install gap: hooks and roles present, boundary never copied.
    "no_sandbox": {"permissions": {"deny": ["Read(./.env)"]}},
    # Boundary on, second layer thin: warn, never block.
    "thin_rules": {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False}},
}


def run_policy(fixture: str | None) -> dict:
    """Run preflight against a synthetic project + HOME, with a working bwrap.

    HOME is redirected so a developer's own ~/.claude/settings.json cannot make
    this pass or fail by accident — the same reason the suite fakes bwrap.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        binder = root / "bin"
        binder.mkdir()
        for name in ("bwrap", "socat"):
            (binder / name).write_text(WORKING_BWRAP)
            (binder / name).chmod(0o755)
        project = root / "project"
        (project / ".claude").mkdir(parents=True)
        if fixture is not None:
            (project / ".claude" / "settings.json").write_text(
                json.dumps(POLICY_FIXTURES[fixture]))
        env = {**os.environ, "PATH": str(binder), "HOME": str(root / "home"),
               "CLAUDE_PROJECT_DIR": str(project)}
        env.pop("HARNESS_SKIP_PREFLIGHT", None)
        proc = subprocess.run(
            [sys.executable, str(PREFLIGHT)], input="{}",
            capture_output=True, text=True, env=env, timeout=90)
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"_unparseable": proc.stdout[:200]}


def run_seccomp(helper: str) -> dict:
    """Run preflight against a project whose sandbox.seccomp.applyPath is set.

    `helper` is one of:
      "exec"     the vendored binary is present and executable — the happy path
      "noexec"   present, execute bit missing (NixOS #510938: exit 126)
      "missing"  applyPath points somewhere that does not exist
      "unset"    no applyPath at all — preflight must claim nothing

    The policy is otherwise complete, so anything this reports comes from the
    seccomp probe and not from the policy gate.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        binder = root / "bin"
        binder.mkdir()
        for name in ("bwrap", "socat"):
            (binder / name).write_text(WORKING_BWRAP)
            (binder / name).chmod(0o755)

        settings = json.loads(json.dumps(POLICY_FIXTURES["complete"]))
        if helper != "unset":
            target = root / "vendor" / "apply-seccomp"
            if helper != "missing":
                target.parent.mkdir(parents=True)
                target.write_text("#!/bin/sh\nexit 0\n")
                target.chmod(0o755 if helper == "exec" else 0o644)
            settings["sandbox"]["seccomp"] = {"applyPath": str(target)}

        project = root / "project"
        (project / ".claude").mkdir(parents=True)
        (project / ".claude" / "settings.json").write_text(json.dumps(settings))
        env = {**os.environ, "PATH": str(binder), "HOME": str(root / "home"),
               "CLAUDE_PROJECT_DIR": str(project)}
        env.pop("HARNESS_SKIP_PREFLIGHT", None)
        proc = subprocess.run(
            [sys.executable, str(PREFLIGHT)], input="{}",
            capture_output=True, text=True, env=env, timeout=90)
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"_unparseable": proc.stdout[:200]}


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

    print("\nThe policy gate — a green probe is not a configured boundary:")
    managed = Path("/etc/claude-code/managed-settings.json")
    if platform.system() != "Linux":
        print("  [skip] policy gate cases assume the Linux probe path")
    elif managed.exists():
        # The managed file outranks the fixture and cannot be pointed elsewhere.
        print(f"  [skip] {managed} exists — it would outrank the fixtures")
    else:
        no_sandbox = run_policy("no_sandbox")
        check("a project with no sandbox block is STOPPED",
              no_sandbox.get("continue") is False,
              f"got {str(no_sandbox)[:140]}")
        check("...and the reason names the configuration gap, not the machine",
              "CONFIGURATION gap" in str(no_sandbox.get("stopReason", "")),
              "the fix is copying a settings file, not installing bwrap")
        missing = run_policy(None)
        check("no settings.json at all is STOPPED too",
              missing.get("continue") is False,
              "an absent policy is an absent boundary")
        thin = run_policy("thin_rules")
        check("a sandboxed project with thin deny rules is WARNED, not stopped",
              thin.get("continue", True) is True
              and "deny rule" in str(thin.get("systemMessage", "")),
              f"got {str(thin)[:140]}")
        complete = run_policy("complete")
        check("a correctly configured project starts clean",
              complete.get("continue", True) is True
              and "WARNING" not in str(complete.get("systemMessage", "")),
              f"got {str(complete)[:140]}")

    print("\nThe seccomp helper — the half of the boundary bwrap doesn't cover:")
    if managed.exists():
        print(f"  [skip] {managed} exists — it would outrank the fixtures")
    else:
        good = run_seccomp("exec")
        check("a present, executable helper is not flagged",
              good.get("continue", True) is True
              and "seccomp" not in str(good.get("systemMessage", "")).lower(),
              f"got {str(good)[:140]}")

        broken = run_seccomp("noexec")
        check("a helper without the execute bit is WARNED about",
              "not executable" in str(broken.get("systemMessage", "")),
              f"got {str(broken)[:180]}")
        # The whole point of the three-state split. This failure mode is real
        # but the probe cannot prove the sandbox is down from it, and a gate
        # that stops sessions on an inference gets switched off.
        check("...but the session still STARTS — this probe never blocks",
              broken.get("continue", True) is True,
              "warn-only is the contract; see PROBE_SECCOMP_HELPER")
        check("...and the warning names the excludedCommands pairing",
              "excludedCommands" in str(broken.get("systemMessage", "")),
              "the exposure is unsandboxed leftovers, not the dead commands")

        gone = run_seccomp("missing")
        check("an applyPath pointing nowhere is WARNED about, not blocked",
              gone.get("continue", True) is True
              and "does not exist" in str(gone.get("systemMessage", "")),
              f"got {str(gone)[:180]}")

        unset = run_seccomp("unset")
        check("no applyPath configured claims nothing either way",
              unset.get("continue", True) is True
              and "proved nothing" in str(unset.get("systemMessage", "")),
              f"got {str(unset)[:180]}")

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
