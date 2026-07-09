# `agents/` — one source, many tools

Every agent instruction file in this repo is **generated** from this directory.
Edit here, then run:

```bash
python agents/sync.py          # regenerate
python agents/sync.py --check  # CI: fail if anything is stale
```

No third-party packages — stdlib `tomllib` only (Python 3.11+).

## Source (edit these)

| File | What it is |
|---|---|
| `coordinator.md` | the shared coordinator instructions — model- and vendor-agnostic |
| `roles/researcher.md` · `roles/implementer.md` · `roles/evaluator.md` | the three role prompts |
| `roles.toml` | per-role description + per-vendor tools/model |
| `vendor/claude.md` · `vendor/gemini.md` | the bits that are genuinely tool-specific |

## Generated (never edit)

| File | Read by |
|---|---|
| `AGENTS.md` | **Codex**, **Mistral Vibe**, and 20+ other agents — an open format stewarded by the Agentic AI Foundation |
| `CLAUDE.md` | Claude Code (thin; `@AGENTS.md` import + Claude specifics) |
| `GEMINI.md` | Gemini CLI (thin; `@./AGENTS.md` import + Gemini specifics) |
| `.claude/agents/*.md` | Claude Code native sub-agents (frontmatter + prompt) |
| `.vibe/agents/*.toml`, `.vibe/prompts/*.md` | Mistral Vibe native sub-agents |

## Why a generator, not just imports?

Import support is inconsistent, so no single mechanism covers every tool:

- **Claude Code** resolves `@path` imports in `CLAUDE.md`.
- **Gemini CLI** resolves `@file.md` imports in `GEMINI.md` (depth limit 5).
- **Codex** reads `AGENTS.md` as plain markdown — **no import syntax**.

So `AGENTS.md` must be self-contained, while `CLAUDE.md` and `GEMINI.md` stay
thin and import it. Rendering all of them from one source is the only way to get
both without maintaining the same instructions three times.

`--check` in CI proves it: edit a role body and exactly the files that *embed*
it go stale, while the ones that *import* it don't.

## There is no `MISTRAL.md` or `CODEX.md` — on purpose

Those filenames aren't read by anything:

- **Codex** reads `AGENTS.md` at the repo root (its global file lives in
  `~/.codex/`, not in your project).
- **Mistral Vibe** also reads `AGENTS.md`, walking up from the working directory.

Adding vendor-named files that no tool loads would create drift with no benefit.
`CLAUDE.md` and `GEMINI.md` exist only because those two tools look for their own
filename first.

## Sub-agent support differs

| Tool | Native sub-agents? | Where |
|---|---|---|
| Claude Code | yes | `.claude/agents/*.md` |
| Mistral Vibe | yes (spawned via its `task` tool) | `.vibe/agents/*.toml` |
| Codex | no | adopt the role inline |
| Gemini CLI | no | adopt the role inline |

Where a tool has no sub-agent mechanism the roles still work: they're spelled out
in `AGENTS.md`, and the agent adopts one per subtask. Context isolation then
becomes a discipline rather than a mechanism — the loop is unchanged.

## Model steering

The roles say nothing about models. Where a tool supports pinning one, it lives
in `roles.toml`:

```toml
[roles.evaluator.claude]
tools = ["Read", "Grep", "Glob", "Bash"]
model = "opus"
```

Claude Code reads that as the sub-agent's `model:` frontmatter field;
`CLAUDE_CODE_SUBAGENT_MODEL` overrides all of them at once. Other CLIs take a
`--model` flag when you start them.

## Adding a role or a vendor

- **New role**: add `roles/<name>.md`, add a `[roles.<name>]` block to
  `roles.toml` (plus `[roles.<name>.claude]` / `[roles.<name>.vibe]`), append the
  name to `order`, then `python agents/sync.py`.
- **New vendor**: add a `render_*` function in `sync.py` and wire it into
  `build()`. Keep `AGENTS.md` neutral — vendor extras belong in that tool's own
  file, or in this README if the tool has no file of its own.

## Going programmatic

Don't rebuild an orchestrator around these prompts. For unattended runs use the
vendor's agent SDK — **Claude Agent SDK**, **OpenAI Agents SDK**, **Google ADK** —
which ship the agent loop, tool execution, sub-agents, and permission hooks. The
role prompts here drop straight into their sub-agent definitions.

## Verify before trusting

The `.vibe/*.toml` schema beyond `agent_type` / `description` is best-effort;
check it against the current Mistral Vibe docs, which document the prompt
directory at user level. Tool names, frontmatter fields, and import syntax all
change — when a tool stops picking something up, compare against its docs first,
then fix the source here and regenerate.
