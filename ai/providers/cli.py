"""Subscription-path providers: drive the vendor agent CLIs as subprocesses.

Why this exists
---------------
API providers authenticate with an API key and are billed per token. The vendor
*agent CLIs* authenticate with your account login instead, so their usage draws
on your subscription (Claude plan / ChatGPT plan / Google account). Routing a
role through one of these providers therefore moves that role onto the
subscription path without changing anything else in the harness.

    config.yaml:  worker: { provider: claude_cli, model: sonnet }

Honest limitations (read before relying on this)
------------------------------------------------
* These CLIs are *agentic tools*, not completion endpoints. They carry their own
  system prompt and tool access. Our ``system`` prompt is prepended to the user
  message, ``temperature`` and ``max_tokens`` have no effect.
* Token counts are **estimates** (~4 chars/token), not billing data. The
  LLMResponse is marked ``estimated=True`` in ``raw``.
* Each model call spawns a process. Keep ``loop.max_concurrency`` low (1-2):
  subscription limits are sized for one human, not four parallel workers.
* Vendors recommend API keys for programmatic/CI use, and the subscription
  treatment of headless CLI usage has been subject to change. Verify the flags
  below against ``<binary> --help`` before you depend on them.

Everything is overridable by env var, so a flag change never requires a code
change:

    AI_CLAUDE_BIN / AI_CODEX_BIN / AI_GEMINI_BIN     path to the binary
    AI_CLAUDE_ARGS / AI_CODEX_ARGS / AI_GEMINI_ARGS  replace the default args
    AI_CLI_TIMEOUT                                   seconds (default 300)
"""
from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal

from ..schemas import LLMResponse
from ..utils import approx_tokens
from .base import Provider


def _timeout() -> float:
    """Read at call time so AI_CLI_TIMEOUT can be set after import."""
    return float(os.environ.get("AI_CLI_TIMEOUT", "300"))


def _render_prompt(system: str, messages: list[dict]) -> str:
    """Flatten system + messages into one prompt string.

    The CLIs take a single prompt, so the system prompt becomes a preamble.
    """
    parts: list[str] = []
    if system:
        parts.append(system.strip())
    if len(messages) == 1:
        parts.append(str(messages[0].get("content", "")).strip())
    else:
        for m in messages:
            parts.append(f"{str(m.get('role', 'user')).upper()}: {m.get('content', '')}".strip())
    return "\n\n".join(p for p in parts if p)


class CLIProvider(Provider):
    """Base for 'shell out to an agent CLI' providers.

    Subclasses set ``binary``, ``default_args`` and (optionally) ``model_flag``.
    ``{prompt}`` in default_args is replaced by the rendered prompt; if the
    placeholder is absent, the prompt is written to the process's stdin.
    """

    name = "cli"
    binary = ""
    default_args: list[str] = []
    model_flag: str | None = None
    env_prefix = "AI_CLI"

    # -- configuration ------------------------------------------------------
    def _binary(self) -> str:
        return os.environ.get(f"{self.env_prefix}_BIN", self.binary)

    def _args(self) -> list[str]:
        override = os.environ.get(f"{self.env_prefix}_ARGS")
        return shlex.split(override) if override else list(self.default_args)

    def _build_argv(self, prompt: str, model: str) -> tuple[list[str], str | None]:
        """Return (argv, stdin_payload). stdin_payload is None when the prompt
        is passed as an argument."""
        argv = [self._binary()]
        args = self._args()

        # Only pass --model when the CLI supports it and a real model is given.
        # "inherit" / "" means: let the CLI use whatever it is configured with.
        if self.model_flag and model and model not in ("inherit", "default"):
            argv += [self.model_flag, model]

        stdin_payload: str | None = prompt
        if any("{prompt}" in a for a in args):
            args = [a.replace("{prompt}", prompt) for a in args]
            stdin_payload = None
        argv += args
        return argv, stdin_payload

    # -- execution ----------------------------------------------------------
    @staticmethod
    async def _terminate(proc) -> None:
        """Kill the process *group*.

        These CLIs spawn children (shells, tools). Killing only the direct child
        leaves grandchildren running, and because they inherit the stdout pipe,
        ``proc.wait()`` then blocks until they close it. Killing the group avoids
        both the orphan and the hang.
        """
        if proc.returncode is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:  # pragma: no cover - Windows has no process groups here
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass  # reaped by the OS; don't block the run on cleanup

    async def complete(self, *, system, messages, model, temperature, max_tokens) -> LLMResponse:
        binary = self._binary()
        if not shutil.which(binary):
            raise RuntimeError(
                f"'{binary}' not found on PATH. Install the CLI and log in "
                f"(so usage draws on your subscription), or set "
                f"{self.env_prefix}_BIN to its full path."
            )

        prompt = _render_prompt(system, messages)
        argv, stdin_payload = self._build_argv(prompt, model)

        # exec (not shell) => no quoting/injection concerns with the prompt.
        # start_new_session puts the child in its own process group so we can
        # kill it and all its descendants together.
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin_payload is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name == "posix"),
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(stdin_payload.encode() if stdin_payload else None),
                timeout=_timeout(),
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Never leave an orphaned agent process behind.
            await self._terminate(proc)
            raise

        if proc.returncode != 0:
            tail = (err or b"").decode(errors="replace").strip()[-500:]
            raise RuntimeError(f"{binary} exited {proc.returncode}: {tail or '(no stderr)'}")

        text = (out or b"").decode(errors="replace").strip()
        return LLMResponse(
            text=text,
            # Estimates, NOT billing data — the CLIs don't report usage here.
            input_tokens=approx_tokens(prompt),
            output_tokens=approx_tokens(text),
            model=model or "(cli default)",
            provider=self.name,
            raw={"estimated": True, "argv": argv, "returncode": proc.returncode},
        )


class ClaudeCLIProvider(CLIProvider):
    """`claude -p "<prompt>"` — headless Claude Code, subscription login."""

    name = "claude_cli"
    binary = "claude"
    default_args = ["-p", "{prompt}"]
    model_flag = "--model"  # opus | sonnet | haiku | full id
    env_prefix = "AI_CLAUDE"


class CodexCLIProvider(CLIProvider):
    """`codex exec "<prompt>"` — Codex's scripting entry point, ChatGPT login.

    OpenAI recommends API-key auth for programmatic/CI workflows; this provider
    exists for the subscription path. Verify flags with `codex exec --help`.
    """

    name = "codex_cli"
    binary = "codex"
    default_args = ["exec", "{prompt}"]
    model_flag = "--model"
    env_prefix = "AI_CODEX"


class GeminiCLIProvider(CLIProvider):
    """`gemini -p "<prompt>"` — Gemini CLI, Google account login (free tier or
    AI Pro/Ultra). Ensure GEMINI_API_KEY is unset, or the CLI uses the API key
    (and its billing) instead of your account."""

    name = "gemini_cli"
    binary = "gemini"
    default_args = ["-p", "{prompt}"]
    model_flag = "--model"
    env_prefix = "AI_GEMINI"
