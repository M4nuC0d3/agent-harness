# PROGRESS

Plain markdown, no tooling. Copy to `.agent/PROGRESS.md` and keep it current —
update when a subtask passes the evaluator, not at the end of the run.

## State
- **Done:**
- **In flight:**
- **Next:**

## Decisions a fresh session would otherwise rediscover
- <decision> — because <reason>

## Edges
Record real relationships, not a flat list:

| Type | Meaning |
|---|---|
| `depends_on` | blocks start |
| `supersedes` | a plan revision replaces an earlier one |
| `caused` | bug → fix |
| `decided_by` | an implementation choice → the plan step that made it |

- `T4 depends_on T2`
- `T7 supersedes T3`
