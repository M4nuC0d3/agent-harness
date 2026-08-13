#!/usr/bin/env python3
"""Static checks on the instruction layer itself.

test_guard.py proves the hook behaves. test_policy.py proves the rules are
present. Neither notices that a skill tells the agent to run a command the
sandbox refuses, that the README claims three skills when there are four, or
that AGENTS.md quietly grew past the context budget.

Every check here is a bug that actually shipped in this repo. A prompt file rots
the way code does; this is the part of the rot a machine can catch.

    python3 .claude/hooks/test_docs.py

Stdlib only. Run from the repo root, or pass the root as the first argument.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# Anthropic's guideline for always-loaded memory. CLAUDE.md imports AGENTS.md,
# so Claude Code sees both at launch — @path imports do not reduce context.
LINE_BUDGET = 200
ALWAYS_LOADED = ["CLAUDE.md", "AGENTS.md"]

# The wrapper trips the sandbox (README *Prerequisites: Maven*). Instruction
# files that the agent follows must never name it as a command to run. README
# and backend/AGENTS.md are excluded: they explain *why* not to use it.
NO_MVNW_IN = [".claude/skills", ".claude/agents", ".codex/agents"]

failures: list[str] = []


def check(label: str, ok: bool, why: str = "") -> None:
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}" + ("" if ok else f" — {why}"))
    if not ok:
        failures.append(label)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def frontmatter(path: Path) -> dict:
    """Parse the leading --- block. Not YAML: only `key: value` scalars."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("---")
    body, _, _ = rest.partition("\n---")
    out = {}
    for line in body.splitlines():
        key, sep, value = line.partition(":")
        if sep and not key.startswith(" "):
            out[key.strip()] = value.strip()
    return out


