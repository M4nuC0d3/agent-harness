---
name: liquibase-changeset
description: Use whenever the MariaDB schema must change — a new table, column, index, constraint, or a data migration. Creates a new Liquibase changeset the correct way and never edits one that has already been applied.
---

# Add a Liquibase changeset

Schema is owned by Liquibase (`src/main/resources/db/changelog/`), not by
Hibernate auto-DDL. Every change is a new, forward-only changeset.

Goal: a new changeset that applies cleanly on a fresh database *and* on an
existing one, wired into the master changelog.

- Add a new changeset with a unique, stable id and include it in the master
  changelog.
- Provide a rollback where practical.
- Verify it applies (`./mvnw quarkus:dev` runs Liquibase on startup, or run the
  Liquibase goal) and that the integration tests still bring the schema up.

## Gotchas
- **Never edit a changeset that has already run** anywhere — Liquibase stores a
  checksum and will fail, or environments silently diverge. Add a new one.
- Don't let Hibernate create or alter tables; that hides drift from Liquibase.
  Schema-management strategy stays `none`.
- Don't renumber or reuse existing changeset ids.
- Test the *upgrade* path on an existing database, not just a fresh create.
