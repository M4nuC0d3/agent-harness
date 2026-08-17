# Enforcement across Claude Code and Codex

Behaviour is shared; enforcement is not. Both tools read the **same**
`AGENTS.md` and the same role prompts, so the coordinator/researcher/implementer/
evaluator loop is identical. The **enforcement layer** — the OS sandbox, the
permission policy, and the hooks — is drawn with each tool's own mechanism.
`.claude/settings.json` and `.claude/hooks/*` are Claude Code's format; Codex
does not read them. This file wires the same guarantees into both and resolves
the two residual risks the README flags under *Verify before trusting*.

Any other agent that reads `AGENTS.md` gets the instructions and the roles — the
format is an open standard — but none of the enforcement below. There the
boundary is yours to provide: an OS-level sandbox (a container, or WSL2) plus
whatever permission model that tool has. Nothing in this repo configures it, and
nothing here has been tested against it.

## The one thing that ports for free: the hook scripts

`.claude/hooks/preflight.py`, `guard.py` and `trace.py` are **one copy each**,
shared across tools. That works because the three CLIs converged on the same
contract for the pre-tool gate: a JSON event on stdin, and **exit 2 + stderr =
block**. `guard.py` reads the command from either shape (`tool_input.command`
for both tools, or a top-level `command` for anything that sends that shape), and exit 2 is the one
blocking signal all three honor — so there is nothing to fork. The scripts are
registered per tool; the logic lives once.

## Codex → `.codex/`

Two files, both shipped:

- **`.codex/config.toml`** — `sandbox_mode = "workspace-write"` (OS boundary) and
  `approval_policy = "on-request"` (pause before crossing it): the analog of the
  `settings.json` sandbox + ask layer. Egress is on via `[sandbox_workspace_write]`;
  a commented `[permissions.harness]` block gives a domain allowlist mirroring
  `.claude/settings.json` if your Codex build accepts the (beta) permissions model.
- **`.codex/hooks.json`** — registers all four shared scripts: `preflight.py`
  on `SessionStart`, `guard.py` on `PreToolUse`, and `trace.py` plus `format.py`
  on `PostToolUse` (matchers `Bash` and `apply_patch|Edit|Write`). Codex's
  `PreToolUse` stdin and exit-2 block match Claude Code, so the scripts run
  unchanged. This is also the file the Codex *plugin* manifest points at — see
  *One hooks file, two install routes* below.

Two things to know:

- **Trust.** Codex loads project-local `.codex/` config, hooks and rules **only
  when the project is trusted** (it prompts on first run). For unattended CI, use
  `codex --run-hooks-without-trust`.
- **Write hooks, and the shape they arrive in.** Codex once fired
  `PreToolUse`/`PostToolUse` for Bash only, which is why this file used to say
  `format.py` could not run there. It fires for `apply_patch` now, and the
  matcher accepts `apply_patch`, `Edit` or `Write`. The payload is *not* Claude
  Code's, though: `tool_name` is reported as `apply_patch` whatever the matcher
  said, and there is no `file_path` — the patch envelope arrives in
  `tool_input.command` and can name several files. `format.py` parses both
  shapes, the same way `guard.py` reads the command from either. Build-time
  formatters remain the source of truth either way.
- **Guard still watches Bash only.** Now that writes are hookable, `guard.py`
  *could* gate `apply_patch` too. It does not: its rules are written against
  shell commands, and a patch envelope is a different grammar that would need
  its own rules and its own tests. Deliberate gap, not an oversight.
- **A guardrail, not a boundary.** The model can write and execute a script to
  sidestep a command matcher, and Codex's own docs call tool hooks a useful
  guardrail rather than a complete enforcement boundary. The sandbox is the
  boundary.

### Shipping it as a Codex plugin

`.codex/` is the *copy* route. The *install* route is a plugin, and it needs its
own hook registration — not because the hooks differ, but because the paths do.

