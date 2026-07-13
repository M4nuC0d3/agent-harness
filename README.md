# Agent Harness — a coordinator + three roles, for any coding agent

A small, model-agnostic instruction layer. It turns whichever coding agent you
use into a **coordinator** that plans, delegates to three focused roles, and
refuses to accept work the **evaluator** hasn't passed. Underneath it, a real
enforcement layer stops the accidents that instructions alone cannot.

No runtime, no orchestrator, no API keys, no build step. Just files your agent
already knows how to read.

## Works with

| Tool | Reads | Native sub-agents? |
|---|---|---|
| **Codex** (ChatGPT) | `AGENTS.md` | no — adopt the role inline |
| **Claude Code** | `CLAUDE.md` → imports `AGENTS.md` | yes: `.claude/agents/*.md` |
| **Gemini CLI** | `GEMINI.md` → imports `AGENTS.md` | no — adopt the role inline |
| **Mistral Vibe** | `AGENTS.md` | yes, but not wired here (see Known gaps) |
| **Cursor, Copilot, Aider, Zed, Jules, …** | `AGENTS.md` | varies |

`AGENTS.md` is an open format stewarded by the Agentic AI Foundation and read by
20+ agents. Everything else imports it.

## Install

Copy into the root of the project you want to work in:

```bash
cp -r AGENTS.md CLAUDE.md GEMINI.md .geminiignore .claude/ evals/ /path/to/your-project/
```

Then start your agent (`claude`, `codex`, `gemini`, `vibe`) there and give it a
real goal:

> Add pagination to the `/users` endpoint, with tests.

It plans first, delegates `researcher` → `implementer` → `evaluator`, and pauses
for your approval before anything irreversible.

Already have an `AGENTS.md`? Merge — don't overwrite. Keep your project's build
commands and conventions; add the sections you want from this one.

## No generator, no drift

Every piece of content exists **exactly once**, in the format the tool actually
reads. There is nothing to regenerate and nothing to keep in sync:

```
AGENTS.md                 the canonical instructions — the only copy
CLAUDE.md                 3 lines + Claude specifics; imports AGENTS.md
GEMINI.md                 3 lines + Gemini specifics; imports AGENTS.md
.claude/agents/*.md       the three role prompts — the only copy
                          (YAML frontmatter for Claude Code; other tools read past it)
.claude/settings.json     sandbox + permission rules + hook registration
.claude/hooks/guard.py    session budget + opt-in accident catcher (config at the top)
.claude/hooks/trace.py    audit trail
.claude/hooks/test_*.py   the tests below
.geminiignore             keeps secrets out of Gemini's view
managed-settings.example.json   org-wide lockdown (deployed outside the repo)
evals/golden-tasks.md     does this setup actually work?
.agent/                   runtime: PROGRESS.md (committed), trace.jsonl (ignored)
```

An earlier version of this repo generated `CLAUDE.md`, `GEMINI.md` and the role
files from a shared source. That solved duplication by adding a build step —
and a build step for four markdown files is worse than the problem. Anthropic's
own advice applies to tooling as much as to agents: find the simplest thing that
works. Imports cover Claude Code and Gemini; Codex reads the canonical file
directly; the role prompts live where Claude Code wants them anyway.

## Instructions vs. enforcement

`AGENTS.md` is *context*: it lowers the **probability** of an accident. The
sandbox and permission rules lower the **possibility**. Layered as Anthropic
documents it:

| Layer | Mechanism | Guarantee |
|---|---|---|
| Container / worktree | blast radius | strongest, for untrusted code |
| **Sandbox** | OS-level isolation of Bash *and its children* | holds even when a prompt injection bypasses the model |
| **Permission rules** | declarative allow / ask / deny | reliable for paths, domains, tools |
| **Hooks** | your code, before the permission check | only what rules can't express |
| `AGENTS.md` | context the model reads | probabilistic |

Concretely, `.claude/settings.json` enables the sandbox with
`allowUnsandboxedCommands: false` — closing the escape hatch that would let a
failed command retry outside the boundary — denies reads of `~/.ssh` and
`~/.aws`, and restricts network egress to an allowlist. Permission rules deny
secrets, `curl`, `wget` and `sudo`, gate `WebFetch` behind a domain allowlist,
and prompt on `git push`, `rm -rf`, `terraform`, `kubectl`.

**Bash patterns are not a security control.** Arguments can be reordered,
variables expanded, wrappers used. That is why the guard's denylist is labelled
an *accident catcher* (`ACCIDENT_CATCHER = False` disables it) and why `curl` is
denied outright rather than pattern-matched. The hook exists for the two things
rules cannot do: count tool calls per session, and write an audit trace.

