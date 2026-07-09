# `ai/` — Async Multi-Agent Harness

A small, provider-agnostic harness built on two of Anthropic's agent patterns.
A **planner/coordinator** splits a goal into subtasks; **worker** sub-agents run
them **in parallel** (grouped into dependency *waves*); an **evaluator** (critic)
scores every result and sends weak ones back for revision. Each worker runs in an
**isolated context** and returns a **distilled summary**, and a human can be put
**in the loop** at three checkpoints. Every agent can run on a **different model /
vendor**, steered from `config.yaml` — not code.

```
Goal
 └─▶ Planner ──▶ [t1, t2, t3(dep t1,t2)]            (which model? -> models.planner)
        │  (+ optional HUMAN checkpoint on the plan)
        ▼
   Wave 1: t1 ‖ t2        Wave 2: t3                (waves from depends_on)
        │      │              │
        ▼      ▼              ▼
     Worker Worker         Worker                    (-> models.worker; scoped context in)
        │      │              │                       (distilled summary out)
        ▼      ▼              ▼
    Evaluator …           Evaluator                  (-> models.evaluator)
        │                    │
   pass/▲fail  ── fail ──▶ back to Worker (max N rounds)
        │  (+ optional HUMAN checkpoint on each result)
        └──────────┬─────────┘
                   ▼
                Synthesis  (+ optional HUMAN checkpoint on the final answer)
                   ▼
   final answer + runs/<id>.result.json + runs/<id>.jsonl (trace)
```

## How this maps to Anthropic's guidance

This harness deliberately follows Anthropic's published recommendations rather
than a heavyweight framework:

