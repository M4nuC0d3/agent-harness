# Agent Harness — Getting Started with Claude Code

A coordinator setup for Claude Code plus a programmatic multi-agent harness.

There are **two ways to use this**, and you can use either on its own:

| | **A. Native Claude Code** | **B. The `ai/` harness** |
|---|---|---|
| What it is | Claude Code acts as coordinator, delegating to sub-agents | A Python orchestrator you run from the terminal |
| Setup | copy 2 things into your project | `pip install` + an API key |
| Models | Claude models only (opus / sonnet / haiku) | Claude, OpenAI, Gemini, local — mixed in one run |
| Parallelism | Claude Code decides | real `asyncio`, dependency waves |
| Cost | your Claude Code plan | billed against your API key |
| Best for | interactive work inside a repo | scripted, parallel, or mixed-vendor runs |

**Start with A.** Add B only when you need cross-vendor models or a scriptable pipeline.

---

## A. Use it in Claude Code (2 minutes, no Python, no API key)

### 1. Copy two things into your project

From this repo into the **root of the project you want to work in**:

```bash
cp CLAUDE.md              /path/to/your-project/
cp -r .claude             /path/to/your-project/
```

That gives your project:

```
your-project/
├── CLAUDE.md                  # makes Claude Code the planner/coordinator
└── .claude/agents/
    ├── researcher.md          # gathers context (read-only, haiku)
    ├── implementer.md         # writes code + runs it (sonnet)
    └── evaluator.md           # reviews results, PASS/FAIL (read-only, opus)
```

If your project already has a `CLAUDE.md`, don't overwrite it — paste the
sections you want (Role, Sub-agents, Human checkpoints) into yours.

### 2. Start Claude Code and verify

```bash
cd /path/to/your-project
claude
```

Then run `/agents`. You should see `researcher`, `implementer`, and `evaluator`
listed. If not, see Troubleshooting below.

### 3. Just ask for something

Claude Code reads `CLAUDE.md` automatically. Give it a real goal:

> Add pagination to the `/users` endpoint, with tests.

It will plan, show you the plan, delegate to the sub-agents, and have
`evaluator` check the work before accepting it. You can also delegate by hand:

> Use the `researcher` subagent to find how auth middleware is wired up.

> Use the `implementer` subagent on: add a `--limit` flag to the CLI.

### 4. What you get

- **A plan first.** Claude states the subtasks before touching anything.
- **A critic.** Nothing is accepted until `evaluator` returns PASS.
- **Checkpoints.** It pauses for your approval on the plan, before anything
  irreversible (deletes, force-push, migrations), and after repeated failure.
- **Small contexts.** Each sub-agent starts with a clean context window and
  returns a short summary, so the main session stays focused.

### 5. Choose the model per agent

Edit the frontmatter of any file in `.claude/agents/`:

```yaml
---
name: implementer
model: sonnet        # opus | sonnet | haiku | a full model id | inherit
---
```

Convention here: judgment → `opus`, implementation → `sonnet`, search → `haiku`.

Force **all** sub-agents onto one model (e.g. to cap cost), no file edits:

```bash
CLAUDE_CODE_SUBAGENT_MODEL=haiku claude
```

> Sub-agents cannot spawn sub-agents. All branching goes through the coordinator.
> If you need agents that spawn agents across vendors, that's what `ai/` is for.

---

## B. Use the `ai/` harness

### 1. Try it with zero setup

No keys, no network — the `mock` provider runs the whole loop offline. Run this
from the **repo root** (the folder containing `ai/`):

```bash
pip install pyyaml
AI_FORCE_MODEL=mock:mock python -m ai.run "Build a CSV-to-JSON converter with tests"
```

You'll see the plan, the dependency waves, parallel workers, and evaluator
scores. Nothing is billed. This is the fastest way to see the shape of a run.

### 2. Run it for real

```bash
pip install -r ai/requirements.txt
cp ai/.env.example ai/.env       # add only the keys you actually use
python -m ai.run "Build a CSV-to-JSON converter with tests"
```

> **Cost note:** the harness calls the API with your `ANTHROPIC_API_KEY`. That is
> billed per token and is **separate from your Claude Code subscription**. Start
> with the mock run, and keep the `budget:` limits in `ai/config.yaml` tight.
> If you'd rather stay on your plan, see "Run it on your subscription" below.

### 3. Keep yourself in the loop

