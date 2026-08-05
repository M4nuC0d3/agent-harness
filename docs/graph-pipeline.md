# Graph pipeline — full criteria and topology

`AGENTS.md`'s decision matrix stays deliberately short — this file holds the
detail that would otherwise blow its ~200-line budget. Read this only when the
matrix has already told you a subtask qualifies; everything else stays on the
plain `researcher` → `implementer` → `evaluator` pipeline described there.

## When it activates

Both conditions must hold — complexity alone, or risk alone, is not enough.

**Complex** — at least one applies:

- touches a public API, interface, or persisted schema
- crosses module/package boundaries, or changes architecture
- affects auth, authorization, or concurrency
- changes deployment or infrastructure behavior

**3+ independent risk domains** — count the ones actually implicated by this
specific subtask, not a fixed set, and not a proxy for it: correctness,
security, API compatibility, performance, data migration, observability,
backward compatibility. The count is about domains, not the number of
changed files or subtasks — ten files that are all CSS is zero domains beyond
style; one file that touches auth, a schema, and the public API is three. A
subtask touching auth and a schema migration is 2 domains, not 3 — stays on
the plain pipeline even though it's complex.

## Topology

```
planner → dependency graph → implementer → parallel evaluators → synthesis → PASS/FAIL
```

- **Dependency graph** — the subtask's plan step, made explicit: which pieces
  are independent (dispatch together) vs. sequential.
- **Parallel evaluators** — one focus-scoped `evaluator` instance per risk
  domain that actually applies to this subtask (not all seven, every time).
  Each still returns the normal VERDICT/SCORE/EVIDENCE/FINDINGS shape from
  `.claude/agents/evaluator.md`, scoped to its one domain.
- **Synthesis** — a final step (you, the coordinator, or one more `evaluator`
  call) that: merges findings, drops duplicates, and reconciles contradictions
  between the parallel verdicts. The rule is the same one the plain pipeline
  already uses — no new severity tier: **any FAIL fails the whole subtask.**
  A PASS may still carry minor findings, exactly as `evaluator.md` already
  allows for the single-reviewer case.

## Recording the decision

Note *why* a subtask went to the graph pipeline as a `decided_by` edge in
`.agent/PROGRESS.md` (see `AGENTS.md` → *Long runs*) — the matrix condition it
tripped, e.g. "auth + schema migration + API change → graph, 3 risk domains."

Don't attach a confidence score to this. The decision matrix is a boolean
check on things you can point at in the diff (file count, does it touch
`api/openapi.yaml`, does it touch auth) — there's nothing probabilistic to
report, and a fabricated-looking number like `0.93` is worse than no number:
it invites trusting a judgment that was never made. If the call is genuinely
unclear, say so in prose and default to the plain pipeline.
