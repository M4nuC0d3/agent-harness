# Adopting the harness for a real project

The repo ships as a **working example**: a generic harness plus a demo project
(`example/`) that shows what filled-in project information looks like. This is
the ordered list for replacing the demo with yours.

Nothing here is generated. Every step edits exactly one copy of one thing.

## Why the project block is inline and not an import

The obvious design — project facts in `docs/project.md`, pulled in with
`@docs/project.md` — breaks Codex. Claude Code resolves `@path` imports in
`CLAUDE.md`/`AGENTS.md`; Codex has no import directive at all (openai/codex
issue #17401 is the open request). The line would load in one tool and sit there
as prose in the other, and nothing would tell you.

Two mechanisms both tools honour: **inline in the root `AGENTS.md`**, and
**nested `AGENTS.md`** files. So the split is by *scope*, not by file type:

| Scope | Lives in | Both tools? |
|---|---|---|
| Applies everywhere, must not be missed | the PROJECT block in `AGENTS.md` | yes |
| One package: build, tests, conventions | `<pkg>/AGENTS.md` | yes, with a caveat |
| A workflow you would explain twice | a skill | Claude Code, Codex (plugin) |
| Formatter wiring | `.claude/format.map.json` (yours, not shipped) | hook-driven, Claude Code |

## What you copy, what you read, what you write

Three kinds of file, and confusing them is the usual first mistake:

| Source | Kind | What to do |
|---|---|---|
| sub-agents, hooks, skills | plugin components | install, don't copy (Route 1) |
| `AGENTS.md`, `CLAUDE.md` | always-loaded instructions | copy, then replace one block |
| `settings.consumer.example.json` | the boundary | copy **to `.claude/settings.json`** |
| `.codex/config.toml` | the boundary, for Codex | copy |
| `templates/*` | blank skeletons | copy and fill in |
| `example/*` | the demo, filled in | read alongside the blank, never copy |

A plugin carries executable components only. Instruction files and settings are
never plugin components — see the table under *Install* in the README for why.

Each blank has a worked counterpart, so write them side by side:

| You write | Skeleton | Worked example |
|---|---|---|
| the PROJECT block in `AGENTS.md` | `templates/PROJECT.block.md` | the block currently in `AGENTS.md` |
| `<pkg>/AGENTS.md` | `templates/package-AGENTS.template.md` | `example/backend/AGENTS.md` |
| your skills | — | `example/skills/*/SKILL.md` |
| your four concrete eval tasks | — | `example/golden-tasks.md` |

## What goes in which AGENTS.md

The root block is **inherited** into every package; a nested file adds to it, it
does not replace it. Where both speak to the same point, the closest file wins —
so a nested file narrows a root rule and never restates it. Restating is how the
two drift apart with nobody editing either.

Root block: true everywhere *and* must not be missed. The layout, two or three
repo-wide rules, pointers to the package files. Keep it near 25 lines.

Package file: only meaningful inside that tree. Build and test commands,
framework conventions, the local traps. If a line in the root block starts with
"in the backend, …", it belongs one level down.

The asymmetry that decides borderline cases: inheritance downward is reliable in
both tools, discovery upward is not. Claude Code loads a nested file when it
touches that subtree, but Codex builds its chain from the repo root down to the
working directory and may never reach a package file in a root-launched session
(openai/codex#13288). So a destructive command must be fenced off in the root
block; a package file may assume an agent that already read the root.

The caveat: Claude Code loads a nested file when it touches that subtree; Codex
builds its chain from the repo root down to the **working directory** and does
not reliably pick up a package file when the session started at the root
(openai/codex#13288). Anything an agent must not miss belongs in the root block
even if it feels package-specific.

## The steps

1. **Replace the PROJECT block.** In `AGENTS.md`, everything between
   `<!-- HARNESS:PROJECT-START -->` and `<!-- HARNESS:PROJECT-END -->`. Skeleton:
   `templates/PROJECT.block.md`. Keep the markers — `test_docs.py` looks for
   them, and they are what makes a later `git diff` show exactly what you own.

2. **Delete or replace `example/`.** It holds the demo's `api/`, `backend/`,
   `frontend/` and the four stack skills. `git rm -r example/` once your own
   packages exist; nothing in `.claude/`, `.codex/` or the hooks refers to it.

3. **Write one `AGENTS.md` per package.** Template:
   `templates/package-AGENTS.template.md`. Commands the sandbox actually
   permits — a wrapper that writes outside the working directory fails as a
   sandbox error and reads like a tooling bug.

4. **Write `.claude/format.map.json`, if you want format-on-write.** The
   harness ships no map: `format.py` reads one from `$CLAUDE_PROJECT_DIR`, and
   with no map it does nothing. Prefix + extensions + command, shape copied from
   `example/.claude/format.map.json`. Prefixes are relative to your project root
   and anchored at its start — the demo's `example/frontend/` becomes plain
   `frontend/` in a project where that package sits at the top level, and it will
   not also match a `frontend/` buried somewhere else. `format.py` itself never
   needs an edit — `test_docs.py` keeps its string literals to a closed
   vocabulary, so a hard-coded path or formatter name fails CI instead of quietly
   working.

5. **Trim the boundary to your stack.** Both files carry a `_project_keys` note
   naming the only key that describes a stack rather than a policy;
   `test_docs.py` checks the note still matches the file. Everything else in
   there is the harness's boundary and should survive adoption unchanged. In `.claude/settings.json` *and*
   `settings.consumer.example.json` — `test_docs.py` asserts their `sandbox` and
   `permissions` blocks are identical, so edit both:
   - `sandbox.network.allowedDomains`: your registries, nothing more.
   - Codex reads none of this: mirror it in `.codex/config.toml`, which a
     consuming project copies because it does not travel with the plugin.

   **Do not add `sandbox.excludedCommands`.** This harness does not support
   it: `preflight.py` refuses to start any session where that key is
   configured, regardless of what it lists (README, *Known issue:
   `excludedCommands` matches the whole shell line*). If a build command fails
   inside the sandbox, that is either a `sandbox.network.allowedDomains` gap to
   close or a machine problem to fix (README, *Known issue: bwrap can't create
   its user namespace*) — never a command to exclude from the boundary.

6. **Write your four concrete golden tasks.** G8, G13, G14 and G16 in
   `evals/golden-tasks.md` name a mechanism rather than a command, because the
   artefact they need — a generated contract, a migration, a test level — is
   yours. `example/golden-tasks.md` shows the demo's filled-in versions. Keep
   yours in a separate file rather than editing the generic suite, so the suite
   stays updatable when the harness changes.

7. **Move your repeated workflows into skills.** `.claude/skills/` for the
   harness's own (`harness-adoption` ships there); yours alongside them. The four
   Quarkus/Angular ones under `example/skills/` are reference material — copy the
   shape, not the content.

8. **Verify, then trust.**

   ```
   python3 .claude/hooks/test_docs.py .          # budget, markers, no @import, map paths
   python3 .claude/hooks/test_policy.py .claude/settings.json
   python3 .claude/hooks/test_policy.py settings.consumer.example.json
   python3 .claude/hooks/test_guard.py .claude/hooks/guard.py
   ```

   Then run `evals/golden-tasks.md` in a scratch copy. The tests prove the files
   are consistent; only the golden tasks say whether the instructions work.

## Checking that both tools actually see it

"Both" means the two primary ones, Claude Code and Codex — they are the pair the
inline-block design exists for, and the pair CI keeps honest. If you also run
another `AGENTS.md` reader, the same check is worth doing once after adoption;
it just isn't the one that gates a change.

Start each CLI at the repo root and ask it to quote the gate command from
*Project facts*. Claude Code additionally shows the assembled context with
`/memory`. If Codex disagrees with Claude Code, something is behind an `@import`
or in a package file Codex never reached.
