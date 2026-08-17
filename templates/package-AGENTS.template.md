# <package>/AGENTS.md

<One line: what this package is and what it is responsible for.>

Loaded when an agent works in this subtree. The root `AGENTS.md` is **inherited**
here — do not restate it. This file adds what is only true inside this tree: the
build, the tests, the conventions, the local traps. Where it speaks to the same
point as the root, the closest file wins, so narrow the root rule rather than
repeating it.

Do NOT put a rule here that an agent must never miss. Codex may never reach this
file in a session started at the repo root; the root block is the reliable level.

## Commands

```
<install>      # first run only
<build>
<test>         # what the evaluator runs to gate a change
<lint/format>
```

Name the commands the sandbox permits. If a wrapper script writes outside the
working directory it fails as a *sandbox* error, not a tooling one — say so here
rather than letting an agent rediscover it.

## Conventions

- <Layering, naming, module boundaries — what a reviewer would flag.>
- <Generated code: what is generated, from what, and that it is never hand-edited.>

## Anti-patterns

- <The mistake an agent actually makes in this package, and the correct move.>

## Definition of done, here

<The command that must be green, and any check beyond "tests pass".>
