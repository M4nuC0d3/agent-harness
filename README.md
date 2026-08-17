# Agent Harness — a coordinator + three roles, for any coding agent

A small, model-agnostic instruction layer. It turns whichever coding agent you
use into a **coordinator** that plans, delegates to three focused roles, and
refuses to accept work the **evaluator** hasn't passed. Underneath it, a real
enforcement layer stops the accidents that instructions alone cannot.

No runtime, no orchestrator, no API keys, no build step. Just files your agent
already knows how to read.

**This repo is a worked example, not a skeleton.** The harness is generic; the
project it is pointed at is a demo — a Quarkus/Angular monorepo — and lives
entirely under **`example/`**, plus one marked block in `AGENTS.md`. Everything
else is stack-agnostic. Adopting it for your own project means replacing that
block, deleting `example/`, and repointing one JSON file: **`docs/adopt.md`**.

## Where project information lives

Four places, and deliberately no fifth:

| What | Where | Read by |
|---|---|---|
| Facts that hold repo-wide | the `HARNESS:PROJECT` block in `AGENTS.md` | Claude Code + Codex |
| Build, tests, conventions per package | `<pkg>/AGENTS.md` | both — with a caveat |
| A workflow you'd explain twice | a skill | Claude Code, Codex (plugin) |
| Which formatter runs where | `.claude/format.map.json` **in your project** | `format.py` |

Read by Claude Code and Codex, in that column, means *verified* there. Other
tools read the same `AGENTS.md` and get the same facts; the caveats below are
written for the two primary ones because those are the ones held to them.

