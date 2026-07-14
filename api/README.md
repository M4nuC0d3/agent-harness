# API contract (contract-first)

`openapi.yaml` in this folder is the **single source of truth** for the HTTP
interface between the Angular frontend and the Quarkus backend. It lives here, at
the repo root, precisely because it belongs to *both* sides.

Workflow:

1. **Change `openapi.yaml` first.**
2. Regenerate from it:
   - backend — server interfaces / DTOs (see `backend/AGENTS.md`);
   - frontend — the typed HTTP client (see `frontend/AGENTS.md`).
3. Implement against the regenerated code. Never hand-edit generated types, and
   never let an endpoint exist in code but not in the contract (or vice versa).

Treat a change here like an API change: review it deliberately, because both
sides depend on it.
