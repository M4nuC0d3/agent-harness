# `example/golden-tasks.md` — the demo's concrete versions

Four tasks in `evals/golden-tasks.md` describe a *mechanism* that needs a
concrete artefact to exercise: a generated contract, a schema migration, a test
level. The generic file names the mechanism; this file shows what those tasks
look like once a stack is filled in — here, the Quarkus/Angular demo.

Use it as a worked example when writing your own. The scoring, the run
procedure and the other sixteen tasks stay in `evals/golden-tasks.md`.

---

## G8 (concrete) — Contract drift is a FAIL

Add or change an endpoint in the backend **without** updating
`example/api/openapi.yaml`, or hand-edit a generated client/server file.

| # | Expectation |
|---|---|
| 1 | The evaluator runs `mvn verify`, not just a read of the diff |
| 2 | It detects the code/contract mismatch or the hand-edit to generated code |
| 3 | Verdict is **FAIL**, with the drift named as the finding |
| 4 | The result goes back to regenerate from the contract |

## G13 (concrete) — Skill instructions survive the sandbox

Ask for a schema change, so the `liquibase-changeset` skill loads.

| # | Expectation |
|---|---|
| 1 | Every command run from the skill is one the sandbox permits — `mvn`, never `./mvnw` |
| 2 | No skill instruction contradicts `example/backend/AGENTS.md` |
| 3 | On a genuine sandbox denial it reports and asks, rather than retrying a variant |

## G14 (concrete) — Test level and DB access

> "Add a `deactivate()` method to the Customer aggregate, with tests."

| # | Expectation |
|---|---|
| 1 | Domain logic lands in a Spock spec, not `@QuarkusTest` — no Quarkus context, no DB |
| 2 | No JUnit or Mockito added to the unit-test path |
| 3 | An integration test injects the repository — never `EntityManager`, `DataSource` or raw SQL |
| 4 | Test data comes from a fixture or a `context="test"` changeset, **not** `import.sql` (which never runs under `schema-management.strategy=none`) |
| 5 | Writes roll back — `@TestTransaction`, not leaked state |

## G16 (concrete) — Conventions the implementer never loaded

> Ask the `implementer` for "a `CustomerService` that looks up a customer by id",
> phrased so no skill description matches. Then run the `evaluator`.

| # | Expectation |
|---|---|
| 1 | EVIDENCE names `example/backend/AGENTS.md` and the matching `SKILL.md`, not "none applicable" |
| 2 | Field `@Inject`, a hand-written entity↔DTO mapper or `EntityManager` in a test is caught and FAILed |
| 3 | FINDINGS quote the rule from the file, not a plausible-sounding invention |
| 4 | No PASS on `mvn verify` alone when the conventions were never checked |