def main() -> int:
    print("Context budget:")
    total = sum(len(read(f).splitlines()) for f in ALWAYS_LOADED)
    check(
        f"always-loaded context is {total} lines (budget {LINE_BUDGET})",
        total <= LINE_BUDGET,
        "move detail into a nested AGENTS.md, a skill, or docs/ — not a new rule here",
    )
    readme = read("README.md")
    claimed = re.search(r"Claude Code sees (\d+)", readme)
    check(
        "README's stated line count matches reality",
        bool(claimed) and int(claimed.group(1)) == total,
        f"README says {claimed.group(1) if claimed else '?'}, actual is {total}",
    )

    print("\nCommands the sandbox actually permits:")
    for rel in NO_MVNW_IN:
        offenders = []
        for path in (ROOT / rel).rglob("*"):
            if not path.is_file():
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "mvnw" not in line:
                    continue
                # "never `./mvnw`" is the instruction, not a violation of it.
                if re.search(r"\b(never|not|instead of|rather than)\b", line, re.I):
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{i}")
        check(f"./mvnw is never given as a command in {rel}/",
              not offenders, f"found at {offenders}")

    print("\nSkills:")
    skills_dir = ROOT / ".claude/skills"
    skills = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
    for name in skills:
        fm = frontmatter(skills_dir / name / "SKILL.md")
        check(f"{name}: has name + description frontmatter",
              bool(fm.get("name")) and bool(fm.get("description")),
              "a skill without a description never loads")
        check(f"{name}: frontmatter name matches its directory",
              fm.get("name") == name, f"frontmatter says {fm.get('name')!r}")
    missing = [s for s in skills if s not in readme]
    check("README mentions every wired skill", not missing, f"missing: {missing}")

    print("\nRoles:")
    claude_agents = sorted(p.stem for p in (ROOT / ".claude/agents").glob("*.md"))
    codex_agents = sorted(p.stem for p in (ROOT / ".codex/agents").glob("*.toml"))
    check("Claude Code and Codex define the same roles",
          claude_agents == codex_agents,
          f"{claude_agents} vs {codex_agents}")
    for name in claude_agents:
        fm = frontmatter(ROOT / ".claude/agents" / f"{name}.md")
        check(f"{name}: declares name, description and tools",
              all(fm.get(k) for k in ("name", "description", "tools")),
              f"got keys {sorted(fm)}")

    print("\nPlugin packaging:")
    plugin = json.loads(read(".claude-plugin/plugin.json"))
    market = json.loads(read(".claude-plugin/marketplace.json"))
    check("plugin.json declares a name and version",
          bool(plugin.get("name")) and bool(plugin.get("version")),
          "without a version bump, installed copies never update")
    settings = json.loads(read(".claude/settings.json"))
    consumer = json.loads(read("settings.consumer.example.json"))
    listed = [p["name"] for p in market.get("plugins", [])]
    check("marketplace lists the plugin", plugin["name"] in listed, f"lists {listed}")
    for field in ("agents", "skills"):
        for rel in plugin.get(field, []):
            check(f"plugin.json {field} path exists: {rel}",
                  (ROOT / rel.removeprefix("./")).exists(), "component would silently not load")
    # `agents` takes FILE paths (`skills` takes directories). Omitting it or
    # pointing it at a directory both pass `claude plugin validate` — the first
    # falls back to a default scan of ./agents/, which does not exist here — so
    # the roles would simply not ship. Validation green, feature absent. Pin the
    # list to what is actually on disk instead.
    declared = sorted(plugin.get("agents", []))
    on_disk = sorted(f"./.claude/agents/{p.name}"
                     for p in (ROOT / ".claude/agents").glob("*.md"))
    check("plugin.json ships exactly the roles that exist",
          declared == on_disk,
          f"declared {declared}, on disk {on_disk}")

    print("\nCodex plugin packaging:")
    codex_plugin = json.loads(read(".codex-plugin/plugin.json"))
    codex_market = json.loads(read(".agents/plugins/marketplace.json"))
    check("Codex plugin.json declares a name and version",
          bool(codex_plugin.get("name")) and bool(codex_plugin.get("version")),
          "without a version bump, installed copies never update")
    # Two manifests, one release. Bumping only one ships an update to half the
    # installs and leaves the other half on a cached copy that looks current.
    check("both plugin manifests carry the same version",
          codex_plugin.get("version") == plugin.get("version"),
          f"Codex {codex_plugin.get('version')} vs Claude {plugin.get('version')}")
    codex_listed = [p["name"] for p in codex_market.get("plugins", [])]
    check("Codex marketplace lists the plugin",
          codex_plugin.get("name") in codex_listed, f"lists {codex_listed}")
    # In a repo that has both, Codex reads BOTH catalogs: .agents/plugins/ and,
    # legacy-compatible, .claude-plugin/marketplace.json. The install cache is
    # keyed by marketplace name (~/.codex/plugins/cache/$MARKETPLACE/$PLUGIN/
    # $VERSION/), so equal names put two different metadata sets in one
    # directory and which one wins is undefined.
    check("the two marketplaces have different names",
          codex_market.get("name") != market.get("name"),
          f"both are {market.get('name')!r} — one cache path, two catalogs")
    # `skills` is ONE directory path in the Codex manifest, an array in Claude's.
    skills_rel = codex_plugin.get("skills")
    check(f"Codex plugin.json skills path exists: {skills_rel}",
          isinstance(skills_rel, str)
          and (ROOT / skills_rel.removeprefix("./")).is_dir(),
          "a string directory path, not an array — the skills would not load")
    # The install cache (~/.codex/plugins/cache/) is not a git checkout, so the
    # git-root path .codex/hooks.json uses resolves to nothing there. The hook
    # then no-ops, and an absent PreToolUse hook blocks nothing.
    codex_hooks = read("hooks/hooks.json")
    check("plugin hooks anchor on ${PLUGIN_ROOT}, not the git root",
          "PLUGIN_ROOT" in codex_hooks and "rev-parse" not in codex_hooks,
          "hooks would not resolve from the plugin install cache")
    referenced = sorted(set(re.findall(r"\.claude/hooks/\w+\.py", codex_hooks)))
    check("plugin hooks register the three shared scripts",
          len(referenced) == 3, f"registers {referenced}")
    for rel in referenced:
        check(f"plugin hook script exists: {rel}", (ROOT / rel).exists(),
              "the hook would silently no-op")

    print("\nThe two settings files, and the line between them:")
    # This repo is the plugin *source*: it runs the hooks from the working tree.
    # Registering the plugin here too would load a second copy of the same four
    # hooks from the plugin cache and run every one twice — halving the tool-call
    # budget and doubling every trace line, silently.
    check("repo settings.json wires the hooks locally",
          "hooks" in settings, "the working tree is where these are developed")
    check("repo settings.json does NOT also install the plugin",
          "enabledPlugins" not in settings,
          "local hooks + plugin hooks = every hook fires twice")
    # A consumer gets the hooks from the plugin. A copied `hooks` block would
    # point at .claude/hooks/*.py paths that don't exist in their project — and
    # an absent PreToolUse hook blocks nothing, silently.
    check("consumer example does NOT wire hooks",
          "hooks" not in consumer, "the plugin supplies them; copied paths would not resolve")
    check("consumer example installs the plugin",
          consumer.get("enabledPlugins", {}).get(f"{plugin['name']}@{market['name']}") is True,
          f"got {consumer.get('enabledPlugins')}")
    check("consumer example registers this marketplace",
          market["name"] in consumer.get("extraKnownMarketplaces", {}),
          f"registers {list(consumer.get('extraKnownMarketplaces', {}))}")
    # The boundary is the one thing a plugin cannot carry, so it exists twice.
    # That is the drift risk this repo warns about everywhere else — assert it.
    for block_name in ("sandbox", "permissions"):
        check(f"{block_name} block is identical in both settings files",
              settings.get(block_name) == consumer.get(block_name),
              "the boundary would differ between this repo and every install")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        return 1
    print("instruction layer is self-consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
