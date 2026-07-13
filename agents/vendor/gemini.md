## Gemini CLI specifics

`AGENTS.md` (imported above) already contains the coordinator instructions and
all three role prompts — Gemini CLI resolves `@file.md` imports, so nothing is
duplicated here. Use `/memory show` to inspect the assembled context and
`/memory refresh` after editing any source file under `agents/`.

Gemini CLI has no native sub-agent files. Adopt the role inline when you take on
a subtask ("acting as the `evaluator` role from AGENTS.md, review this change").

**Model steering:** pass `--model` when you start the CLI; the roles themselves
are model-agnostic.

**Enforcement:** `.geminiignore` keeps secrets out of the agent's view, but
ignore files are advisory. For a hard block, run Gemini CLI with its sandbox
enabled, or port `agents/hooks/guard.py` to Gemini's hook mechanism. The
deterministic guard currently ships wired up for Claude Code only.

**Note:** when both `GEMINI.md` and `AGENTS.md` exist in a directory, some Gemini
surfaces prefer `GEMINI.md` — which is why this file imports the canonical one
rather than competing with it. You can also point Gemini CLI straight at the
shared file via `settings.json`:

```json
{ "context": { "fileName": ["AGENTS.md", "GEMINI.md"] } }
```
