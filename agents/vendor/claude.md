## Claude Code specifics

Sub-agents live in `.claude/agents/*.md` (frontmatter + system prompt) and are
generated from `agents/`. Delegate explicitly:

> Use the `implementer` subagent on: \<subtask\>

Sub-agents **cannot** spawn further sub-agents — all branching goes through you.

**Model steering:**
- **Per agent**: the `model:` field in the agent's frontmatter
  (`opus` | `sonnet` | `haiku`, a full model id, or `inherit`).
- **Global**: `CLAUDE_CODE_SUBAGENT_MODEL` forces one model for all sub-agents
  (highest precedence; useful for cost/compliance ceilings).
- **Cross-vendor** (OpenAI, Gemini, Mistral, local): use the `ai/` harness —
  Claude Code itself only routes between Claude models.

After editing an agent file on disk, restart the session; agents created or
edited via `/agents` take effect immediately. Project settings (permissions etc.)
go in `.claude/settings.json`.

In the `ai/` harness the same checkpoints are available as `--approve` /
`--interactive` (plan / result / final gates).
