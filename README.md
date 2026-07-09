# Agent Harness — a coordinator + three roles, for any coding agent

A small, model-agnostic instruction layer. It turns whichever coding agent you
use into a **coordinator** that plans, delegates to three focused roles, and
refuses to accept work the **evaluator** hasn't passed.

There is no runtime here — no orchestrator to install, no API keys, no code to
run. Just instructions your agent already knows how to read, generated from one
source so they can't drift apart.

## Works with

| Tool | Reads | Native sub-agents? |
|---|---|---|
| **Codex** (ChatGPT) | `AGENTS.md` | no — adopt the role inline |
| **Claude Code** | `CLAUDE.md` → imports `AGENTS.md` | yes: `.claude/agents/*.md` |
| **Gemini CLI** | `GEMINI.md` → imports `AGENTS.md` | no — adopt the role inline |
| **Mistral Vibe** | `AGENTS.md` | yes: `.vibe/agents/*.toml` |
| **Cursor, Copilot, Aider, Zed, Jules, …** | `AGENTS.md` | varies |

`AGENTS.md` is an open format stewarded by the Agentic AI Foundation and read by
20+ agents. Everything else either imports it or is generated from the same
source.

## Install (60 seconds, nothing to install)

Copy into the root of the project you want to work in:

```bash
cp -r agents/  AGENTS.md  CLAUDE.md  GEMINI.md  .claude/  .vibe/  /path/to/your-project/
```

Then start your agent (`claude`, `codex`, `gemini`, `vibe`) in that directory and
give it a real goal:

> Add pagination to the `/users` endpoint, with tests.

It will plan first, delegate to `researcher` → `implementer` → `evaluator`, and
pause for your approval before anything irreversible.

If your project already has an `AGENTS.md` or `CLAUDE.md`, merge rather than
overwrite: move your content into `agents/coordinator.md` first.

## What you get

- **A plan first.** The agent states the subtasks before touching anything.
- **A critic.** Nothing is accepted until `evaluator` returns PASS. Max 2
  revisions, then it escalates to you.
- **Human checkpoints.** Plan approval; before deletes, force-push, migrations;
  on repeated failure; and a final review.
- **Small contexts.** Each role gets a scoped brief and returns a distilled
  summary, so the coordinator's context fills with conclusions, not transcripts.

## One source, many tools

```
agents/                  ← EDIT ONLY HERE
├── coordinator.md       #   shared coordinator instructions (model-agnostic)
├── roles/*.md           #   researcher / implementer / evaluator prompts
├── roles.toml           #   per-role description + per-vendor tools/model
├── vendor/*.md          #   the bits that are genuinely tool-specific
└── sync.py              #   regenerates everything below

AGENTS.md                # generated — Codex, Mistral Vibe, 20+ others
CLAUDE.md                # generated — Claude Code (imports AGENTS.md)
GEMINI.md                # generated — Gemini CLI (imports AGENTS.md)
.claude/agents/*.md      # generated — Claude Code native sub-agents
.vibe/agents/*.toml      # generated — Mistral Vibe native sub-agents
```

```bash
python agents/sync.py          # regenerate
python agents/sync.py --check  # CI gate: fails if a generated file is stale
```

No dependencies — `sync.py` uses only the standard library (Python 3.11+).
Details in `agents/README.md`.

## Choosing the model per role

The roles are model-agnostic. Where a tool lets you pin a model, it's a field in
`agents/roles.toml`:

```toml
[roles.evaluator.claude]
model = "opus"     # judgment → strongest
```

Convention: judgment → strongest, implementation → balanced, search → fast/cheap.
For Claude Code you can also cap everything at once with
`CLAUDE_CODE_SUBAGENT_MODEL=haiku`. Other CLIs take a `--model` flag at startup.

## Going programmatic

For unattended runs (CI, pipelines, products), use the vendor's agent SDK rather
than hand-writing an orchestrator: **Claude Agent SDK**, **OpenAI Agents SDK**,
or **Google ADK**. Each ships the agent loop, tool execution, sub-agents, and
permission hooks that you would otherwise rebuild.

The roles in `agents/roles/` are plain prompts — paste them into an SDK's
sub-agent definitions and the same structure works there.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/agents` doesn't list the sub-agents | You edited files on disk — restart the Claude Code session. Agents created via `/agents` apply immediately. |
| The agent ignores `AGENTS.md` / `CLAUDE.md` | It must be in the directory you launched from (or a parent). In Claude Code check with `/memory`; in Gemini CLI with `/memory show`. |
| Edited `CLAUDE.md` and it got overwritten | It's generated. Edit `agents/coordinator.md` (or `agents/vendor/claude.md`) and run `python agents/sync.py`. |
| Codex/Vibe ignore my `CODEX.md` / `MISTRAL.md` | Neither filename is read by anything. Both tools read `AGENTS.md`. |
| Gemini loads `GEMINI.md` but not the roles | Run `/memory refresh`. Imports resolve at load time, max depth 5. |
| `Python 3.11+ required` | `sync.py` uses stdlib `tomllib`. On 3.10, `pip install tomli`. |

## Verify before trusting

Tool names, frontmatter fields, and import syntax change. The `.vibe/*.toml`
schema beyond `agent_type` / `description` is best-effort — check it against the
current Mistral Vibe docs. When a tool stops picking something up, compare
against its docs, fix the source in `agents/`, and regenerate.
