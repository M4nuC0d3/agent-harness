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
edited via `/agents` take effect immediately. Project settings (permissions etc.)
go in `.claude/settings.json`.

For programmatic, unattended runs, use the **Claude Agent SDK** — it is the
Claude Code harness as a library (agent loop, sub-agents, hooks, permissions),
rather than a hand-written orchestrator.
