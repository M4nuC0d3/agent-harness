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
| **Cursor, Copilot, Aider, Zed, ZCode, Jules, …** | `AGENTS.md` | varies |

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

**Requirements.** Each CLI installs itself (`claude`, `codex`, `gemini`, …). The
only *extra* dependency is **Python 3**: the two hooks run as
`python3 .claude/hooks/guard.py` / `trace.py`. They're stdlib-only, so any Python
3 works — but if `python3` isn't on `PATH` they don't fail loudly, they silently
no-op, and an absent `PreToolUse` hook blocks nothing (see *Verify before
trusting*). That quietly drops the session budget, the accident catcher **and**
the audit trace — the whole hook layer — while the sandbox and permission rules
stay up. Run `python3 --version` before you rely on enforcement.

Already have an `AGENTS.md`? Merge — don't overwrite. Keep your project's build
commands and conventions; add the sections you want from this one.

## Prerequisites: Windows + WSL

On Windows, run this harness — and the agent — **inside WSL2**. Not native
Windows, and not WSL1. This isn't a preference: the enforcement layer leans on
Linux kernel isolation primitives (user + mount namespaces, seccomp, Landlock)
that native Windows doesn't expose and WSL1 doesn't implement. The instructions
still load anywhere, but the *sandbox* — the one guarantee that holds when a
prompt injection gets past the model — either silently degrades or refuses to
start outside WSL2. Treat WSL2 (or a Linux container) as the baseline.

> Some tools now ship a native-Windows sandbox of their own (Codex, with an
> emerging one for others). Those are real, but this harness's `settings.json`
> assumes the Linux sandbox and is validated against it — so WSL2 is the
> supported path here.

One-time setup, from an elevated PowerShell:

```powershell
wsl --install                 # WSL2 + a default Ubuntu
wsl --set-default-version 2   # new distros as v2, not v1
wsl -l -v                     # VERSION must read 2 for your distro
```

Then work **inside the Linux filesystem**, not the Windows mount:

```text
✅  ~/code/your-project              native ext4 — fast, clean POSIX paths
❌  /mnt/c/Users/you/your-project    crosses the 9P bridge — slow, mixed paths
```

`/mnt/c` works, but its per-file latency compounds badly across the hundreds of
reads and writes an agentic run makes, and the mixed path semantics muddy the
sandbox's working-directory boundary. Clone into `~` and install the agent files
there.

One more Windows→WSL gotcha: check the repo out with **LF line endings**
(`git config --global core.autocrlf input`, or ship a `.gitattributes`). A file
that arrives with CRLF breaks shell heredocs and any script run directly by its
shebang — and those failures read as sandbox or tooling bugs, not what they are.

### The instructions are shared; the sandbox setup is not

Every agent reads the *same* `AGENTS.md` and the *same* role prompts, so their
**behaviour is identical**. Their **enforcement is not**: each draws the boundary
with a different OS mechanism, so what you install under WSL2 differs per tool.

| Agent | Reads | Boundary under WSL2 | Install / enable |
|---|---|---|---|
| **Claude Code** | `CLAUDE.md` | `bubblewrap` + `socat`, in the distro — no container | `sudo apt-get install bubblewrap socat`. Ubuntu 24.04+: also allow `bwrap` user namespaces (AppArmor). `/sandbox` → *Dependencies* lists anything missing. |
| **Codex** | `AGENTS.md` | Landlock + seccomp, in the distro — no container | Node 22+; nothing extra for the sandbox. WSL1 is seen as "linux" but fails the seccomp/Landlock probe — you must be on WSL2. |
| **Gemini CLI** | `GEMINI.md` | **Container only** (Docker/Podman) — `sandbox-exec` is macOS-only, so there's no host-level boundary here | A Docker/Podman engine running *in* the distro, then `GEMINI_SANDBOX=docker` (or `-s`). Native Docker-in-WSL2 (no Docker Desktop): enable `systemd` in `/etc/wsl.conf` and join the `docker` group, or Gemini silently falls back to **no** sandbox. |
| **Cursor, Copilot, Aider, Zed, ZCode, Vibe, …** | `AGENTS.md` | varies — most have no OS sandbox | `.claude/settings.json` and the hooks **don't apply here** — a non-Claude-Code tool doesn't read them. Get the boundary from an OS-level sandbox (WSL2 + a container) and reproduce the deny/ask policy in the tool's own permission controls (e.g. ZCode's per-agent read/write permissions). A CLI that exposes its *own* pre-tool hook can reuse `guard.py` — see *Known gaps*. |

