---
name: harness-adoption
description: Use when adapting this harness to a project for the first time, when a build/test command or stack convention has to be recorded somewhere, or when someone asks where project-specific information belongs. Covers the PROJECT block in AGENTS.md, nested package AGENTS.md files, the formatter map and the settings the boundary needs — and why none of it may be an @import.
---

# Adopting the harness for a project

The harness is stack-agnostic. Everything about *your* project lives in four
places, and nowhere else. If you are about to write a build command into a role
prompt, a hook or the README, it belongs in one of these instead.

## 1. The PROJECT block in `AGENTS.md`

Between `<!-- HARNESS:PROJECT-START -->` and `<!-- HARNESS:PROJECT-END -->`.
Skeleton: `templates/PROJECT.block.md`. Keep it to the layout, the two or three
rules that hold repo-wide, and pointers — under ~25 lines, because `CLAUDE.md` +
`AGENTS.md` are always loaded and `test_docs.py` enforces a 200-line ceiling.

**It must stay inline.** Claude Code resolves `@path` imports; Codex does not
(openai/codex#17401). An `@docs/project.md` line would load in one tool and be
dead text in the other — the exact drift this repo exists to avoid. One copy, in
the file both tools read.

## 2. Nested `AGENTS.md`, one per package

Build and test commands, framework conventions, local anti-patterns. Template:
`templates/package-AGENTS.template.md`. The closest file wins.

Caveat worth knowing: Claude Code loads a nested file when it touches that
subtree; Codex assembles its chain from the repo root down to the *working
directory*, and does not reliably pick up a package file when the session was
started at the root. So anything an agent must not miss — a destructive command,
a gate — goes in the root block, not only in the package file.

## 3. `.claude/format.map.json`

Path prefix + extension → formatter. The only stack knowledge in `.claude/`.
`format.py` reads it; empty `rules` disables auto-formatting.

## 4. The boundary, in two files that must stay identical

`.claude/settings.json` and `settings.consumer.example.json` share their
`sandbox` and `permissions` blocks — `test_docs.py` asserts the two are equal,
so edit both or neither. Project-specific lines in there: `excludedCommands`
(`mvn *`, `npm *`, `docker *`) and `network.allowedDomains`. Trim both to your
stack; every entry is a widening of what escapes the sandbox.

For Codex the same boundary lives in `.codex/config.toml` — it does not travel
with the plugin, so a consuming project copies it.

## Verifying

`python3 .claude/hooks/test_docs.py .` fails on a PROJECT block that is still
the example, on an `@import` in `AGENTS.md`, on a formatter map pointing at
paths that do not exist, and on the context budget. Run it after adopting.

Full walkthrough with the ordered steps: `docs/adopt.md`.