Test both without a model in the loop:

```bash
python .claude/hooks/test_guard.py  .claude/hooks/guard.py     # 24 behavioural cases
python .claude/hooks/test_policy.py .claude/settings.json      # sandbox + rules present
```

The guard denies only catastrophic targets (`rm -rf /`, `~`, `$HOME`, `*`) and
*asks* for everyday deletes like `rm -rf node_modules`. A guard that blocks real
work gets switched off, and then it protects nothing.

## Evals

Tests prove the hook behaves. They say nothing about whether the *instructions*
work. `evals/golden-tasks.md` holds six behavioural tasks: does it plan first,
does the evaluator actually gate, does it resist prompt injection, does the
sandbox hold when the model is wrong. Run them in a scratch repo, score
Pass/Fail, and add a task every time you hit a real failure.

## Choosing the model per role

The roles are model-agnostic. Where a tool lets you pin a model it is the
`model:` field in the sub-agent's frontmatter:

```yaml
---
name: evaluator
model: opus      # judgment → strongest
---
```

Convention: judgment → strongest, implementation → balanced, search →
fast/cheap. Claude Code can cap everything at once with
`CLAUDE_CODE_SUBAGENT_MODEL=haiku`. Other CLIs take `--model` at startup.

## Going programmatic

For unattended runs (CI, pipelines, products) use the vendor's agent SDK rather
than hand-writing an orchestrator: **Claude Agent SDK**, **OpenAI Agents SDK**,
**Google ADK**. Each ships the agent loop, tool execution, sub-agents and
permission hooks you would otherwise rebuild. The role prompts here are plain
markdown and drop straight into their sub-agent definitions.

## Monorepos

The **closest** `AGENTS.md` wins. Keep this root file to what applies
everywhere, and put package-specific build commands, framework conventions and
local anti-patterns in a nested `AGENTS.md` inside that package. Nested files
keep the root small, which is what keeps it read.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/agents` doesn't list the sub-agents | You edited files on disk — restart the Claude Code session. Agents created via `/agents` apply immediately. |
| The agent ignores `AGENTS.md` / `CLAUDE.md` | It must be in the directory you launched from (or a parent). Check with `/memory` (Claude Code) or `/memory show` (Gemini CLI). |
| Codex/Vibe ignore my `CODEX.md` / `MISTRAL.md` | Neither filename is read by anything. Both tools read `AGENTS.md`. |
| Gemini loads `GEMINI.md` but not the rest | Run `/memory refresh`. Imports resolve at load time, max depth 5. |
| Sandbox won't start on Linux/WSL2 | Install `bubblewrap` and `socat`. Native Windows and WSL1 are unsupported — use a container. |
| Heredocs (`<< EOF`) fail | A known sandbox limitation: the shell needs a temp file. Write the file, then run it. |
| The guard blocks something legitimate | Move it out of `ACCIDENT_PATTERNS` and add a `Bash(...)` **ask** rule in `.claude/settings.json`. Don't disable the sandbox. |
| Context feels bloated | `AGENTS.md` is 145 lines; Claude Code sees 184. Anthropic warns above ~200, and `@path` imports do **not** reduce context — they load at launch. |

## Known gaps

- **No project facts.** This layer is pure process — it does not know your build
  or test commands, which is the single highest-ROI section of an `AGENTS.md`.
  Run your tool's `/init` in the target repo and merge the result in.
- **Enforcement is wired for Claude Code only.** Codex has execpolicy and a
  sandbox, Gemini CLI has a sandbox flag, Vibe has per-tool permissions.
  `guard.py` is a plain stdin→JSON script and ports to any of them.
- **Mistral Vibe sub-agents are not shipped.** An earlier version generated
  `.vibe/agents/*.toml`, but the schema beyond `agent_type`/`description` was
  never verified against a live CLI, so it was removed rather than shipped
  broken. Vibe reads `AGENTS.md` and adopts roles inline.

## Verify before trusting

Hook schemas, frontmatter fields and import syntax move fast — published sources
already disagree on whether Claude Code exposes 27 or 30 hook lifecycle events.
Exit-code semantics have a real footgun: exit 1 blocks nothing, exit 2 blocks,
and mixing exit 2 with JSON on stdout silently discards the JSON.

The hooks here were tested against simulated stdin payloads, not a live CLI. The
sandbox settings were written against Anthropic's own example config but never
executed. Reported caveats worth knowing: the sandbox can fail open if it cannot
start, and its network filter does not inspect TLS, so domain fronting is
possible. Run `evals/golden-tasks.md` on your machine before trusting this setup
with anything irreversible.
