# CLAUDE.md

The coordinator instructions and role definitions live in `AGENTS.md`:

@AGENTS.md

## Claude Code specifics

Sub-agents are in `.claude/agents/*.md`. Delegate explicitly:
*"Use the `implementer` subagent on: \<subtask\>"*. Sub-agents cannot spawn
sub-agents — all branching goes through you.

**Enforcement**, in `.claude/settings.json`, layered as Anthropic documents it:

1. **Sandbox** (`/sandbox`) — OS-level isolation of Bash *and its children*.
   Writes limited to the working directory, network to an allowlist, `~/.ssh`
   and `~/.aws` denied. `allowUnsandboxedCommands: false` closes the escape
   hatch that would otherwise let a failed command retry outside the boundary.
   macOS uses Seatbelt; Linux/WSL2 need `bubblewrap` and `socat`.
2. **Permission rules** — reliable for paths, domains and whole tools. Not for
   Bash *arguments*: those are string matches and are trivially evaded, which is
   why `curl`/`wget` are denied outright and fetching goes through
   `WebFetch(domain:…)` rules.
3. **Hooks** — only what the above cannot express: a per-session tool-call
   ceiling and an audit trace. Hooks run before the permission check, so a hook
   `deny` holds even under `--dangerously-skip-permissions`; a hook `allow` can
   never loosen a `deny`.

The bash denylist in `.claude/hooks/guard.py` is an **accident catcher, not a
boundary** (`ACCIDENT_CATCHER = False` turns it off). For org-wide lockdown,
deploy `managed-settings.example.json`: a managed `deny` cannot be overridden.

**Model steering:** the `model:` field in each sub-agent's frontmatter
(`opus` | `sonnet` | `haiku` | full id | `inherit`). `CLAUDE_CODE_SUBAGENT_MODEL`
overrides all of them at once. After editing an agent file on disk, restart the
session; agents created via `/agents` apply immediately.

For programmatic, unattended runs use the **Claude Agent SDK** — the Claude Code
harness as a library — rather than a hand-written orchestrator.
