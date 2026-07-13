## Claude Code specifics

Sub-agents live in `.claude/agents/*.md` (frontmatter + system prompt), generated
from `agents/`. Delegate explicitly:

> Use the `implementer` subagent on: \<subtask\>

Sub-agents **cannot** spawn further sub-agents — all branching goes through you.

**Model steering:**
- **Per agent**: the `model:` field in the agent's frontmatter
  (`opus` | `sonnet` | `haiku`, a full model id, or `inherit`). Set it in
  `agents/roles.toml` under `[roles.<name>.claude]`, then regenerate.
- **Global**: `CLAUDE_CODE_SUBAGENT_MODEL` forces one model for all sub-agents
  (highest precedence; useful for cost/compliance ceilings).

After editing an agent file on disk, restart the session; agents created or
edited via `/agents` take effect immediately.

**Enforcement.** `.claude/settings.json` (generated from `agents/policy.toml`)
carries the permission rules and registers two hooks: a `PreToolUse` guard that
denies destructive commands, refuses writes to secrets, and enforces a per-
session tool-call ceiling; and a `PostToolUse` tracer that appends every call to
`.agent/trace.jsonl`. Hooks run before the permission check, so a `deny` holds
even under `--dangerously-skip-permissions`. A hook can tighten policy, never
loosen a `deny` rule. Change the policy, not the generated files.

For programmatic, unattended runs, use the **Claude Agent SDK** — it is the
Claude Code harness as a library (agent loop, sub-agents, hooks, permissions),
rather than a hand-written orchestrator.
