---
name: quarkus-testing
description: Use when writing, fixing, or reviewing backend tests — choosing between a Spock spec and @QuarkusTest, getting at the database in an integration test, or setting up test data. Keeps DB access behind the repository and stops test data landing in a file that never runs.
---

# Backend tests — Spock and @QuarkusTest

Two kinds of test, one gate: `mvn verify` (system `mvn`, never `./mvnw` — the
wrapper trips the sandbox). Unit tests alone: `mvn test`. A single one:
`-Dtest=SomethingSpec` or `-Dtest=ClassName#method`.

Goal: the cheapest test that actually covers the behaviour, with database access
going through a repository and test data that provably loads.

## Pick the level before writing anything

- **Domain or application logic → Spock** (`src/test/groovy`, name ends `…Spec`).
  No Quarkus context, no DB, no HTTP. Use Spock's own `Mock()` / `Stub()` —
  never add JUnit or Mockito here.
- **The wired application → JUnit 5 + `@QuarkusTest`** (`src/test/java`), with
  Dev Services (a real MariaDB in Testcontainers) and RestAssured for HTTP.
  Needs a running Docker daemon.
- **One bean, not the whole app → `@QuarkusComponentTest`.** Boots far less than
  `@QuarkusTest`. Still not the place for a database.

Reaching for `@QuarkusTest` because a Spock spec was awkward to write is the
common mistake: awkwardness usually means the logic sits in the wrong layer.

## Database access

- **Inject the repository.** Never `EntityManager`, never `DataSource`, never
  raw SQL in a test — those bypass the mapping the production path uses, so the
  test passes on a schema the application couldn't actually read.
- Repositories live in `infrastructure`. If a test needs one only to assemble an
  object, it belongs in Spock with a stub instead.
- Writes need a transaction: `@Transactional` for setup, or **`@TestTransaction`
  on the test** so each one rolls back. Prefer `@TestTransaction` — it keeps
  tests order-independent and stops one test seeding another.
- Replace a collaborator with `@InjectMock`, not by swapping the repository
  implementation or pointing the test at a second datasource.

## Test data

- **Fixture builders are the default** — plain factory methods that construct a
  domain aggregate and persist it through the repository. They refactor with the
  code and fail at compile time when the model changes.
- **Bulk seed data → a Liquibase changeset with `context="test"`**, activated by
  `quarkus.liquibase.contexts=test` under `%test`. Schema is Liquibase's
  (`liquibase-changeset` skill); test data is too.
- **`import.sql` / `sql-load-script` does not run in this project.** Hibernate
  only executes it as part of schema generation, and the strategy here is
  `none`. The file is accepted, logs nothing, and silently inserts nothing.

## Gotchas
- **Adding H2 "for speed."** Tests run against MariaDB via Dev Services;
  a different dialect passes tests the real database would reject.
- **Asserting on persistence entities instead of domain aggregates.** The mapping
  in `infrastructure` is what you want covered — go through the repository.
- **State bleeding between tests** because setup used `@Transactional` and never
  rolled back. Reach for `@TestTransaction` first.
- **A `@QuarkusTest` for logic with no framework in it.** Slow, and it hides
  which layer the behaviour really lives in.
- **Deleting or weakening a test to make a subtask pass** — never. Report it as
  blocked instead.