So the answer to the obvious follow-up — *is the behaviour identical across
agents?* — is: yes for the instructions, no for enforcement. Claude Code and
Codex isolate at the host level inside the distro; Gemini CLI needs a container
running; the `AGENTS.md`-only tools get neither the `.claude/` permission rules
nor the hooks — those take effect only under Claude Code — so they need an
OS-level sandbox plus whatever permission controls the tool itself provides. Set
your expectations by the row above.

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
managed-settings.example.json   org-wide lockdown TEMPLATE — deploy outside the repo; never read from it
evals/golden-tasks.md     does this setup actually work?
.agent/                   runtime: PROGRESS.md (committed), trace.jsonl (ignored)
```

> **`managed-settings.example.json` is a template, not live config — nothing in
> this repo reads it.** Claude Code loads managed settings only from a fixed
> *system* path that needs admin rights: `/etc/claude-code/managed-settings.json`
> on Linux/WSL, `/Library/Application Support/ClaudeCode/managed-settings.json` on
> macOS, and the equivalent `ClaudeCode` path on Windows (check the docs — sources
> disagree between `Program Files` and `ProgramData`). Copy the file there, renamed
> to `managed-settings.json`, to enforce an org-wide lockdown. Living *outside* the
> repo is the whole point: a `deny` a developer could edit or `git revert` away
> would enforce nothing.

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

## Recommendations

Beyond what's already wired, these are the agentic-coding habits current practice
converges on. Optional and opinionated — adopt what fits.

- **Push repeated workflows into skills, not this file.** On-demand context
  (loaded only when its description matches) keeps the always-loaded memory lean
  — the same reason the root nearly blew the ~200-line budget. Three are wired in
  `.claude/skills/` (Claude Code): `openapi-client`, `liquibase-changeset`,
  `ddd-archunit`. Add your own for any workflow you'd otherwise explain twice.
- **Auto-format on write.** Wired as `.claude/hooks/format.py` (PostToolUse):
  Prettier for `frontend/**`, google-java-format for `backend/**` Java, both only
  if installed. Best-effort and non-blocking; Spotless/Prettier in `verify` stay
  the source of truth. Remove the PostToolUse entry to disable it.
- **Demand evidence, not assertions.** "It works" is not a result. The evaluator
  already verifies; have it *show* the command it ran and the test summary (a
  screenshot for UI) so a human can trust a verdict without re-running it.
- **Context hygiene.** `/clear` between unrelated tasks, and compact *before*
  ~50% rather than letting it auto-compact (the model is weakest mid-compaction).
  After two failed corrections, start fresh from `PROGRESS.md` instead of pushing
  a polluted context further.
- **Bounded parallelism via git worktrees.** Independent work can run as parallel
  agents in separate worktrees — but the cap is *your* review capacity, ~2-3 in
  practice, not the tool's.
- **Maintain the harness like code.** On a recurring failure, reach for a hook or
  a golden task in `evals/` before adding another `AGENTS.md` rule, and delete
  anything the model already does right. Prompt files rot the way code does.
- **MCP servers: least privilege.** If you wire external tools via MCP, treat
  them like the permission allowlist — connect only what a task needs, scope the
  tokens, and remember an MCP server is one more source of untrusted content.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/agents` doesn't list the sub-agents | You edited files on disk — restart the Claude Code session. Agents created via `/agents` apply immediately. |
| The agent ignores `AGENTS.md` / `CLAUDE.md` | It must be in the directory you launched from (or a parent). Check with `/memory` (Claude Code) or `/memory show` (Gemini CLI). |
| Codex/Vibe ignore my `CODEX.md` / `MISTRAL.md` | Neither filename is read by anything. Both tools read `AGENTS.md`. |
| Gemini loads `GEMINI.md` but not the rest | Run `/memory refresh`. Imports resolve at load time, max depth 5. |
| Claude Code sandbox won't start on Linux/WSL2 | Install `bubblewrap` + `socat` (`/sandbox` → *Dependencies* shows what's missing); on Ubuntu 24.04+ allow `bwrap` user namespaces. WSL1 and native Windows are unsupported — see *Prerequisites: Windows + WSL*. |
| Gemini CLI runs but the status bar shows "no sandbox" under WSL2 | `sandbox-exec` is macOS-only, so WSL2 needs a container: start a Docker/Podman engine in the distro and set `GEMINI_SANDBOX=docker`. With native Docker (no Docker Desktop) enable `systemd` and join the `docker` group. |
| Codex: "seccomp/landlock … not supported in this environment" | You're on WSL1 (or an old kernel) — Codex detects it as Linux but the primitives aren't there. Move to WSL2. |
| Heredocs (`<< EOF`) fail | A known sandbox limitation: the shell needs a temp file. Write the file, then run it. |
| The guard blocks something legitimate | Move it out of `ACCIDENT_PATTERNS` and add a `Bash(...)` **ask** rule in `.claude/settings.json`. Don't disable the sandbox. |
| Context feels bloated | `AGENTS.md` is 160 lines; Claude Code sees ~199 — just under Anthropic's ~200 guideline. Stack detail lives in the nested `backend/` / `frontend/` `AGENTS.md` (loaded only in-tree), and repeated workflows belong in skills or `.claude/rules/*.md` (see *Recommendations*), not here. `@path` imports do **not** reduce context — they load at launch. |

## Known gaps

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
