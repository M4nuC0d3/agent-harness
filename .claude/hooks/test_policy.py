#!/usr/bin/env python3
"""Tests for a settings file that carries the boundary.

When enforcement moved out of the hook and into declarative rules and the
sandbox, the protection had to *move*, not disappear. This asserts it did.

Runs against either of the two files that carry it — this repo's own, and the
example every consumer copies. A boundary that only holds in the source repo is
worth very little.

    python3 .claude/hooks/test_policy.py .claude/settings.json
    python3 .claude/hooks/test_policy.py settings.consumer.example.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SETTINGS = Path(sys.argv[1] if len(sys.argv) > 1 else ".claude/settings.json")
# The default above is relative to the CURRENT directory, so running this suite
# from the repo root without an argument points it at a path that does not
# exist. That failure is loud but deeply misleading: `python3 <missing>.py`
# exits 2, so every exit-code assertion below fails at once and the suite reads
# like the settings file is broken rather than like the invocation is wrong. Cost a
# real debugging session once. Fail here instead, before any assertion runs.
if not SETTINGS.is_file():
    sys.exit(
        f"no settings file at {SETTINGS}\n"
        f"Pass the path explicitly:\n"
        f"    python3 {sys.argv[0]} .claude/settings.json"
    )



def check(label: str, condition: bool, why: str = "") -> bool:
    print(f"  [{'ok ' if condition else 'FAIL'}] {label}" + (f"  ({why})" if not condition else ""))
    return condition


def main() -> int:
    s = json.loads(SETTINGS.read_text(encoding="utf-8"))
    perms = s.get("permissions", {})
    deny, ask, allow = perms.get("deny", []), perms.get("ask", []), perms.get("allow", [])
    sandbox = s.get("sandbox", {})
    hooks = s.get("hooks", {})
    ok = True

    print("Credential paths are covered on every layer that can see them:")
    # The three controls bind different callers, and each one has a blind spot
    # the others cover:
    #   sandbox.credentials / filesystem.denyRead  bind SANDBOXED commands only
    #   permissions Read(...) deny                 binds Claude's file tools and
    #                                              the Bash file commands Claude
    #                                              Code recognises — including
    #                                              when a command is excluded
    #                                              from the sandbox
    # A path listed in only one of them is protected against one caller and open
    # to the other, which is exactly how ~/.ssh stayed readable while sitting in
    # denyRead the whole time. Assert the two lists mirror each other so the gap
    # cannot reopen silently.
    creds = [e.get("path") for e in
             (sandbox.get("credentials") or {}).get("files", [])
             if isinstance(e, dict) and e.get("mode") == "deny"]
    ok &= check("sandbox.credentials denies the credential paths",
                {"~/.ssh", "~/.aws", "~/.gnupg"} <= set(creds),
                f"got {creds}")
    read_rules = " ".join(r for r in deny if r.startswith("Read("))
    missing = [c for c in creds if c.rstrip("/") not in read_rules]
    ok &= check(
        "...and every one of them also has a Read deny rule",
        not missing,
        f"{missing} are denied only for sandboxed commands — an excluded "
        "command or a broken sandbox reads them freely",
    )
    deny_read = " ".join(sandbox.get("filesystem", {}).get("denyRead", []))
    ok &= check(
        "project secrets are in denyRead, not only in Read rules",
        all(x in deny_read for x in (".env", "secrets")),
        "Read rules do not reach a subprocess that opens the file itself",
    )

    print()
    print("The sandbox is the boundary:")
    ok &= check("sandbox.enabled", sandbox.get("enabled") is True)
    ok &= check(
        "sandbox.allowUnsandboxedCommands is false (escape hatch closed)",
        sandbox.get("allowUnsandboxedCommands") is False,
        "the model may otherwise retry a failed command outside the sandbox",
    )
    ok &= check(
        "sandbox denies reads of ~/.ssh and ~/.aws",
        all(any(p.startswith(x) for p in sandbox.get("filesystem", {}).get("denyRead", []))
            for x in ("~/.ssh", "~/.aws")),
        "the sandbox's default read policy still exposes credentials",
    )
    ok &= check(
        "network egress is an allowlist, not open",
        isinstance(sandbox.get("network", {}).get("allowedDomains"), list),
    )
    ok &= check(
        "docker socket not exposed",
        sandbox.get("network", {}).get("allowAllUnixSockets") is False,
    )

    print("\nWhat the hook gave up, the rules picked up:")
    ok &= check("secrets: .env is deny-read", any(".env" in r and r.startswith("Read(") for r in deny))
    ok &= check("secrets: .env is deny-edit", any(".env" in r and r.startswith("Edit(") for r in deny))
    ok &= check("secrets: secrets/ is denied", any("secrets" in r for r in deny))
    ok &= check("bash network tools denied (URL patterns are unreliable)",
                any(r.startswith("Bash(curl") for r in deny) and any(r.startswith("Bash(wget") for r in deny))
    # NOT deny-all: rules resolve deny > ask > allow, first match wins, and a
    # deny takes no allowlist exception -- so "WebFetch(domain:*)" in deny would
    # have killed the allowlist below rather than narrowing it. Unlisted domains
    # prompt the human instead; the hard egress boundary is the sandbox
    # allowlist, which is asserted separately above.
    ok &= check("WebFetch: unlisted domains prompt, listed ones are pre-approved",
                "WebFetch" in ask and any(r.startswith("WebFetch(domain:") for r in allow))
    ok &= check("no WebFetch deny-all (it cannot be narrowed by an allow)",
                not any(r.startswith("WebFetch") for r in deny))
    ok &= check("irreversible git/infra commands prompt the human",
                any("git push" in r for r in ask))
    ok &= check("recursive rm prompts rather than being silently allowed",
                any("rm -rf" in r for r in ask))

    print("\nThe hook still covers what rules cannot:")
    # Hooks arrive one of two ways: wired here (this repo, which develops them)
    # or carried by the plugin (a consumer, whose project has no .claude/hooks/).
    # Requiring both would be wrong; requiring neither would let a file ship with
    # no session budget and no trace at all.
    via_plugin = bool(s.get("enabledPlugins"))
    source = "the plugin" if via_plugin else "this file"
    ok &= check(f"PreToolUse hook comes from {source} (session budget)",
                "PreToolUse" in hooks or via_plugin,
                "no hooks block and no plugin — nothing counts tool calls")
    ok &= check(f"PostToolUse hook comes from {source} (audit trace)",
                "PostToolUse" in hooks or via_plugin,
                "no hooks block and no plugin — nothing writes the trace")

    print()
    print("settings.json checks passed" if ok else "settings.json FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
