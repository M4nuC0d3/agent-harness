# `ai/` — Async Multi-Agent Harness

Ein kleines, provider-agnostisches Harness: ein **Planner/Coordinator** zerlegt
ein Ziel in Subtasks, **Worker**-Sub-Agenten arbeiten sie **parallel** ab, ein
**Evaluator** (Kritiker) prüft jedes Ergebnis und schickt es bei Bedarf zur
Überarbeitung zurück. Jeder Agent kann auf einem **anderen Modell / anderen
Anbieter** laufen — gesteuert über `config.yaml`, nicht über Code.

```
Ziel
 └─▶ Planner ──▶ [Subtask 1, Subtask 2, …]         (welches Modell? -> models.planner)
                    │
        ┌───────────┼───────────┐  (parallel, begrenzt durch max_concurrency)
        ▼           ▼           ▼
     Worker      Worker      Worker                 (-> models.worker)
        │           │           │
        ▼           ▼           ▼
    Evaluator   Evaluator   Evaluator               (-> models.evaluator)
        │           │           │
     pass/▲fail  pass/▲fail  pass/▲fail   ── fail -> zurück an Worker (max N Runden)
        └───────────┴───────────┘
                    ▼
                 Synthese ──▶ Endergebnis + runs/<id>.result.json + runs/<id>.jsonl (Trace)
```

## Schnellstart

```bash
pip install -r ai/requirements.txt
cp ai/.env.example ai/.env      # Keys eintragen (nur die, die du nutzt)

# Trockenlauf ohne Keys / ohne Netz (Mock-Provider):
AI_FORCE_MODEL=mock:mock python -m ai.run "Baue einen CSV-zu-JSON-Konverter mit Tests"

# Echter Lauf (nutzt config.yaml):
python -m ai.run "Baue einen CSV-zu-JSON-Konverter mit Tests"

# Mit Freigabe des Plans durch einen Menschen:
python -m ai.run --approve "Refactore Modul X"
```

Programmatischer Aufruf:

```python
import asyncio
from ai import run_goal
state = asyncio.run(run_goal("Fasse die offenen Issues zusammen"))
print(state.final_output)
```

## Modelle steuern (der wichtigste Punkt)

Drei Ebenen, von grob nach fein:

1. **Global per Env** — überschreibt alle Agenten auf einmal:
   `AI_FORCE_MODEL="anthropic:claude-haiku-4-5-20251001"` (billig überall) oder
   `AI_FORCE_MODEL="mock:mock"` (Trockenlauf).
2. **Pro Rolle in `config.yaml`** — der Normalfall. Jede Rolle (`planner`,
   `worker`, `evaluator`, plus eigene) bekommt Provider + Modell + Temperatur +
   `max_tokens`. Anbieter dürfen gemischt werden (z. B. Planner = Claude Opus,
   Worker = lokales Llama, Evaluator = Gemini).
3. **Eigener Provider zur Laufzeit** — `register_provider("name", MyProvider())`
   in `ai/models.py` andocken (Azure, Bedrock, ein Router, …).

Implementierte Provider: `anthropic`, `openai`, `local` (jeder
OpenAI-kompatible Endpoint: Ollama / vLLM / LM Studio), `google`, `mock`.

## Aufbau

| Datei | Zweck |
|---|---|
| `run.py` | CLI-Einstieg (`python -m ai.run "…"`) |
| `loop.py` | `AsyncOrchestrator`: plan → execute(parallel) → evaluate → revise |
| `agents/planner.py` | zerlegt das Ziel in Subtasks (JSON) |
| `agents/worker.py` | bearbeitet einen Subtask, berücksichtigt Feedback |
| `agents/evaluator.py` | bewertet Ergebnis (Score + pass/fail + Feedback) |
| `agents/base.py` | Modell-Call mit Timeout, Retries + Backoff, Token-Zählung |
| `models.py` | Provider-Registry + Anbieter-Adapter |
| `config.py` / `config.yaml` | Rollen→Modell-Mapping, Budgets, Loop-Settings |
| `observability.py` | Logger + JSONL-Trace (`runs/<id>.jsonl`) |
| `schemas.py` | Datenstrukturen (Task, Budget, RunState, …) |

## Was gehört (noch) in ein Harness?

Deine Frage — hier die vollständige Checkliste. ✅ = in diesem Gerüst enthalten,
🔌 = als Hook/Stelle vorbereitet, an der du erweiterst.

**Kern**
- ✅ Orchestrierung / Planner-Coordinator (`loop.py`, `planner.py`)
- ✅ Spezialisierte Sub-Agenten (`agents/`)
- ✅ Evaluator / Kritiker mit Revisions-Schleife
- ✅ Async-Ausführung mit begrenzter Parallelität (`asyncio` + Semaphore)
- ✅ Multi-Provider-Modell-Routing pro Rolle (`config.yaml`, `models.py`)

**Robustheit & Kontrolle**
- ✅ Budgets/Limits: Token, Wall-Clock, Iterationen, Revisions-Runden → **garantiertes Ende**
- ✅ Abbruch-/Terminierungsbedingungen (`Budget.exceeded`)
- ✅ Retries + exponentielles Backoff + Timeouts (`base.py`)
- ✅ Fehlerbehandlung / Graceful Degradation (Task→FAILED statt Absturz)
- ✅ Kosten-/Token-Accounting (`Usage`)
- ✅ Human-in-the-Loop-Freigabe (`--approve` / `require_human_approval`)

**Beobachtbarkeit & Reproduzierbarkeit**
- ✅ Strukturiertes Logging + JSONL-Trace pro Run (`observability.py`)
- ✅ Persistenz des Ergebnisses (`runs/<id>.result.json`)
- ✅ Run-IDs, Config-Snapshot im Trace
- 🔌 Checkpoint/Resume mitten im Lauf (RunState ist bereits serialisierbar)

**Fähigkeiten & Sicherheit (nächste sinnvolle Schritte)**
- 🔌 Tools / Function-Calling für Agenten (Datei-, Shell-, HTTP-Tools; MCP-Server)
- 🔌 Guardrails: Ein-/Ausgabe-Validierung, Schema-Checks, Content-Filter
- 🔌 Geteiltes Gedächtnis / Blackboard zwischen Agenten (aktuell einfacher `context`-String)
- 🔌 Task-Abhängigkeiten (`depends_on`) als Wellen ausführen (Grundgerüst im `loop.py` kommentiert)
- 🔌 Prompt-Caching / Ergebnis-Caching
- 🔌 Secret-Management jenseits `.env` (Vault o. Ä.)
- 🔌 Eval-/Regressions-Suite mit Golden-Tasks (der Evaluator ist der Laufzeit-Teil davon)
- 🔌 Rate-Limiting pro Anbieter, Circuit-Breaker

Faustregel: Alles, was einen Agenten **stoppen** (Budget, Timeout, Guardrail),
**prüfen** (Evaluator, Schema) oder **nachvollziehen** (Trace, Persistenz) lässt,
gehört ins Harness — nicht in die einzelnen Agenten.