```bash
python -m ai.run --approve      "Refactor module X"   # approve the plan, then run
python -m ai.run --interactive  "Refactor module X"   # plan + results + final
python -m ai.run --interactive --results always "…"   # review every single result
```

At each checkpoint you can approve, edit the plan, send work back with feedback,
or abort. If stdin isn't a terminal (CI, a pipe), every gate auto-approves rather
than hanging.

### 4. Run it on your subscription instead of an API key

Set a role's provider to one of the CLI providers. They shell out to the vendor's
agent CLI, which authenticates with your account login — so usage draws on your
plan, not an API key. The CLI must be installed and logged in.

```yaml
# ai/config.yaml
planner: { provider: claude_cli, model: sonnet }    # `claude -p`
worker:  { provider: codex_cli,  model: inherit }   # `codex exec`
worker:  { provider: gemini_cli, model: inherit }   # `gemini -p`
```

Or for one run: `AI_FORCE_MODEL=claude_cli:sonnet python -m ai.run "…"`

Caveats worth knowing: `temperature`/`max_tokens` are ignored, token counts are
estimates, each call spawns a process (set `loop.max_concurrency: 2`), and
vendors recommend API keys for unattended/CI work. Details in `ai/README.md`.

### 5. Pick models per role

Edit `ai/config.yaml` — no code changes:

```yaml
models:
  planner:   { provider: anthropic, model: claude-opus-4-8 }
  worker:    { provider: local,     model: llama3.1:70b }     # via Ollama
  evaluator: { provider: google,    model: gemini-2.5-pro }
```

Or override everything at once for one run:

```bash
AI_FORCE_MODEL=anthropic:claude-haiku-4-5-20251001 python -m ai.run "…"
```

### 6. Let Claude Code drive the harness

Inside a Claude Code session you can simply say:

> Run `AI_FORCE_MODEL=mock:mock python -m ai.run "summarize the open TODOs"`
> and tell me what the plan looked like.

Every run also writes:

- `runs/<id>.jsonl` — a full, greppable trace of every model call and decision
- `runs/<id>.result.json` — the final state (tasks, scores, summaries, tokens)

Full details, the checklist of what belongs in a harness, and how this maps to
Anthropic's published guidance: **[`ai/README.md`](ai/README.md)**.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/agents` doesn't list the sub-agents | You edited the files on disk — restart the Claude Code session. Agents created via `/agents` apply immediately. |
| Claude ignores `CLAUDE.md` | It must be in the directory you launched `claude` from (or a parent). Check with `/memory`. |
| `No module named ai` | Run `python -m ai.run` from the repo root, the folder that contains `ai/`. |
| `PyYAML is required` | `pip install pyyaml` |
| `Unknown provider 'x'` | Typo in `config.yaml`, or register it: `register_provider("x", MyProvider())`. |
| Missing API key | Copy `ai/.env.example` to `ai/.env` and fill it in, or `export ANTHROPIC_API_KEY=…`. |
| A run costs more than expected | Lower `budget.max_tokens` / `max_iterations` in `ai/config.yaml`, or `AI_FORCE_MODEL=anthropic:claude-haiku-4-5-20251001`. |
| Interactive prompts never appear | `--interactive` needs a real terminal; piped stdin auto-approves by design. |
| `'claude' not found on PATH` | Install the CLI and log in, or set `AI_CLAUDE_BIN` to its full path. |
| A CLI provider fails after a vendor changes flags | Override without editing code: `AI_CLAUDE_ARGS="-p {prompt}"` (same for `AI_CODEX_ARGS`, `AI_GEMINI_ARGS`). |
| `gemini_cli` bills the API anyway | Unset `GEMINI_API_KEY`; otherwise the CLI authenticates with the key. |

## Layout

```
CLAUDE.md              coordinator instructions for Claude Code
.claude/agents/        native Claude Code sub-agents (researcher/implementer/evaluator)
ai/                    the async Python harness  (see ai/README.md)
  run.py               CLI entry point
  loop.py              orchestrator: plan → waves → evaluate → revise → synthesize
  hitl.py              human checkpoints (plan / result / final)
  context.py           sub-agent context isolation + summary compaction
  providers/           one module per vendor: API key or subscription (CLI) path
  config.yaml          which model each role uses, budgets, HITL, context policy
```

## Notes

- Model ids in `ai/config.yaml` are current as of writing — verify the latest at
  <https://docs.claude.com/en/docs/about-claude/models>. The OpenAI and Gemini
  ids in the commented examples are placeholders.
- `runs/` is gitignored; it fills up with traces.
