# GEMINI.md

The coordinator instructions and role definitions live in `AGENTS.md`:

@./AGENTS.md

## Gemini CLI specifics

Gemini CLI resolves `@file.md` imports (max depth 5), so nothing is duplicated
here. Use `/memory show` to inspect the assembled context and `/memory refresh`
after editing `AGENTS.md`.

Gemini CLI has no native sub-agent files. Adopt the role inline when you take on
a subtask: *"acting as the `evaluator` role from `.claude/agents/evaluator.md`,
review this change"*. The YAML frontmatter in those files is for Claude Code;
ignore it and read the prompt below it.

**Enforcement:** `.geminiignore` keeps secrets out of view, but ignore files are
advisory. For a hard block, run Gemini CLI with its sandbox enabled — and note
that its sandbox is **not** set up the way Claude Code's is. `sandbox-exec` only
exists on macOS, so **under WSL2 the only real boundary is a container**: install
Docker or Podman inside the distro and start Gemini with `GEMINI_SANDBOX=docker`
(or `-s`, or `"sandbox": "docker"` in `settings.json`). With native Docker-in-WSL2
(no Docker Desktop) you must enable `systemd` in `/etc/wsl.conf` and add your user
to the `docker` group, or Gemini quietly falls back to **no sandbox**. WSL1 is not
a supported baseline; see the README's *Prerequisites: Windows + WSL*. The
deterministic guard in `.claude/hooks/` is wired for Claude Code only; it is a
plain stdin→JSON script and ports easily.

**Model steering:** pass `--model` at startup. The roles are model-agnostic.

**Note:** when both `GEMINI.md` and `AGENTS.md` exist, some Gemini surfaces
prefer `GEMINI.md` — which is why this file imports the canonical one instead of
competing with it. You can also point the CLI straight at the shared file:

```json
{ "context": { "fileName": ["AGENTS.md", "GEMINI.md"] } }
```
