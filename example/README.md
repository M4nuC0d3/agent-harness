# `example/` — the demo project

**Not part of the harness.** Everything here exists so the repo ships as a
*working* example rather than a skeleton: it shows what filled-in project
information looks like once the harness is adopted.

```
.claude/   format.map.json — the demo's formatter map, reference only
api/       OpenAPI contract — the demo's single source of truth
backend/   Quarkus · Java 25 · Maven · DDD   → backend/AGENTS.md
frontend/  Angular                           → frontend/AGENTS.md
skills/    the four stack-specific skills: openapi-client,
           liquibase-changeset, ddd-archunit, quarkus-testing
golden-tasks.md  the four eval tasks that need a concrete stack
```

There is no source code here — the point is the *instruction* layer: two nested
`AGENTS.md` files and four skills, written the way a real project would write
them. Read them as reference, not as something to run, and **never copy this
directory into a project**. What you copy is `templates/`; what you read is here.

| You are writing | Start from | Read next to it |
|---|---|---|
| the PROJECT block in `AGENTS.md` | `templates/PROJECT.block.md` | the block in the root `AGENTS.md` |
| a package `AGENTS.md` | `templates/package-AGENTS.template.md` | `backend/AGENTS.md` |
| a skill | — | `skills/*/SKILL.md` |
| your four concrete eval tasks | — | `golden-tasks.md` |

Note what `backend/AGENTS.md` does *not* contain: no branch policy, no
definition of done, no contract-first rule. Those live once in the root block and
are inherited here. A package file that repeats them is a package file that will
eventually contradict them.

## What refers to this directory

Exactly one thing: the PROJECT block in the root `AGENTS.md`, between the
`HARNESS:PROJECT` markers — the demo's facts.

Nothing in `.claude/`, `.codex/` or the plugin manifests knows this directory
exists, and `test_docs.py` asserts it. That is the separation the layout is for:
`git rm -r example/`, replace the PROJECT block, and the harness is yours.
Ordered walkthrough: `docs/adopt.md`.

## The formatter map lives here for the same reason the skills do

`.claude/format.map.json` used to be the one documented exception — *the only
stack knowledge left in `.claude/`*. It was also a leak: the plugin packages
`.claude/hooks/format.py`, the hook resolved its map relative to `__file__`, and
under a plugin install `__file__` is the plugin cache. So every consumer ran a
write hook driven by *these* prefixes, `example/frontend/` and
`example/backend/`, against a map sitting somewhere they would never think to
look and could not usefully edit.

`format.py` now reads `$CLAUDE_PROJECT_DIR/.claude/format.map.json` — the
consumer's own file, absent by default, absent meaning off. What is left here,
`.claude/format.map.json`, is a reference copy nothing reads: the demo's Prettier
and google-java-format rules, kept to show the shape. Copy the shape; do not copy
the file.

Four checks in `test_docs.py` hold the line, since a comment saying "project data
goes in the map" never stopped anyone from special-casing a path in the hook: no
map under `.claude/`, no `__file__` in the resolution, `format.py`'s string
literals confined to an allowlist of the map's schema and the hook payload, and
no value from any map appearing in the hook's source.

The prefixes here are also why `test_format.py` exists. A prefix is matched
against the path *relative to the project root*, anchored at its start — so in
your own project `example/frontend/` becomes `frontend/`, and that means the
top-level package and nothing else. It used to be an unanchored substring test on
the absolute path, under which `frontend/` quietly also meant
`vendor/legacy/frontend/`, and a prefix of `""` reached files outside the project
altogether. Neither is visible in review; both are one assertion each.

## Skills live here, so they do not ship

`.claude/skills/` is packaged by both plugin manifests and installs for every
consumer. Quarkus and Angular workflows have no business in a generic install,
so they sit here instead — copy the shape into your own `.claude/skills/`.

## The Maven note

The demo backend uses the system `mvn`, never the `./mvnw` wrapper: the wrapper
writes outside the paths the sandbox allows, so the first invocation fails as a
*sandbox* error rather than a Maven error. `test_docs.py` enforces that no skill
or role prompt hands `./mvnw` to an agent as a command.
