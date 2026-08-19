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

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# Same trap as the other suites, one shape further out: this one takes a repo
# ROOT, so a wrong directory does not crash — it reports every documentation
# file as missing, which reads like the instruction layer is gone. Anchor on a
# file that must exist in any checkout and say so once, up front.
if not (ROOT / "AGENTS.md").is_file():
    sys.exit(
        f"no AGENTS.md under {ROOT} — that is not a harness checkout.\n"
        f"Pass the repo root explicitly:\n"
        f"    python3 {sys.argv[0]} ."
    )

# Anthropic's guideline for always-loaded memory. CLAUDE.md imports AGENTS.md,
# so Claude Code sees both at launch — @path imports do not reduce context.
LINE_BUDGET = 200
ALWAYS_LOADED = ["CLAUDE.md", "AGENTS.md"]

# The wrapper trips the sandbox (README *Prerequisites: Maven*). Instruction
# files that the agent follows must never name it as a command to run. README
# and example/backend/AGENTS.md are excluded: they explain *why* not to use it.
NO_MVNW_IN = [".claude/skills", ".claude/agents", ".codex/agents", "example/skills"]

# Codex refuses to load an AGENTS.md past this; Claude Code would still read it,
# so the two tools would silently disagree about the rules.
CODEX_AGENTS_LIMIT = 32 * 1024
MARKERS = ("<!-- HARNESS:PROJECT-START", "<!-- HARNESS:PROJECT-END")

