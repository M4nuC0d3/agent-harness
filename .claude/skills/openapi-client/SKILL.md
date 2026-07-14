---
name: openapi-client
description: Use when api/openapi.yaml (the shared API contract) changes, or when backend endpoints or the frontend API client need to match the contract. Regenerates the server interfaces and the typed Angular client from the spec so code and contract never drift.
---

# Regenerate from the OpenAPI contract

`api/openapi.yaml` is the single source of truth (contract-first). When it
changes, both sides are regenerated from it. You never hand-edit generated code,
and you never add an endpoint in code that the contract doesn't define.

Goal: after this, backend stubs and the frontend client both match the spec and
the build is green.

- **Backend** — regenerate server interfaces/DTOs (openapi-generator `jaxrs-spec`
  or the configured generator) into the generated-sources folder, then implement
  those interfaces in `interfaces/`.
- **Frontend** — regenerate the typed client (`ng-openapi-gen` or
  openapi-generator `typescript-angular`) into its own folder, and consume it
  from services.
- Build and test both, so a contract change that breaks a consumer fails loudly.

## Gotchas
- Editing generated code instead of the spec — the next regeneration silently
  reverts it. Change `openapi.yaml` first, always.
- Adding an endpoint in the backend or frontend that the contract doesn't have.
  Contract first, then code.
- Forgetting the *other* side: a backend-only change the client never sees is
  drift. Regenerate both.
- Committing without regenerating — reviewers can no longer tell code from
  contract.
