# backend/AGENTS.md

Quarkus service, **Java 25**, built with **Maven** (`./mvnw`). Packaged as a JVM
jar for now — no native build yet. Domain-Driven Design, with the architecture
**enforced by tests**, not just convention.

## Build & run

- Dev: `./mvnw quarkus:dev` — live reload; starts Dev Services (a MariaDB
  container) automatically.
- Unit tests only: `./mvnw test`
- Full suite (unit + integration): `./mvnw verify`
- A single test: `./mvnw test -Dtest=SomethingSpec` (Spock) or
  `-Dtest=ClassName#method` (JUnit).
- Package: `./mvnw package` → runnable JVM jar under `target/quarkus-app/`.

Integration tests need a running **Docker** daemon (Testcontainers / Dev
Services). On Windows, run inside WSL2 — see the README's *Prerequisites:
Windows + WSL*.

## Architecture — DDD, verified with ArchUnit

Structure by bounded context, then by layer inside each context:

```
<context>/
  domain/          aggregates, entities, value objects, domain events,
                   repository *interfaces* — no framework imports
  application/     use cases / application services, orchestration, transactions
  infrastructure/  Hibernate repositories, adapters, messaging, config
  interfaces/      REST resources (the generated API), DTO mapping
```

Dependency rule: `interfaces` → `application` → `domain`, and
`infrastructure` → `domain`. **The domain layer depends on nothing** — no
Quarkus, no JPA, no Jackson. Invariants live in the aggregate, not in services;
value objects are immutable.

These rules are **enforced by ArchUnit** (`*ArchTest` / `*ArchitectureTest`),
run as part of `./mvnw verify`. The ArchUnit suite is the source of truth for the
layering: forbidden dependencies, package boundaries, "domain has no framework
imports", naming. If you change the structure, update the ArchUnit rules **in the
same PR** — a green build must mean the rules still hold. Never weaken a rule to
make code pass; fix the dependency direction instead.

## Persistence

**Hibernate ORM with Panache** against **MariaDB**, using the **Panache
repository** pattern (`PanacheRepository`), not the active-record entity style.
Panache and JPA live in `infrastructure` only — map domain aggregates to
persistence entities there, so `domain/` stays free of Panache/JPA/Quarkus
imports (an ArchUnit rule enforces this). Keep persistence entities separate from
domain aggregates rather than annotating aggregates directly.

Schema is owned by **Liquibase** (`src/main/resources/db/changelog/`). Every
schema change is a **new changeset**. **Never edit a changeset that has already
been applied** — add a new one. The app does not auto-create or update schema;
Liquibase does (`quarkus.hibernate-orm.schema-management.strategy=none` or
equivalent).

## Tests

- **Unit tests → Spock** (Groovy, `src/test/groovy`, specs end in `…Spec`). They
  cover domain and application logic with **no** Quarkus context and **no** DB.
  Use Spock's built-in mocking/stubbing — **do not** add JUnit or Mockito for
  unit tests.
- **Integration tests → JUnit 5 + `@QuarkusTest`** (Java, `src/test/java`), with
  **Testcontainers** / Dev Services for a real MariaDB and RestAssured for the
  HTTP layer. This is where the wired application is exercised end to end.
- Coverage (JaCoCo) is expected to stay high, but the gate is simply: all of the
  above green. Never delete or weaken a test to make a subtask pass.

## API — contract-first

The REST layer **implements** the shared contract at `../api/openapi.yaml`; the
code is not the source of truth. Server interfaces and DTOs are generated from
that spec (e.g. openapi-generator `jaxrs-spec`). **Do not hand-edit generated
code.** To change an endpoint: edit `api/openapi.yaml` first, regenerate, then
implement. Error responses follow RFC 7807 Problem Details (adjust if the
contract defines a different error schema).

## Conventions

- Config in `application.properties` with `%dev` / `%test` / `%prod` profiles.
  No secrets in the repo — env vars only (see the root rules and `.gitignore`).
- Logging via JBoss Logging (`io.quarkus.logging.Log`), never `System.out`.
- Formatting enforced in `verify` (Spotless recommended) — state your formatter
  here so it isn't a per-PR debate.
- **Do not touch:** `target/`, and anything under the generated-API output
  folder. Regenerate it; don't edit it.