# format.py is the one hook whose whole job is to act on project data, which
# makes it the one hook where a hard-coded shortcut ("just special-case
# example/frontend/ until the map is fixed") is tempting and invisible. An
# allowlist of its string literals closes that door: a blacklist of formatter
# names would always trail the next stack. The set is the map's schema plus the
# hook payload's keys — nothing that names a language, path or tool. Adding to
# it should feel like a decision, because it is one.
FORMAT_VOCAB = {
    "rules", "prefix", "extensions", "command", "requires",   # the map's schema
    "tool_name", "tool_input", "file_path", "path",           # payload keys
    "Write", "Edit", "MultiEdit",                             # payload values
    "CLAUDE_PROJECT_DIR", ".claude", "format.map.json",       # where the map lives
    "{file}", "utf-8", "\\", "/", "../", ".", "", "\n", "\"", "'", "__main__",
    "apply_patch",                                            # Codex's tool name
    "git", "rev-parse", "--show-toplevel",                    # the root fallback
    # Codex's patch envelope. Payload grammar, not project data — these say how
    # an edit is reported, never which formatter runs or where.
    r"^\*\*\* (?:Add|Update) File: (.+)$",
    r"^\*\*\* Move to: (.+)$",
}

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

    print("\nThe project block — the one part a consumer replaces:")
    agents = read("AGENTS.md")
    check("AGENTS.md carries both HARNESS:PROJECT markers",
          all(m in agents for m in MARKERS),
          "docs/adopt.md and the harness-adoption skill both point at them")
    check(f"AGENTS.md fits Codex's {CODEX_AGENTS_LIMIT // 1024} KiB ceiling",
          len(agents.encode("utf-8")) < CODEX_AGENTS_LIMIT,
          "Codex would drop the file that Claude Code still reads")
    # The split between harness and project must not be made with an import:
    # Claude Code resolves @path, Codex has no import directive at all
    # (openai/codex#17401), so half the instruction layer would go missing in
    # one tool with nothing to show for it. CLAUDE.md may import;
    # AGENTS.md is the file both tools read literally.
    imports = [f"{i}: {ln}" for i, ln in enumerate(agents.splitlines(), 1)
               if ln.strip().startswith("@")]
    check("AGENTS.md contains no @imports", not imports,
          f"Codex cannot resolve these — {imports}")
    if (ROOT / "example").is_dir():
        check("the example project is out of the packaged tree",
              not (ROOT / ".claude/skills").joinpath("quarkus-testing").exists(),
              "stack skills under .claude/skills/ install for every consumer")

    print("\nFormatter wiring (no stack knowledge under .claude/, in any form):")
    src = read(".claude/hooks/format.py")
    check("no formatter map under .claude/",
          not (ROOT / ".claude/format.map.json").exists(),
          "a map here ships with the plugin and describes the demo's stack, "
          "not the consumer's — it belongs in example/ as reference")
    # Both checks below read *code*, not prose: the docstring is allowed to
    # explain __file__ and the map's schema, which is why a plain substring
    # search over the source would fail on its own explanation.
    tree = ast.parse(src)
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                doc_nodes.add(id(first.value))
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in doc_nodes}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

    check("format.py resolves the map in the project, not next to itself",
          "CLAUDE_PROJECT_DIR" in literals and "__file__" not in names,
          "under a plugin install __file__ is the plugin cache, so the map "
          "found there is the harness author's, not the consumer's")
    stack_words = literals - FORMAT_VOCAB
    check("format.py's string vocabulary stays closed",
          not stack_words,
          f"stack knowledge in the hook — move it to the map: {sorted(stack_words)}")

    ref = ROOT / "example/.claude/format.map.json"
    if ref.exists():
        print("\nThe demo's map, as reference (nothing reads it):")
        fmap = json.loads(ref.read_text(encoding="utf-8"))
        for rule in fmap.get("rules", []):
            prefix = rule.get("prefix", "")
            check(f"format.map prefix exists: {prefix or '<project root>'}",
                  not prefix or (ROOT / prefix).exists(),
                  "the rule could never match — repoint it or drop it")
            check(f"format.map rule for {prefix or '<project root>'} names a command",
                  bool(rule.get("command")), "an empty command formats nothing")
        values = {v for rule in fmap.get("rules", [])
                  for v in [rule.get("prefix"), rule.get("requires"),
                            *(rule.get("extensions") or []),
                            *(rule.get("command") or [])]
                  if v and v != "{file}"}
        # In code an exact literal is the leak (`startswith("example/frontend/")`).
        # Anywhere else — a comment parking the value for later — a substring hit
        # counts, except where the value is itself part of a vocabulary word:
        # ".json" and ".js" both live inside "format.map.json" and would report
        # forever. Between the two rules, a real value has nowhere to sit.
        leaked = sorted(v for v in values if v in literals or
                        (v in src and not any(v in w for w in FORMAT_VOCAB)))
        check("no value from the map appears in format.py", not leaked,
              f"the hook must not know a single one of them: {leaked}")

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

    example_skills_dir = ROOT / "example/skills"
    if example_skills_dir.is_dir():
        example_readme = read("example/README.md")
        for name in sorted(d.name for d in example_skills_dir.iterdir() if d.is_dir()):
            fm = frontmatter(example_skills_dir / name / "SKILL.md")
            check(f"example skill {name}: frontmatter name matches its directory",
                  fm.get("name") == name, f"frontmatter says {fm.get('name')!r}")
            check(f"example/README.md mentions {name}", name in example_readme,
                  "reference material nobody is pointed at rots unnoticed")

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
    # There used to be two Codex hook files, because neither anchor works in both
    # places: the install cache (~/.codex/plugins/cache/) is not a git checkout,
    # so a git-root path resolves to nothing there, and ${PLUGIN_ROOT} is unset
    # in a project that just copied .codex/ in. Two files meant two chances to
    # forget one — which is how format.py ended up registered in neither.
    #
    # One file with a shell default covers both: Codex expands the command
    # string, ${PLUGIN_ROOT:-...} takes the cache path when set and falls back to
    # the git root when not.
    check("exactly one Codex hooks file",
          (ROOT / ".codex/hooks.json").exists()
          and not (ROOT / ".codex-plugin/hooks.json").exists(),
          "a second file drifts from the first — the events it registers are "
          "the ones the other one is missing")
    check("Codex plugin.json points hooks at the one file",
          codex_plugin.get("hooks") == "./.codex/hooks.json",
          "no hooks entry, or it points elsewhere — Codex would fall back to "
          "the plugin root's hooks/hooks.json default, which is also Claude "
          "Code's default and would load twice")
    # A Codex-flavoured file at the plugin root's hooks/hooks.json is discovered
    # by BOTH tools, and under Claude Code ${PLUGIN_ROOT} is never set: it
    # resolves empty and every command runs against /.claude/hooks/*.py.
    check("no repo-root hooks/hooks.json shadows Claude Code's default hook path",
          not (ROOT / "hooks/hooks.json").exists(),
          "Claude Code auto-discovers hooks/hooks.json in the plugin root "
          "and merges it with plugin.json's inline hooks — a Codex-only file "
          "there double-registers guard.py with an unresolved ${PLUGIN_ROOT}")
    codex_hooks = read(".codex/hooks.json")
    check("Codex hooks resolve in both the install cache and a checkout",
          codex_hooks.count("${PLUGIN_ROOT:-$(git rev-parse --show-toplevel)}")
          == codex_hooks.count(".claude/hooks/"),
          "every command needs the fallback anchor, or it works in one "
          "install route and silently no-ops in the other")
    referenced = sorted(set(re.findall(r"\.claude/hooks/(\w+)\.py", codex_hooks)))
    claude_hooked = sorted(set(re.findall(r"\.claude/hooks/(\w+)\.py",
                                          read(".claude/settings.json"))))
    check("Codex registers the same hook scripts as Claude Code",
          referenced == claude_hooked,
          f"Codex {referenced} vs Claude Code {claude_hooked} — enforcement "
          f"differs by tool, which is the thing this repo claims it does not do")
    # Codex reports tool_name apply_patch for every edit, whatever the matcher
    # said, so the matcher and the hook's accepted names must both cover it.
    check("the write matcher names Codex's patch tool",
          "apply_patch" in codex_hooks,
          "matching only Edit|Write would still fire, but a hook that checks "
          "tool_name against Claude Code's names would then drop the event")
    for rel in (f".claude/hooks/{name}.py" for name in referenced):
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

    print("\nThe eval suite must outlive the demo project:")
    # Same rule as the instruction layer: the harness ships mechanisms, the
    # project supplies artefacts. A golden task that says `mvn verify` only runs
    # for one stack — and unlike a stale doc line, nobody notices, because the
    # task simply gets skipped.
    STACK_TERMS = ["quarkus", "angular", "liquibase", "archunit", "spock",
                   "jakarta", "openapi", "entitymanager", "mockito", "mvn ",
                   "maven"]
    evals_text = read("evals/golden-tasks.md").lower()
    leaked = sorted({term.strip() for term in STACK_TERMS if term in evals_text})
    check("evals/golden-tasks.md names no stack", not leaked,
          f"concrete versions belong in example/golden-tasks.md; found: {leaked}")
    if (ROOT / "example/golden-tasks.md").exists():
        check("the concrete task versions are pointed at from the generic suite",
              "example/golden-tasks.md" in read("evals/golden-tasks.md"),
              "an example nobody is sent to is an example nobody reads")

    print("\nThe two project-specific settings keys stay labelled:")
    # settings.json has no import mechanism, so the stack values cannot be split
    # out into a separate file — the same constraint as AGENTS.md. Marking them
    # is the next best thing, and the marking is only worth something if it is
    # checked against reality.
    for rel in (".claude/settings.json", "settings.consumer.example.json"):
        data = json.loads(read(rel))
        note = " ".join(data.get("_project_keys", []))
        check(f"{rel} labels its project-specific keys", bool(note),
              "a consumer cannot tell policy from stack without it")
        check(f"{rel}: the labelled keys exist",
              "excludedCommands" in data.get("sandbox", {})
              and "allowedDomains" in data.get("sandbox", {}).get("network", {}),
              "the label points at keys that are not there")
    check("docs/adopt.md walks through both labelled keys",
          "excludedCommands" in read("docs/adopt.md")
          and "allowedDomains" in read("docs/adopt.md"),
          "the label needs somewhere to send people")

    print("\nManaged lockdown — the template must replace what its flags remove:")
    managed = json.loads(read("managed-settings.example.json"))
    plugin_id = f"{plugin['name']}@{market['name']}"
    # allowManagedHooksOnly blocks project hooks AND plugin hooks, except plugins
    # force-enabled in managed enabledPlugins (matched by full plugin@marketplace
    # id). Setting the flag without that entry silently switches off guard.py,
    # preflight.py and trace.py — and preflight, being a hook, cannot report it.
    # The failure is a MISSING session message, which nobody notices.
    if managed.get("allowManagedHooksOnly"):
        check("managed template force-enables this plugin's hooks",
              managed.get("enabledPlugins", {}).get(plugin_id) is True,
              f"allowManagedHooksOnly blocks every other hook source; {plugin_id} "
              "must be in enabledPlugins or the hook layer is off")
        check("managed template knows the marketplace it force-enables",
              market["name"] in managed.get("extraKnownMarketplaces", {}),
              "the plugin id would not resolve")
    # allowManagedPermissionRulesOnly makes project rules inert, so the deny
    # baseline has to exist HERE or it exists nowhere.
    if managed.get("allowManagedPermissionRulesOnly"):
        repo_deny = set(settings.get("permissions", {}).get("deny", []))
        managed_deny = set(managed.get("permissions", {}).get("deny", []))
        gap = sorted(repo_deny - managed_deny)
        check("managed template repeats every repo-level deny rule", not gap,
              f"project rules are inert under this flag; missing: {gap}")
    # The boundary itself: a lockdown that leaves the sandbox optional is not one.
    check("managed template pins the sandbox on",
          managed.get("sandbox", {}).get("enabled") is True
          and managed.get("sandbox", {}).get("allowUnsandboxedCommands") is False,
          "the one thing no lower scope can then re-open")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        return 1
    print("instruction layer is self-consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
