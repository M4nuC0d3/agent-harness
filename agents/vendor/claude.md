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

**Enforcement**, in the order Anthropic documents, all generated from
`agents/policy.toml` into `.claude/settings.json`:

1. **Sandbox** (`/sandbox`) — OS-level isolation of Bash *and its children*.
   Writes limited to the working directory, network limited to an allowlist,
   `~/.ssh` and `~/.aws` denied. `allowUnsandboxedCommands: false` closes the
   escape hatch that would otherwise let Claude retry a failed command outside
   the boundary. macOS uses Seatbelt; Linux/WSL2 need `bubblewrap` and `socat`.
2. **Permission rules** — reliable for paths, domains and whole tools. Do *not*
   use `Bash(...)` patterns to constrain arguments; they are string matches and
   are trivially evaded. That is why `curl`/`wget` are denied outright and
   fetching goes through `WebFetch(domain:...)` rules.
3. **Hooks** — only what the above cannot express: a per-session tool-call
   ceiling, and a `PostToolUse` audit trace to `.agent/trace.jsonl`. Hooks run
   before the permission check, so a hook `deny` holds even under
   `--dangerously-skip-permissions`; a hook `allow` can never loosen a `deny`.

The bash denylist in the hook is an **accident catcher, not a boundary**
(`[bash] enabled = false` turns it off). For org-wide lockdown deploy
`managed-settings.example.json` — a managed `deny` cannot be overridden.

For programmatic, unattended runs, use the **Claude Agent SDK** — it is the
Claude Code harness as a library (agent loop, sub-agents, hooks, permissions),
rather than a hand-written orchestrator.
