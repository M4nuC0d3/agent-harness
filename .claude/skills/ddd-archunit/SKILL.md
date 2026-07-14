---
name: ddd-archunit
description: Use before finishing any backend change, or when adding or moving classes between domain, application, infrastructure, and interfaces. Confirms the DDD layering holds and the ArchUnit rules pass, and keeps the rules in sync when the structure changes.
---

# DDD / ArchUnit check

The DDD layering is enforced by ArchUnit, run as part of `./mvnw verify`. This is
the checklist before you call backend work done.

Goal: the architecture tests pass for the right reasons — not because a rule was
weakened.

- Dependency direction holds: `interfaces → application → domain`, and
  `infrastructure → domain`. `domain` imports no framework — no Quarkus, JPA,
  Panache, or Jackson.
- Invariants live in the aggregate; value objects are immutable.
- Run the ArchUnit suite (part of `verify`) and read what it actually asserts.
- If you deliberately changed the structure, update the ArchUnit rules in the
  same change, so a green build still means the rules hold.

## Gotchas
- **Weakening a rule to make code compile** is the failure mode to avoid. Fix the
  dependency direction instead; if a rule is genuinely wrong, change it
  explicitly and say why.
- Panache/JPA leaking into `domain/` — an import or annotation. Map in
  `infrastructure` instead.
- A new bounded context that no rule covers yet — extend the rules to include it.
- "It compiles" is not "the architecture holds." Run ArchUnit.