- **`.codex-plugin/plugin.json`** — the manifest. `skills` takes a single
  directory path (Claude's takes an array); there is no `agents` field, so the
  roles in `.codex/agents/*.toml` do not ship with the plugin and stay a copy.
- **`.agents/plugins/marketplace.json`** — the repo marketplace
  `codex plugin marketplace add M4nuC0d3/agent-harness` reads. Codex also reads
  `.claude-plugin/marketplace.json` as a legacy-compatible source, so both are
  discoverable; only the Codex one carries `policy` and `category`.
### One hooks file, two install routes

There used to be two: `.codex/hooks.json` anchored on
`$(git rev-parse --show-toplevel)`, correct for a checkout and wrong for an
install (plugins live in `~/.codex/plugins/cache/…`, which is not a git
repository), and `.codex-plugin/hooks.json` anchored on `${PLUGIN_ROOT}`, which
is unset in a project that copied `.codex/` in. Neither anchor works in both
places, so the file was duplicated — and two files meant two chances to forget
one. That is exactly what happened: when write hooks became available, the
formatter got registered in neither.

One file covers both, because Codex expands the command string:

```
${PLUGIN_ROOT:-$(git rev-parse --show-toplevel)}/.claude/hooks/format.py
```

`${PLUGIN_ROOT}` when Codex loads this from an install, the git root otherwise.
`.codex-plugin/plugin.json` points at it with `"hooks": "./.codex/hooks.json"`;
manifest hook paths are resolved against the plugin root and must stay inside it,
which `.codex/` does. Codex also sets `CLAUDE_PLUGIN_ROOT` for compatibility, so
either variable name would do — `PLUGIN_ROOT` is the native one.

It deliberately does **not** live at the repo-root `hooks/hooks.json` default
path — that path is Claude Code's own default plugin-hook location, and this repo
is *also* a Claude Code plugin from the same root (`.claude-plugin/marketplace.json`
sets `"source": "./"`). Claude Code merges a plugin's `hooks/hooks.json` with
`plugin.json`'s inline `hooks` block rather than one replacing the other, so a
Codex-only file at that path would load a second time under Claude Code, where
`${PLUGIN_ROOT}` is never set: it resolves to an empty string and every hook runs
against `/.claude/hooks/*.py` instead of the plugin's real install directory. That
was a real bug here, not a hypothetical. `test_docs.py` asserts the path stays
empty, that only one Codex hooks file exists, that every command carries the
fallback anchor, and that Codex and Claude Code register the *same* set of
scripts — the drift that hid the missing formatter is now a failing check.

One caveat the merge does not remove: Codex loads matching hooks from **all**
sources. A project that both copies `.codex/` in and installs the plugin
registers each hook twice, and both copies run.

- **`guard.py`'s chaining check no-ops here.** It reads `excludedCommands` from
  the project's `.claude/settings.json`; a Codex-only project has none, so the
  prefix list is empty and the check skips (fail-open, as its header documents).
  Nothing is lost — the hole it closes is specific to Claude Code's
  `excludedCommands`, which Codex has no equivalent of. The budget, the accident
  catcher and the trace are unaffected.

Optional extra: `codex execpolicy` `.rules` (Starlark) give per-command
allow/prompt/block, the closest match to `settings.json`'s `deny`/`ask` command
lists. Test rules with `codex execpolicy check --rules <file> -- <command>`.
`requirements.toml` (managed) can forbid `sandbox_mode = "danger-full-access"` or
`approval_policy = "never"` org-wide — the `managed-settings.json` analog.

## Resolving the two residual risks

### 1) Sandbox fail-open → fail-closed preflight

A sandbox that cannot start can fail **open**: on WSL1 or native Windows there is
no Linux sandbox at all, and on Linux/WSL2 the boundary needs `bwrap` + `socat`.
`.claude/hooks/preflight.py` runs at session start (Claude Code `SessionStart`,
Codex `SessionStart`) and **stops the session** when the
boundary would be absent — so "no sandbox" is loud, not silent. It is
conservative: it blocks the clear-cut cases (WSL1; missing `bwrap`/`socat` on
Linux/WSL2), warns on macOS (Seatbelt) and native Windows (Codex has a native
sandbox we can't rule out from a hook), and **fails safe on its own bugs** (a
broken preflight warns and continues rather than bricking every session). Set
`HARNESS_SKIP_PREFLIGHT=1` when the environment is already isolated externally (a
container, a cloud runner). This complements the existing
`allowUnsandboxedCommands: false`, which stops a *single* command from retrying
outside the sandbox; preflight covers the *whole session* when the sandbox isn't
there at all.

### 2) Network filter doesn't inspect TLS (domain fronting)

The sandbox network filter allowlists by domain/SNI; it cannot see inside the TLS
session, so a permitted SNI can front a request to a different backend. **A domain
allowlist cannot fix this** — it's structural. Options, strongest last:

- **Trim the allowlist.** Every allowed domain is a potential front. This repo's
  list is polyglot (npm, Maven, PyPI, crates, GitHub); a Java + Node project only
  needs Maven Central + the npm registry + GitHub. Drop what your stack doesn't
  use.
- **Put a real egress proxy in front.** A proxy that enforces `SNI == Host` (or
  terminates and inspects TLS) blocks fronting in a way an allowlist can't. Codex
  can route through one via `features.network_proxy`.
- **Run the agent phase offline.** The strongest option for unattended work: fetch
  dependencies in a separate, trusted setup step, then run the agent with **no**
  network (the model Codex cloud uses — network during setup, offline during the
  agent phase). No egress means no fronting.

## Verify

The enforcement is only real if it holds on your machine. Run the golden tasks in
`evals/golden-tasks.md` (G3 injection, G4 enforcement) under each tool you use,
and the deterministic checks without a model in the loop:

```
python .claude/hooks/test_guard.py  .claude/hooks/guard.py    # both stdin payload shapes
python .claude/hooks/test_policy.py .claude/settings.json
```