- **Orchestrator-workers** and **evaluator-optimizer** patterns from
  [*Building effective agents*](https://www.anthropic.com/engineering/building-effective-agents).
  The planner is the orchestrator; workers are the workers; the evaluator +
  revision loop is the optimizer.
- **The three principles** from the same post:
  1. *Simplicity* — plain `asyncio` and direct provider calls; no framework
     abstraction to hide the prompts.
  2. *Transparency* — the plan, the waves, and every accept/revise decision are
     printed as they happen, and mirrored into a JSONL trace.
  3. *Good ACI* (agent-computer interface) — each sub-agent has one focused
     system prompt and a narrow job; tools are the documented next extension.
- **Stopping conditions & human checkpoints** — Anthropic recommends letting an
  agent "pause for human feedback at checkpoints" and keeping hard stopping
  conditions. Both are first-class here (see HITL and Budget below).
- **Sub-agent context isolation** from
  [*Effective context engineering for AI agents*](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents):
  a sub-agent works in a clean context window and returns a condensed summary,
  so the coordinator accumulates conclusions, not raw transcripts.

## Quickstart

```bash
pip install -r ai/requirements.txt
cp ai/.env.example ai/.env      # add only the keys you actually use

# Dry run — no keys, no network (mock provider):
AI_FORCE_MODEL=mock:mock python -m ai.run "Build a CSV-to-JSON converter with tests"

# Real run (uses config.yaml):
python -m ai.run "Build a CSV-to-JSON converter with tests"

# With human checkpoints:
python -m ai.run --approve "Refactor module X"          # gate the plan only
python -m ai.run --interactive "Refactor module X"      # gate plan + results + final
python -m ai.run --interactive --results always "…"     # review every result
```

Programmatic use:

```python
import asyncio
from ai import run_goal
state = asyncio.run(run_goal("Summarize the open issues"))
print(state.final_output)
```

## Steering the models (the core knob)

Three levels, coarse to fine:

1. **Global, via env** — override every agent at once:
   `AI_FORCE_MODEL="anthropic:claude-haiku-4-5-20251001"` (cheap everywhere) or
   `AI_FORCE_MODEL="mock:mock"` (dry run).
2. **Per role, in `config.yaml`** — the normal case. Each role (`planner`,
   `worker`, `evaluator`, plus any you add) gets provider + model + temperature +
   `max_tokens`. Vendors may be mixed (e.g. planner = Claude Opus, worker = a
   local Llama, evaluator = Gemini).
3. **A custom provider at runtime** — `register_provider("name", MyProvider())`
   in `ai/models.py` (Azure, Bedrock, a router, …).

Implemented providers: `anthropic`, `openai`, `local` (any OpenAI-compatible
endpoint: Ollama / vLLM / LM Studio), `google`, `mock`.

## Human-in-the-loop checkpoints

Configured under `hitl:` in `config.yaml`, overridable by CLI flags. `mode: auto`
runs unattended; `mode: interactive` asks on the terminal. Three gates:

| Gate | When | Human can |
|---|---|---|
| `plan` | after planning, before any work | **approve** / **edit** the subtasks / **revise** (re-plan with feedback) / **abort** |
| `results` | after the evaluator scores a subtask (`off` / `on_fail` / `always`) | **accept** (override the critic) / **revise** (add guidance) / **abort** |
| `final` | before the synthesized answer is accepted | **accept** / **request changes** (re-opens the weakest subtask once) / **abort** |

Interactive prompts fall back to *approve* on EOF (non-interactive stdin), so
enabling HITL never deadlocks a pipe or CI job. Swap the terminal reviewer for a
web UI, Slack approval, or a queue by subclassing `Reviewer` in `ai/hitl.py` and
passing it to `AsyncOrchestrator(reviewer=...)`.

## Context isolation

Configured under `context:`. Each worker is handed only a **scoped brief** and
returns a short **summary** used for everything downstream:

- `policy: scoped` (default) — a worker sees only the summaries of *its
  dependencies*. `full` = full upstream results; `minimal` = just the goal;
  `none` = only its own subtask.
- `summary_target_tokens` — target size of each sub-agent's distilled summary.
  Workers emit their own summary after a `===SUMMARY===` marker; if a model omits
  it, the harness compacts the result deterministically as a fallback.
- The **full** result is still what the evaluator judges and what the final
  synthesis uses — only cross-agent *context* is compacted.

Because dependent tasks receive summaries rather than full transcripts, adding
more subtasks doesn't linearly inflate every downstream context window.

## Layout

| File | Purpose |
|---|---|
| `run.py` | CLI entry (`python -m ai.run "…"`), HITL flags |
| `loop.py` | `AsyncOrchestrator`: plan → waves(parallel) → evaluate → revise → synthesize, with checkpoints |
| `context.py` | `ContextManager`: scoped briefs in, distilled summaries out |
| `hitl.py` | `Reviewer` interface + `AutoReviewer` / `CLIReviewer` |
| `agents/planner.py` | splits the goal into subtasks + dependencies (JSON) |
| `agents/worker.py` | runs one subtask in isolation, returns result + summary |
| `agents/evaluator.py` | scores a result (pass/fail + score + feedback) |
| `agents/base.py` | model call with timeout, retries + backoff, token accounting |
| `models.py` | provider registry + vendor adapters |
| `config.py` / `config.yaml` | role→model mapping, budgets, context, HITL |
| `observability.py` | logger + JSONL trace (`runs/<id>.jsonl`) |
| `schemas.py` | data structures (Task, Budget, RunState, ContextPolicy, …) |

## What belongs in a harness? (checklist)

✅ = shipped here, 🔌 = a prepared hook/extension point.

**Core**
- ✅ Orchestration / planner-coordinator (`loop.py`, `planner.py`)
- ✅ Specialized sub-agents (`agents/`)
- ✅ Evaluator / critic with a revision loop
- ✅ Async execution with bounded parallelism (`asyncio` + semaphore)
- ✅ Dependency **waves** (`depends_on` → topological grouping)
- ✅ Multi-provider model routing per role (`config.yaml`, `models.py`)

**Control & humans**
- ✅ Budgets/limits: tokens, wall-clock, iterations, revision rounds → **guaranteed termination**
- ✅ Stopping conditions (`Budget.exceeded`)
- ✅ Retries + exponential backoff + timeouts (`base.py`)
- ✅ Graceful degradation (task → FAILED instead of crashing the run)
- ✅ Cost/token accounting (`Usage`)
- ✅ Human-in-the-loop at plan / result / final (`hitl.py`) with pluggable reviewers

**Context**
- ✅ Sub-agent context isolation (scoped briefs, `context.py`)
- ✅ Compaction of results into distilled summaries (worker summary or fallback)
- 🔌 Structured note-taking / shared scratchpad persisted outside the window
- 🔌 Prompt-/result-caching

**Observability & reproducibility**
- ✅ Structured logging + JSONL trace per run (`observability.py`)
- ✅ Result persistence (`runs/<id>.result.json`)
- ✅ Run ids + config snapshot in the trace
- 🔌 Checkpoint/resume mid-run (`RunState` is already serializable)

**Capabilities & safety (next steps)**
- 🔌 Tools / function-calling for agents (file/shell/HTTP tools; MCP servers) — invest in the ACI as Anthropic recommends
- 🔌 Guardrails: input/output validation, schema checks, content filters
- 🔌 Secret management beyond `.env` (Vault, etc.)
- 🔌 Eval/regression suite with golden tasks (the evaluator is the runtime half)
- 🔌 Per-provider rate limiting, circuit breakers

Rule of thumb: anything that **stops** an agent (budget, timeout, guardrail),
**checks** it (evaluator, schema, human), or makes it **reproducible** (trace,
persistence) belongs in the harness — not inside the individual agents.

## Notes on model ids

The Anthropic model ids in `config.yaml` are current as of writing; verify the
latest at <https://docs.claude.com/en/docs/about-claude/models>. The OpenAI and
Gemini ids in the commented examples are placeholders — substitute a current id.
The `google` adapter is intentionally minimal; check it against the
`google-genai` SDK version you install.
