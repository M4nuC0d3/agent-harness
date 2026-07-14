# CLAUDE.md

The coordinator instructions and role definitions live in `AGENTS.md`:

@AGENTS.md

## Claude Code specifics

Sub-agents are in `.claude/agents/*.md`. Delegate explicitly:
*"Use the `implementer` subagent on: \<subtask\>"*. Sub-agents cannot spawn
sub-agents — all branching goes through you.

**Enforcement**, in `.claude/settings.json`, layered as Anthropic documents it:

1. **Sandbox** (`/sandbox`) — OS-level isolation of Bash *and its children*:
   writes limited to the working directory, network to an allowlist, `~/.ssh`
   and `~/.aws` denied. `allowUnsandboxedCommands: false` means a command that
   fails under the sandbox cannot retry outside it. macOS uses Seatbelt; Linux
   and WSL2 use `bubblewrap` + `socat`. **WSL1 and native Windows have no
   sandbox** — on Windows run inside WSL2 (setup in the README's *Prerequisites*).
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
(`opus` | `sonnet` | `haiku` | full id | `inherit`). The defaults already match
cost to task difficulty — `haiku` for read-only research, `sonnet` for
implementation, `opus` for the evaluator's judgment; tune per role to trade spend
against rigor. `CLAUDE_CODE_SUBAGENT_MODEL` overrides all of them at once. After editing an agent file on disk, restart the
session; agents created via `/agents` apply immediately.

For programmatic, unattended runs use the **Claude Agent SDK** — the Claude Code
harness as a library — rather than a hand-written orchestrator.
