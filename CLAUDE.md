# CLAUDE.md

The coordinator instructions and role definitions live in `AGENTS.md`:

@AGENTS.md

## Claude Code specifics

Sub-agents are in `.claude/agents/*.md`. Delegate explicitly: *"Use the
`implementer` subagent on: \<subtask\>"*. Sub-agents cannot spawn sub-agents —
all branching goes through you. Dispatch independent instances of one role in a
single message, each with its own git worktree (`isolation: "worktree"`) when
they'd touch the same files. Cap parallelism at what you can review, ~2-3.

**Enforcement** is specified in `AGENTS.md` (*Hard rules*) and configured in
`.claude/settings.json`. Only the Claude-Code-specific mechanics are here:

- Hooks run **before** the permission check, so a hook `deny` holds even under
  `--dangerously-skip-permissions`; a hook `allow` never loosens a `deny`.
- Rules evaluate `deny` → `ask` → `allow`, first match wins. A `deny` takes no
  allowlist exception — which is why WebFetch is gated with `ask`, not a
  deny-all (README, *Known issue: WebFetch*).
- Sandbox: Seatbelt on macOS, `bubblewrap` + `socat` on Linux/WSL2, **absent on
  WSL1 and native Windows**; `/sandbox` lists what is missing. `preflight.py` also
  stops when no sandbox is *configured* — a plugin install with no settings.json.
- `managed-settings.example.json`, deployed to the system path, makes a `deny`
  unoverridable org-wide — and must force-enable this plugin, or its hooks stop.

**Model steering:** the `model:` field per sub-agent (`opus` | `sonnet` |
`haiku` | full id | `inherit`) — read-only research cheap, implementation
balanced, the evaluator's judgment strongest. `CLAUDE_CODE_SUBAGENT_MODEL`
overrides all at once. Restart the session after editing an agent file on disk.

**Skills** (`.claude/skills/`) load only on a description match, so they cost
nothing until used. A workflow you would explain twice belongs there, not here.

For unattended runs use the **Claude Agent SDK**, not a hand-written orchestrator.