The block is **inline on purpose**. The tidy-looking alternative —
`@docs/project.md` — silently breaks Codex: Claude Code resolves `@path`
imports, Codex has no import directive at all (openai/codex#17401), so half the
instruction layer would go missing in one tool and nothing would say so.
`test_docs.py` fails the build on an `@import` inside `AGENTS.md`.

### How the two levels compose

The root block is **inherited**: it applies in every package, and a nested
`AGENTS.md` adds to it rather than replacing it. Where both speak to the same
point the **closest file wins**, so a nested file *narrows* a root rule and never
restates it — restating is how the two drift apart with nobody editing either.

One asymmetry decides the borderline cases. Claude Code loads a nested file when
it touches that subtree; Codex builds its chain from the repo root down to the
*working directory* and may never reach a package file in a root-launched session
(openai/codex#13288). Inheritance downward is reliable, discovery upward is not —
so a rule an agent must never miss belongs in the root block even when it feels
package-specific.

`docs/adopt.md` has the line-by-line test for what goes where.

## Works with

**Claude Code and Codex.** Both read the same `AGENTS.md`, get the same three
roles as native sub-agents, and run the same three hook scripts — so behaviour
and enforcement are identical across them, and CI keeps them in step.

| Tool | Reads | Sub-agents | Enforcement |
|---|---|---|---|
| **Claude Code** | `CLAUDE.md` → imports `AGENTS.md` | `.claude/agents/*.md` | `.claude/settings.json` + hooks |
| **Codex** | `AGENTS.md` | `.codex/agents/*.toml` | `.codex/config.toml` + hooks |

`AGENTS.md` is an open format stewarded by the Agentic AI Foundation and read by
20+ agents, so any other tool that reads it gets the instructions, the loop and
the roles for free. It gets **none of the enforcement**: the sandbox, the
permission rules and the hooks below are wired for these two only. Elsewhere the
boundary is yours to provide — an OS-level sandbox plus that tool's own
permission model. Nothing here configures it and nothing here is tested against
it.

## Install

[#install](#install)

Installing is always two parts, whichever route you take. A plugin can carry
**executable components** — sub-agents, skills, hooks. It cannot carry
**instruction files** or **settings**: a `CLAUDE.md` at a plugin root is not
loaded as project context, and sandbox and permission rules are project
settings. So three files always live in your repo:

| | Comes from | Why it can't be the other way |
|---|---|---|
| the three roles, as sub-agents | plugin | — |
| `preflight.py`, `guard.py`, `trace.py` | plugin | — |
| skills | plugin | — |
| `AGENTS.md` + `CLAUDE.md` | **your repo** | must be always-loaded, and one block in it is yours to edit |
| `.claude/settings.json` | **your repo** | the sandbox and permission rules are project settings |
| `.codex/config.toml` (Codex only) | **your repo** | same, in Codex's vocabulary |

The plugin is an *install* — versioned, cached, refreshed on a version bump. The
repo files are *inherited* — merged along the directory hierarchy at load time.
Different mechanisms with different failure modes: a missing repo file is
obvious immediately, a stale plugin version is not.

### Route 1: plugin + three files (recommended)

The roles, skills and hooks are versioned and update in place:

```
/plugin marketplace add M4nuC0d3/agent-harness
/plugin install agent-harness@m4nuc0d3-harness
```

Then add the three files the plugin cannot carry:

```
# from a checkout of this repo
cp AGENTS.md CLAUDE.md /path/to/your-project/
cp settings.consumer.example.json /path/to/your-project/.claude/settings.json
cp .codex/config.toml /path/to/your-project/.codex/       # Codex only
```

Then **replace the `HARNESS:PROJECT` block** in the copied `AGENTS.md` — that is
the one edit that makes the harness yours, and `docs/adopt.md` walks it through.
Everything outside the two markers stays as copied.

`settings.consumer.example.json` also registers the marketplace, so anyone who
trusts the project folder is prompted to install the plugin.

> **Copy the consumer example, not this repo's `.claude/settings.json`.** They
> are deliberately different. This repo *develops* the hooks, so its file wires
> them from the working tree and does not install the plugin. A consumer gets
> the hooks *from* the plugin, so its file has no `hooks` block at all. Copying
> the wrong one gives you either every hook firing twice — halving the tool-call
> budget and doubling every trace line — or a `hooks` block pointing at
> `.claude/hooks/*.py` files your project doesn't have, which no-op silently.
> And an absent `PreToolUse` hook blocks nothing. `test_docs.py` asserts the
> split, and that the `sandbox` and `permissions` blocks stay byte-identical
> between the two.

**On the Codex side**, the same skills and hook scripts install with:

```
codex plugin marketplace add M4nuC0d3/agent-harness
```

Then open the Plugins directory, pick **M4nuC0d3 Harness** and install *Agent
Harness*. Copy the whole of **`.codex/`**: its manifest has no `agents` field, so
unlike Claude Code the three roles do *not* travel with the install, and
`config.toml` carries the boundary.

> **Installing is not trusting.** Codex skips plugin-bundled hooks until you
> review and trust the hook definition. Until you do, the session budget, the
> accident catcher and the audit trace are all absent — and an absent
> `PreToolUse` hook blocks nothing. Same failure mode as a missing `python3`,
> different cause. The sandbox and `approval_policy` from `.codex/config.toml`
> are unaffected; they never depended on the hooks.

Codex also reads `.claude-plugin/marketplace.json` as a legacy-compatible
catalog, so this repo can appear **twice** in the directory. The two catalogs
carry deliberately different names (`m4nuc0d3-harness-codex` for Codex): the
install cache is keyed by marketplace name, so equal names would put two sets of
metadata in one directory. `test_docs.py` asserts they stay different.

> **Developing on this repo? Then don't also have the plugin installed.** The
> working tree registers the hooks through `.codex/hooks.json`, and the plugin
> registers the same file again from its own install root. Codex loads matching
> hooks from every source, so each one runs twice — half the tool-call budget,
> doubled trace lines, files formatted twice, silently. The
> Claude-side version of this trap is assertable, because `enabledPlugins` lives
> in `.claude/settings.json`, in the repo. This one is not: Codex keeps the
> enabled state in `~/.codex/config.toml`, user-level, where no test in this
> repo can see it. `/plugins` shows you what is installed.

One behavioural difference: `guard.py`'s chaining check reads its prefixes from
the project's `.claude/settings.json`, which a Codex-only project doesn't have —
so it reads none and skips itself, by design. It closes a hole specific to Claude
Code's `excludedCommands`, which Codex has no equivalent of. Budget, accident
catcher and trace still run.

Bump `version` in **both** `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json` on every release; without a bump, installed copies
keep the cached version and never see your changes. `test_docs.py` asserts the
two numbers stay equal — one release, one number.

### Route 2: copy everything (no plugin support, or you want to fork it)

Same three files, plus the components the plugin would otherwise have carried:

```
cp -r AGENTS.md CLAUDE.md .claude/ .codex/ docs/ evals/ templates/ \
      /path/to/your-project/
cp settings.consumer.example.json /path/to/your-project/.claude/settings.json
```

Then replace the `HARNESS:PROJECT` block, and verify the boundary landed:

```
python3 --version                                          # the only extra dep
python3 .claude/hooks/test_policy.py .claude/settings.json
```

**`example/` is never copied**, in either route. It is the demo project, not
part of the harness — nothing in `.claude/`, `.codex/` or the hooks refers to it
at all. What you copy and fill in is `templates/`;
`example/` is what you read next to it. `docs/adopt.md` pairs each blank with its
worked counterpart.

Copies drift and have no update path — that is the trade-off, and it is why the
plugin route exists.

`.codex/` wires the same enforcement into Codex; drop it if you only use Claude
Code. `.codex/agents/*.toml` additionally gives Codex the same three roles as
native sub-agents (`[agents]` in `.codex/config.toml` turns this on). Then start
`claude` or `codex` there and give it a real goal:

> Add pagination to the `/users` endpoint, with tests.

It plans first, delegates `researcher` → `implementer` → `evaluator`, and pauses
for your approval before anything irreversible.

**Requirements.** Each CLI installs itself. The only *extra* dependency is
**Python 3**: the hooks run as `python3 .claude/hooks/{preflight,guard,trace}.py`.
They're stdlib-only and shared between both tools (one copy each — see
`docs/porting-enforcement.md`), so any Python 3 works — but if `python3` isn't on
`PATH` they don't fail loudly, they silently no-op, and an absent `PreToolUse`
hook blocks nothing (see *Verify before trusting*). That quietly drops the
session budget, the accident catcher **and** the audit trace — the whole hook
layer — while the sandbox and permission rules stay up. Run `python3 --version`
before you rely on enforcement.

**Checking the install.** At session start `preflight.py` prints one line naming
what is actually armed — the shell-call budget, the accident catcher, how many
excluded prefixes the chaining check loaded, and where the trace goes. If you do
not see that line, the hook layer did not run at all. That is the whole point of
printing it: silence must never be evidence of a boundary.

## Prerequisites: your project's toolchain

The harness itself needs Python 3 and nothing else. Whatever your build needs is
your project's business — with one rule worth carrying over: **name commands the
sandbox actually permits.** A wrapper that writes outside the working directory
(`./mvnw` is the demo's example) fails on first invocation as a *sandbox* error
rather than a build error, which reads like a tooling bug and costs an hour.
`test_docs.py` enforces that no skill or role prompt hands `./mvnw` to an agent.

The demo project's own toolchain notes are in `example/README.md`.

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

Both tools read the *same* `AGENTS.md` and the *same* role prompts, so their
**behaviour is identical**. Their **enforcement is not**: each draws the boundary
with a different OS mechanism, so what you install under WSL2 differs.

| Agent | Boundary under WSL2 | Install / enable |
|---|---|---|
| **Claude Code** | `bubblewrap` + `socat`, in the distro — no container | `sudo apt-get install bubblewrap socat`. Ubuntu 24.04+: also allow `bwrap` user namespaces (AppArmor). `/sandbox` → *Dependencies* lists anything missing. |
| **Codex** | Landlock + seccomp, in the distro — no container | Node 22+; nothing extra for the sandbox. WSL1 is seen as "linux" but fails the seccomp/Landlock probe — you must be on WSL2. Enforcement is wired in **`.codex/`** (config + hooks; trusted projects only). |

So the answer to the obvious follow-up — *is the behaviour identical?* — is: yes
for the instructions, no for enforcement. Both isolate at the host level inside
the distro, but through different primitives, configured in different files.
`docs/porting-enforcement.md` has the per-tool wiring and the two residual risks.

## No generator, no drift

Every piece of content exists **exactly once**, in the format the tool actually
reads. There is nothing to regenerate and nothing to keep in sync:

```
AGENTS.md                 the canonical instructions — the only copy. Generic,
                          except the HARNESS:PROJECT block: your project facts
CLAUDE.md                 3 lines + Claude specifics; imports AGENTS.md
.claude/agents/*.md       the three role prompts for Claude Code
                          (YAML frontmatter for Claude Code; other tools read past it)
.claude/settings.json     sandbox + permissions + hooks — for THIS repo (dev)
settings.consumer.example.json  what a consuming project copies: same boundary,
                          no hooks (the plugin brings them), plus the plugin
                          registration. Kept in sync by test_docs.py.
.claude/hooks/preflight.py sandbox gate: present AND working, fail-closed (shared)
.claude/hooks/guard.py    session budget + opt-in accident catcher (shared; config at the top)
.claude/hooks/trace.py    audit trail (shared across tools)
.claude/hooks/format.py   auto-format on write (PostToolUse; best-effort). Reads
                          .claude/format.map.json from the PROJECT dir, which
                          this repo does not ship — no map, no formatting.
                          Prefixes are anchored there, so a rule cannot reach
                          outside the project
.claude/hooks/test_*.py   the six suites below, run in CI
.claude/skills/*/SKILL.md on-demand workflows, loaded on description match.
                          Packaged for every consumer, so stack-agnostic only —
                          currently just harness-adoption
.claude-plugin/plugin.json      makes this installable + updatable as a plugin
                          (`agents` takes FILE paths, `skills` takes directories)
.claude-plugin/marketplace.json the catalog `/plugin marketplace add` reads
.codex-plugin/plugin.json the same, for Codex (`skills` takes ONE directory path;
                          there is no `agents` field, so the roles stay a copy)
.agents/plugins/marketplace.json the catalog `codex plugin marketplace add` reads
.github/workflows/harness.yml   runs all six suites on every push and PR
.codex/config.toml        Codex sandbox + approval policy + [agents] switch
.codex/agents/*.toml      the three roles as native Codex sub-agents (own copy;
                          same responsibilities as .claude/agents/*.md)
.codex/hooks.json         Codex hook registration → all four shared .claude/hooks/
                          scripts, for BOTH install routes: commands anchor on
                          ${PLUGIN_ROOT:-$(git rev-parse --show-toplevel)}, so
                          the same file resolves from the plugin install cache
                          (not a git checkout) and from a project that copied
                          .codex/ in. .codex-plugin/plugin.json points at it.
                          Deliberately NOT at the repo-root hooks/hooks.json —
                          that is Claude Code's own default plugin-hook path,
                          which it merges with plugin.json's inline hooks, so a
                          Codex file there would load twice under Claude Code
                          with ${PLUGIN_ROOT} unset
docs/adopt.md             replacing the demo with a real project, in order
docs/porting-enforcement.md  how the same enforcement is wired for Codex
docs/graph-pipeline.md    full decision-matrix criteria + graph topology (AGENTS.md keeps only the summary)
managed-settings.example.json   org-wide lockdown TEMPLATE — deploy outside the repo; never read from it
evals/golden-tasks.md     does this setup actually work?
.agent/                   runtime: PROGRESS.md (committed), trace.jsonl (ignored)
templates/                skeletons: the PROJECT block, a package AGENTS.md
example/                  THE DEMO PROJECT — not part of the harness. api/,
                          backend/, frontend/ and the four stack skills. Delete
                          it; only the PROJECT block refers to it. Also holds
                          .claude/format.map.json as reference — a copy nothing
                          reads. See example/README.md
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

**A lockdown switches off the thing it is protecting, unless you let the plugin
through.** `allowManagedHooksOnly` blocks user hooks, project hooks and plugin
hooks alike — with one exception: hooks from plugins **force-enabled in managed
`enabledPlugins`**, matched by the full `plugin@marketplace` id. Deploy the
template without that entry and `guard.py`, `preflight.py` and `trace.py` simply
stop running. Nothing announces it: preflight *is* a hook, so the `Armed: …`
session line it normally prints just disappears, and an absent message is not a
warning. `allowManagedPermissionRulesOnly` does the same to the deny/ask list —
project rules go inert, so the baseline has to be repeated in the managed file
or it exists nowhere.

`managed-settings.example.json` therefore carries all three: the force-enable,
the full deny/ask baseline, and `sandbox.enabled` + `allowUnsandboxedCommands:
false`. `test_docs.py` fails the build if a flag is set without its replacement.

This also answers *is the plugin worth shipping, if it cannot carry the
boundary?* Under a lockdown it is the **only** delivery form that survives: a
copied `.claude/hooks/` is a project hook and gets blocked, while the plugin's
hooks run because the admin vetted them by id. Route 2 is the one a lockdown
breaks, not Route 1.

An earlier version of this repo generated `CLAUDE.md` and the role files from a
shared source. That solved duplication by adding a build step, and a build step
for four markdown files is worse than the problem. The import covers Claude Code;
the role prompts live where each tool wants them — `.claude/agents/*.md`,
`.codex/agents/*.toml` — each a standalone copy carrying the same
responsibilities, not a generated one.

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
secrets, `curl`, `wget` and `sudo`, pre-approve a small `WebFetch` allowlist and
prompt for every other domain (see *Known issue: WebFetch*), and prompt on
`git push`, `rm -rf`, `terraform`, `kubectl`.

**Bash patterns are not a security control.** Arguments can be reordered,
variables expanded, wrappers used. That is why the guard's denylist is labelled
an *accident catcher* (`ACCIDENT_CATCHER = False` disables it) and why `curl` is
denied outright rather than pattern-matched.

The hook exists for the three things rules cannot do: count tool calls per
session, write an audit trace, and refuse a sandbox-excluded command that
carries other commands with it (*Known issue: `excludedCommands`*). That last
one is enforceable — unlike the accident catcher — precisely because it matches
on *shape* (is anything chained?) rather than on intent (is this dangerous?).

Test all three without a model in the loop:

```bash
python3 .claude/hooks/test_guard.py  .claude/hooks/guard.py   # 40 behavioural cases
python3 .claude/hooks/test_policy.py .claude/settings.json    # sandbox + rules present
python3 .claude/hooks/test_docs.py   .                        # instruction-layer consistency
python3 .claude/hooks/test_preflight.py .claude/hooks/preflight.py  # fake bwrap on PATH
python3 .claude/hooks/test_trace.py  .claude/hooks/trace.py   # trace format is stable
python3 .claude/hooks/test_format.py .claude/hooks/format.py  # fake formatter on PATH
```

All six run in CI on every push and PR (`.github/workflows/harness.yml`).
`test_docs.py` is the least obvious: it checks what rots silently — the
always-loaded context staying under ~200 lines, the README's own line count
matching reality, skills naming only commands the sandbox permits, every skill
having loadable frontmatter, Claude Code and Codex defining the same roles, and
the plugin manifest pointing at paths that exist. Every one of those checks is
a bug that shipped here.

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

Codex's `.codex/agents/*.toml` mirrors this with its own `model` /
`model_reasoning_effort` fields per role, with a fallback in
`.codex/config.toml`'s `[agents]` block
(`default_subagent_model`, `default_subagent_reasoning_effort`).

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

The **closest** `AGENTS.md` wins, and the root is inherited into every package —
see *How the two levels compose* for what belongs at which level and for the
Codex discovery caveat. Keep this root file to what applies everywhere and put
package-specific build commands, framework conventions and local anti-patterns in
a nested `AGENTS.md`. Nested files keep the root small, which is what keeps it
read.

## Recommendations

Beyond what's already wired, these are the agentic-coding habits current practice
converges on. Optional and opinionated — adopt what fits.

- **Ship it as a plugin, not a copy.** Copies have no update path; a plugin's
`version` field is the update signal, so bump it on every release — in both
manifests. What the plugin does and does not carry is the table under *Install*;
Codex adds one more gap, the sub-agent definitions, which its manifest has no
field for.
- **Push repeated workflows into skills, not this file.** On-demand context
  (loaded only when its description matches) keeps the always-loaded memory lean
  — the same reason the root nearly blew the ~200-line budget. `.claude/skills/`
  ships one, `harness-adoption` (where project information goes, and why it is
  never an `@import`); it is packaged for every consumer, so only stack-agnostic
  skills belong there. The demo's four — `openapi-client`, `liquibase-changeset`,
  `ddd-archunit`, `quarkus-testing` — sit under `example/skills/` as reference.
  Add your own for any workflow you'd otherwise explain twice.
- **Auto-format on write.** Wired as `.claude/hooks/format.py` (PostToolUse).
  The hook is stack-agnostic and ships with *no* map: it reads
  `$CLAUDE_PROJECT_DIR/.claude/format.map.json` — a file you write, in your
  project, holding path prefix + extensions + command. No map, no formatting,
  the same silent no-op as a formatter that isn't installed. Resolving against
  the project rather than `__file__` is the point: a map next to the hook is the
  map of whoever *shipped* the plugin, so every consumer would inherit the
  demo's `example/frontend/` and `example/backend/` rules and be unable to edit
  them. `example/.claude/format.map.json` is that demo map, kept as reference
  only — nothing reads it. Best-effort and non-blocking; the formatters in your
  build stay the source of truth. Remove the PostToolUse entry to drop the hook
  entirely.
- **Demand evidence, not assertions.** "It works" is not a result. The evaluator
  already verifies; have it *show* the command it ran and the test summary (a
  screenshot for UI) so a human can trust a verdict without re-running it. It
  also names the convention files it read: a skill loads only when its
  description matches, so the evaluator reads the nearest `AGENTS.md` and the
  relevant `SKILL.md` as plain files rather than assuming the implementer did.
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
| The agent ignores `AGENTS.md` / `CLAUDE.md` | It must be in the directory you launched from (or a parent). Check with `/memory` (Claude Code). |
| Codex ignores my `CODEX.md` | That filename is read by nothing. Codex reads `AGENTS.md`. |
| Claude Code sandbox won't start on Linux/WSL2 | Install `bubblewrap` + `socat` (`/sandbox` → *Dependencies* shows what's missing); on Ubuntu 24.04+ allow `bwrap` user namespaces. WSL1 and native Windows are unsupported — see *Prerequisites: Windows + WSL*. |
| Codex: "seccomp/landlock … not supported in this environment" | You're on WSL1 (or an old kernel) — Codex detects it as Linux but the primitives aren't there. Move to WSL2. |
| Heredocs (`<< EOF`) fail | A known sandbox limitation: the shell needs a temp file. Write the file, then run it. |
| The guard blocks something legitimate | Move it out of `ACCIDENT_PATTERNS` and add a `Bash(...)` **ask** rule in `.claude/settings.json`. Don't disable the sandbox. |
| Every Bash command fails with `apply-seccomp: write /proc/self/uid_map: Operation not permitted` | `bwrap` itself can't start — see *Known issue: bwrap can't create its user namespace* below. Only commands listed in `sandbox.excludedCommands` in `.claude/settings.json` (currently `docker *`, `mvn *`, `npm *`, `find *`, `ls *`, `grep *`), which skip the sandbox wrapper entirely, still run; everything else — including `echo` and `git` — is blocked at the boundary, not by a permission rule. **Don't "fix" this by adding more entries to `excludedCommands`** — see *Known issue: `excludedCommands` matches the whole shell line* below before touching that list. |
| Context feels bloated | `AGENTS.md` is 162 lines; with `CLAUDE.md` Claude Code sees 199 — just under Anthropic's ~200 guideline. Re-measure with `cat CLAUDE.md AGENTS.md \| wc -l` after editing either; the number above goes stale silently. Stack detail lives in the nested per-package `AGENTS.md` (loaded only in-tree — and see *Where project information lives* for what Codex does with those), and repeated workflows belong in `.claude/skills/` (see *Recommendations*), not here. `@path` imports do **not** reduce context — they load at launch. |

## Known gaps

- **Enforcement is wired for two tools, by design.** `.claude/` and `.codex/`
  register the *same* `preflight.py` / `guard.py` / `trace.py`, sharing one
  stdin+exit-2 contract — one copy each, not a fork. Any other `AGENTS.md`
  reader gets the instructions and none of this; the boundary there is an
  OS-level sandbox you provide plus that tool's own permission model. Details
  and caveats (Codex trust, the two residual risks): `docs/porting-enforcement.md`.
- **A session-start check, not a running one.** `preflight.py` verifies that a
  sandbox is available *and* configured before the first tool call. It cannot
  see a settings change made mid-session, and it runs outside the wrapper the
  Bash tool itself uses — see *Verify before trusting*.

## Verify before trusting

Hook schemas, frontmatter fields and import syntax move fast — published sources
already disagree on whether Claude Code exposes 27 or 30 hook lifecycle events.
Exit-code semantics have a real footgun: exit 1 blocks nothing, exit 2 blocks,
and mixing exit 2 with JSON on stdout silently discards the JSON.

The hooks here were tested against simulated stdin payloads, not a live CLI. The
sandbox settings were written against Anthropic's own example config but never
executed. Two caveats used to sit here bare; both now have a resolution in
`docs/porting-enforcement.md`:

- **Sandbox fail-open.** If the sandbox can't start (WSL1, native Windows, a
  missing `bwrap`/`socat`, or a `bwrap` that is installed but cannot create its
  user namespace) it can silently fail open. That last case is the one a
  `which` check misses and the one this repo actually hit, so preflight *runs*
  `bwrap --unshare-all --ro-bind / / --dev /dev true` rather than only looking
  for the binary. The `--unshare-all` matters: an earlier version of this probe
  omitted it, passed on a machine where every real Bash call died at
  `/proc/self/uid_map`, and so reproduced the fail-open one step later. On
  failure the probe retries the plain form to classify the cause — plain-works
  means the namespaces are refused (a nested sandbox), plain-fails-too means
  bwrap cannot create a user namespace at all. A definitive non-zero exit
  blocks; an indeterminate result (timeout) warns — refuse only a clear-cut
  absence, the same rule that already governs macOS and native Windows. The
  success path prints a line too, so silence never has to be read as a green
  light.
  `.claude/hooks/preflight.py` runs at session start and **stops the session**
  when the boundary would be absent — fail-closed, with `HARNESS_SKIP_PREFLIGHT=1`
  to opt out when you're isolated externally. It complements
  `allowUnsandboxedCommands: false`, which already blocks a single command from
  retrying outside the sandbox.
- **TLS / domain fronting.** The network filter allowlists by SNI and can't see
  inside TLS, so an allowlist can't stop fronting. Mitigate by trimming the
  allowlist to your stack, fronting egress with a proxy that enforces `SNI ==
  Host` (Codex: `features.network_proxy`), or running the agent phase offline.

Run `evals/golden-tasks.md` on your machine before trusting this setup with
anything irreversible.

#### Known issue: sandbox network proxy blocks the allowlist it accepted

Root cause of the network-proxy restriction above, for whoever picks this up:

1. `sandbox.network.allowedDomains` is correctly parsed and displayed by the
   `/sandbox` Config tab, but the running srt proxy (`localhost:3128`) rejects
   every listed domain with `403 blocked-by-allowlist`. Reproduced on
   `repo1.maven.org`, `pypi.org`, `github.com`. Persists across a full session
   restart (fresh proxy auth token each time — rules out staleness).
2. `sandbox.excludedCommands` does not exempt commands from network namespace
   isolation on Linux/WSL2. `ip addr` inside an "excluded" `npm install` shows
   only the loopback interface — the process never leaves the bubblewrap
   container. Removing the sandbox proxy env vars for such a command causes
   immediate `EAI_AGAIN`, since the private network namespace has no route out
   except the (separately broken) allowlist proxy.

Environment: Claude Code 2.1.210, WSL2 (bubblewrap + socat, Unix-domain-socket
bridge to an outer-namespace TCP proxy). Possible upstream bug:
[anthropics/claude-code#30112](https://github.com/anthropics/claude-code/issues/30112).

This has only been reproduced with Claude Code's sandbox on WSL2 — it has not
yet been verified on other platforms (native Linux, macOS/Seatbelt) or with
other AI coding tools (Codex), so treat it as scoped to that combo
until someone confirms otherwise.

Workaround: Sandbox exclude Docker, Maven and NPM
"excludedCommands": ["docker *", "mvn *", "npm *"]

(This list has since grown for an unrelated reason — see the next section and
the current `excludedCommands` value in `.claude/settings.json`.)

#### Known issue: a `WebFetch` deny-all cannot be narrowed by an allowlist

[#known-issue-webfetch](#known-issue-webfetch)

`permissions.deny` previously held `WebFetch(domain:*)` alongside three
`WebFetch(domain:…)` entries in `allow`, the intent being "deny everything except
these". That is not expressible. Rules resolve **`deny` → `ask` → `allow`, first
match wins**, and a `deny` takes no allowlist exception — so either the wildcard
matched (and the `researcher`'s `WebFetch` tool was dead, every fetch refused) or
it matched nothing (and there was no boundary at all). Both are silent, and
`test_policy.py` passed either way, because it only asserted the two strings were
present — a rule green for the wrong reason, exactly what the *Evals* section
warns about.

Resolved by dropping the deny and putting bare `WebFetch` in `ask`: unlisted
domains prompt the human, the three listed ones are pre-approved, and the hard
egress boundary stays where it always was — `sandbox.network.allowedDomains`,
which applies to Bash and its children regardless of these rules.
`test_policy.py` now asserts the absence of a `WebFetch` deny.

Not verified against a live CLI (see *Verify before trusting*): whether a bare
`ask` entry short-circuits the more specific `allow` entries is untested here.
If it does, the allowlist costs an extra prompt but denies nothing.

#### Known issue: bwrap can't create its user namespace (all sandboxed Bash fails)

Symptom: **every** Bash call — including a bare `echo` — fails immediately with:

```
apply-seccomp: write /proc/self/uid_map: Operation not permitted
```

before any command output. `mvn`, `npm`, `docker`, `find`, `ls` and `grep` still
work, because `sandbox.excludedCommands` in `.claude/settings.json` (see the
workaround above — since extended to also cover the three read-only commands)
makes them skip the `bwrap` wrapper entirely — everything else (`echo`, `git`,
`cat`, `node`, …) goes through it and dies at namespace setup, so this is a
sandbox-boundary failure, not a permission denial and not something a retry or
a different command form fixes (and `allowUnsandboxedCommands: false` means
there is no fallback path anyway).

Read-only file exploration (`find`/`ls`/`grep`) is a pragmatic, low-risk
addition to the exclusion list to keep working while the underlying `bwrap`
issue is unresolved — but it's still a widening of what bypasses the sandbox,
so don't casually add more commands here. Anything that writes or reaches the
network stays firmly inside the broken boundary until this is fixed. In
particular, **do not add `git *`** — see the next known issue for why.

#### Known issue: `excludedCommands` matches the whole shell line, not just the excluded command

While chasing the `bwrap` failure above, `"git *"` was briefly added to
`excludedCommands` (to get `git status`/`git diff` working again) and turned
out to skip the sandbox for the **entire command string**, not just the `git`
invocation. Any command chained after a match ran fully unsandboxed:

```
$ echo solo-echo-should-fail
apply-seccomp: ... Operation not permitted        # blocked, as expected

$ git rev-parse --show-toplevel >/dev/null; whoami; id -u; cat /etc/hostname
root
0
Koordinator                                        # ran completely unsandboxed
```

So `excludedCommands` entries are a prefix/pattern match on the whole line
Claude Code is about to run, not a per-command allowlist — chaining anything
after an excluded command (`;`, `&&`, `|`) carries it past the sandbox
boundary with it: no write restriction to the working directory, no network
allowlist, no `~/.ssh`/`~/.aws` deny. This is the same class of gap
*Instructions vs. enforcement* above already warns about for the `guard.py`
denylist ("Bash patterns are not a security control") — it turns out to apply
to `excludedCommands` too.

**Resolution (two parts).** First, `.claude/hooks/guard.py` now blocks any
command line that *starts with* an excluded prefix **and** contains a chain or
substitution operator (`;`, `&&`, `||`, `|`, `$(`, backtick, newline). Chaining
is the entire exploit, so refusing the chained form closes it without giving up
the exclusions that keep Maven, npm and Docker working while `bwrap` is broken.
The prefixes are read from `settings.json`, so the two cannot drift, and
`test_guard.py` covers the cases — including that a *non*-excluded command
chains freely, since both halves stay sandboxed and there is nothing to protect.

Second, `"git *"` was removed from `excludedCommands` again
(confirmed `git status` goes back to failing at the sandbox boundary rather
than silently escaping it). `find`/`ls`/`grep`/`mvn`/`npm`/`docker` stay
excluded — they're read-only or need registry/daemon access anyway, so the
chaining risk they carry is small compared to `git` (which can push, and
reach arbitrary network in one unsandboxed line). Before excluding **any**
further command, weigh what chaining something dangerous after it would let
through, not just what that command does on its own.

Not yet filed upstream or root-caused beyond the reproduction above.
Environment: Claude Code, WSL2. Treat as scoped to that combo until confirmed
elsewhere.

Likely cause: `bwrap` sets up its sandbox by writing to `/proc/self/uid_map` to
configure the new user namespace before applying its seccomp filter. That
write is rejected when unprivileged user namespaces are restricted at the
kernel/distro level — e.g. `kernel.unprivileged_userns_clone=0`, or Ubuntu
24.04+'s AppArmor restriction on unprivileged `bwrap` namespaces (already
called out in the *Troubleshooting* row above) — or when the session is itself
running inside an outer sandbox/container that doesn't grant nested
user-namespace creation (`enableWeakerNestedSandbox: false` here rules out
silently working around that).

**Measured on the affected machine** (host shell, same user the agent runs as,
WSL2, bubblewrap 0.11.1):

```
bwrap --unshare-all --ro-bind / / --dev /dev true   -> 0
/proc/sys/user/max_user_namespaces                  -> 62699
/proc/self/uid_map                                  -> 0 0 4294967295
kernel.unprivileged_userns_clone                    -> does not exist
kernel.apparmor_restrict_unprivileged_userns        -> does not exist
systemd-detect-virt                                 -> wsl
```

That rules out the causes this section originally guessed at. Neither sysctl
exists, the namespace budget is untouched, and `uid_map` shows the initial user
namespace with a full identity map — the shell is not nested. bwrap creates a
fully unshared sandbox on demand. Whatever breaks the Bash tool is therefore
**not** a kernel or distro restriction; it is something about how the CLI
invokes bwrap, or what it invokes it inside.

`preflight.py` cannot see this. It is a SessionStart hook — a direct child of
the CLI, outside the Bash sandbox path — so its probe measures the same thing
the host shell measures, and gets the same 0. An earlier version of that probe
omitted `--unshare-all`, which was a genuine bug (it would have passed even on
a kernel-restricted machine) and is fixed; but fixing it did not make preflight
able to detect *this* failure, and the success message now says so rather than
implying a certificate it cannot issue.

The practical exposure here is not a silent fail-open — the first Bash call
fails loudly. It is the pairing: every sandboxed command dies while every
`sandbox.excludedCommands` entry still runs, unsandboxed. Shrinking that list is
the mitigation; `guard.py`'s chaining check keeps the entries that must stay
from carrying anything else out with them.

Not yet root-caused against a live machine in this environment (would need
`sysctl kernel.unprivileged_userns_clone kernel.apparmor_restrict_unprivileged_userns`
and `bwrap --version`, which the same broken Bash can't run — check these from
outside the agent session). Environment: Claude Code, WSL2. Treat as scoped to
that combo until confirmed elsewhere.

Until the `bwrap` failure itself is fixed: expect Bash-dependent verification
to stay limited. `find`/`ls`/`grep` work directly and `mvn`/`npm`/`docker` cover
builds and tests, but there is no working `git`, and the guard now refuses to
let any of those carry a second command past the boundary — so
`mvn verify | tee log` has to be two calls. That is the intended trade-off: a
slightly noisier day in exchange for no silent escape.
