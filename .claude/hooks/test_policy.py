#!/usr/bin/env python3
"""Tests for the generated `.claude/settings.json`.

When enforcement moved out of the hook and into declarative rules and the
sandbox, the protection had to *move*, not disappear. This asserts it did.

    python .claude/hooks/test_policy.py .claude/settings.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SETTINGS = Path(sys.argv[1] if len(sys.argv) > 1 else ".claude/settings.json")


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
    ok &= check("WebFetch is deny-all + explicit allowlist",
                "WebFetch(domain:*)" in deny and any(r.startswith("WebFetch(domain:") for r in allow))
    ok &= check("irreversible git/infra commands prompt the human",
                any("git push" in r for r in ask))
    ok &= check("recursive rm prompts rather than being silently allowed",
                any("rm -rf" in r for r in ask))

    print("\nThe hook still covers what rules cannot:")
    ok &= check("PreToolUse hook registered (session budget)", "PreToolUse" in hooks)
    ok &= check("PostToolUse hook registered (audit trace)", "PostToolUse" in hooks)

    print()
    print("settings.json checks passed" if ok else "settings.json FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
