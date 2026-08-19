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

## 3. `.claude/format.map.json` — yours, and not shipped

Path prefix + extension → formatter. `format.py` reads the map from
`$CLAUDE_PROJECT_DIR/.claude/format.map.json`, so it is a file you write in your
own project; the harness ships none and no map means no auto-formatting, the same
as a formatter that is not installed. Shape: `example/.claude/format.map.json`.
Never patch `format.py` — it owns no stack knowledge and CI asserts it stays
that way.

## 4. The boundary, in two files that must stay identical

`.claude/settings.json` and `settings.consumer.example.json` share their
`sandbox` and `permissions` blocks — `test_docs.py` asserts the two are equal,
so edit both or neither. The one project-specific line in there:
`network.allowedDomains`. Trim it to your stack; every entry is a widening of
what escapes the sandbox.

Do not add `sandbox.excludedCommands`. It is not a project-specific key to
fill in — this harness refuses to start any session where it's configured
(`preflight.py`'s `check_policy()`), because an excluded command skips the
sandbox for its whole shell line, chaining included. `test_docs.py` asserts
the key stays absent from both settings files.

For Codex the same boundary lives in `.codex/config.toml` — it does not travel
with the plugin, so a consuming project copies it.

## Verifying

`python3 .claude/hooks/test_docs.py .` fails on a PROJECT block that is still
the example, on an `@import` in `AGENTS.md`, on stack knowledge that has crept
into `format.py`, and on the context budget. Run it after adopting.

Full walkthrough with the ordered steps: `docs/adopt.md`.
