# `example/` — the demo project

**Not part of the harness.** Everything here exists so the repo ships as a
*working* example rather than a skeleton: it shows what filled-in project
information looks like once the harness is adopted.

```
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

Only two things, both by design:

- the PROJECT block in the root `AGENTS.md`, between the `HARNESS:PROJECT`
  markers — the demo's facts;
- `.claude/format.map.json`, which maps `example/frontend/` and
  `example/backend/` to Prettier and google-java-format.

Nothing in `.claude/hooks/`, `.claude/agents/`, `.codex/` or the plugin
manifests knows this directory exists. That is the separation the layout is
for: `git rm -r example/`, replace the PROJECT block, repoint the formatter map,
and the harness is yours. Ordered walkthrough: `docs/adopt.md`.

## Skills live here, so they do not ship

`.claude/skills/` is packaged by both plugin manifests and installs for every
consumer. Quarkus and Angular workflows have no business in a generic install,
so they sit here instead — copy the shape into your own `.claude/skills/`.

## The Maven note

The demo backend uses the system `mvn`, never the `./mvnw` wrapper: the wrapper
writes outside the paths the sandbox allows, so the first invocation fails as a
*sandbox* error rather than a Maven error. `test_docs.py` enforces that no skill
or role prompt hands `./mvnw` to an agent as a command.
