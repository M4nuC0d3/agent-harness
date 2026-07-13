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
| `policy.toml` | the enforcement policy: denied/asked commands, protected paths, tool-call ceiling |
| `hooks/guard.py` · `hooks/trace.py` | the deterministic layer (+ `hooks/test_guard.py`, 36 cases) |
| `evals/golden-tasks.md` | behavioural evals: does the setup actually work? |
| `vendor/claude.md` · `vendor/gemini.md` | the bits that are genuinely tool-specific |

## Generated (never edit)

| File | Read by |
|---|---|
| `AGENTS.md` | **Codex**, **Mistral Vibe**, and 20+ other agents — an open format stewarded by the Agentic AI Foundation |
| `CLAUDE.md` | Claude Code (thin; `@AGENTS.md` import + Claude specifics) |
| `GEMINI.md` | Gemini CLI (thin; `@./AGENTS.md` import + Gemini specifics) |
| `.claude/settings.json` | Claude Code: permission rules + hook registration |
| `.claude/hooks/*` | Claude Code: `guard.py`, `trace.py`, `policy.json` |
| `.claude/agents/*.md` | Claude Code native sub-agents (frontmatter + prompt) |
| `.vibe/agents/*.toml`, `.vibe/prompts/*.md` | Mistral Vibe native sub-agents |
| `.geminiignore` | Gemini CLI: keeps secrets out of view (advisory only) |

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

## Instructions vs. enforcement

Anthropic's own docs are blunt about it: an agent treats `CLAUDE.md` as context,
**not** as enforced configuration — to block an action regardless of what the
model decides, use a `PreToolUse` hook. The same split exists everywhere: for
Codex, `AGENTS.md` lowers the probability of an accident while execpolicy and
the sandbox lower the possibility; in Vibe, the `safety` field on a tool is a
visual hint with no enforcement behind it.

So this repo keeps two layers, both generated from `agents/policy.toml`:

- **Permission rules** (`.claude/settings.json`) — declarative allow/ask/deny for
  anything a pattern can express.
- **Hooks** (`.claude/hooks/`) — code that sees the real command. `PreToolUse`
  runs *before* the permission check, so its `deny` holds even under
  `--dangerously-skip-permissions`; a hook can tighten policy but can never
  loosen a `deny` rule. `PostToolUse` writes the audit trail.

The guard **fails closed**: if `policy.json` is missing or corrupt it blocks every
call and tells you to regenerate. A guard that silently stops guarding is worse
than one that stops the agent, because the human keeps believing they're covered.

Two deliberate calibrations:

- `rm -rf node_modules` **asks**; only `/`, `~`, `$HOME` and bare `*` are denied.
  A guard that blocks everyday work gets switched off, and then it protects nothing.
- Ignore files (`.geminiignore`) and permission rules can be worked around by
  other read paths. Only the hook is a reliable block.

Test it without a model in the loop:

```bash
python agents/hooks/test_guard.py agents/hooks/guard.py
```

## Context budget

Anthropic warns that instruction files over ~200 lines consume more context and
may reduce adherence — and that `@path` imports help organization but do **not**
reduce context, since imports load at launch. So the role prompts were pulled out
of `AGENTS.md`; an agent reads `agents/roles/<name>.md` only when it adopts that
role, and tools with native sub-agents load their own copy on delegation.

Current load: `AGENTS.md` 138 lines; Claude Code sees 171 (`CLAUDE.md` + import).
Keep it that way — measure after editing `coordinator.md`.

## Long runs

`.agent/PROGRESS.md` plus git history is how a fresh context window reconstructs
state. The coordinator is told to update it when a subtask passes the evaluator,
commit at green checkpoints, read it before planning, and spend the first context
window of a project on setup. `PROGRESS.md` is committed; `trace.jsonl` and the
session counters are gitignored.

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

## Known gaps

- **Project facts.** This layer is pure process. It does not know your build or
  test commands. Run `/init` in the target repo and merge into `coordinator.md`.
- **Enforcement ships wired for Claude Code only.** `guard.py` is a plain
  stdin→JSON script; porting it to Codex's execpolicy/hooks, Vibe's hooks, or
  Gemini's sandbox is straightforward but not done here.
- **Sub-agent least privilege** relies on the tool honoring `tools:` /
  `enabled_tools`. The hook does not enforce it.

## Verify before trusting

Hook schemas move fast — published sources already disagree on whether Claude
Code exposes 27 or 30 lifecycle events, and exit-code semantics have a real
footgun (exit 1 blocks nothing; exit 2 blocks; never mix exit 2 with JSON on
stdout). The `.vibe/*.toml` schema beyond `agent_type` / `description` is
best-effort. Everything here was tested against simulated payloads, not a live
CLI. When a tool stops picking something up, compare against its docs first, then
fix the source here and regenerate.
