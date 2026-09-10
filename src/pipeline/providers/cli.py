"""Providers that drive a locally-installed agent CLI.

This is the default way the pipeline talks to a model, and the reason is access rather than
taste: `claude`, `codex` and `gemini` authenticate against a **subscription** the user
already has. No API key, no per-token billing account, no separate credential to manage or
leak. Someone with a Claude or ChatGPT plan can run this pipeline as-is.

Each provider is a subprocess call with no session state, which is what makes it a
drop-in for the API providers: one request in, one response out (rule 1). The CLIs are
agentic by default, so every provider here **disables their tools** — the pipeline wants a
completion, not an agent that edits the working tree behind its back.

Adding another CLI means subclassing :class:`CLIProvider` and implementing ``build_command``
and ``parse_output``. Nothing else changes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pipeline.providers.base import (
    FatalProviderError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    classify_error,
    token_cost,
)

__all__ = [
    "CLIProvider",
    "ClaudeCLIProvider",
    "CodexCLIProvider",
    "GeminiCLIProvider",
    "CLIResult",
]


@dataclass
class CLIResult:
    """What a CLI produced, before it becomes an :class:`LLMResponse`."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    usd: float | None = None
    raw: dict[str, object] | None = None


class CLIProvider(LLMProvider):
    """Base for subprocess-driven agent CLIs."""

    #: Executable name, looked up on PATH.
    executable: str = ""
    #: Human-facing note shown when the executable is missing.
    install_hint: str = ""

    def __init__(
        self,
        *,
        model: str | None = None,
        executable: str | None = None,
        timeout: float = 600.0,
        cwd: str | Path | None = None,
        extra_args: Sequence[str] = (),
    ) -> None:
        self.model = model
        self.executable = executable or type(self).executable
        self.timeout = timeout
        # Run in a scratch directory by default. These CLIs read project configuration
        # (CLAUDE.md, AGENTS.md, .codex) from the working directory, and a completion
        # provider should not inherit whatever repository it happens to be invoked from.
        self.cwd = Path(cwd) if cwd else None
        self.extra_args = list(extra_args)
        self.calls: list[LLMRequest] = []

    # ------------------------------------------------------------- availability

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which(cls.executable) is not None

    @classmethod
    def unavailable_reason(cls) -> str | None:
        if shutil.which(cls.executable) is None:
            return f"`{cls.executable}` is not on PATH. {cls.install_hint}".strip()
        return None

    # ------------------------------------------------------------------- hooks

    @abstractmethod
    def build_command(self, request: LLMRequest, workdir: Path) -> list[str]:
        """The argv to run. ``workdir`` is a scratch directory for this call only."""

    @abstractmethod
    def parse_output(
        self, stdout: str, stderr: str, workdir: Path, request: LLMRequest
    ) -> CLIResult:
        """Turn the CLI's output into text plus whatever accounting it exposed."""

    def stdin_for(self, request: LLMRequest) -> str | None:
        """Text to pipe in, when the prompt is too large for an argv."""
        return None

    # ------------------------------------------------------------------- run

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if reason := type(self).unavailable_reason():
            raise FatalProviderError(reason)
        if request.images:
            raise FatalProviderError(
                f"{self.name} cannot take images; use an API provider for the ingest stage"
            )

        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="pipeline-cli-") as tmp:
            workdir = Path(tmp)
            command = self.build_command(request, workdir)
            stdin_text = self.stdin_for(request)
            try:
                proc = subprocess.run(
                    command,
                    cwd=str(self.cwd or workdir),
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    # A CLI that inherits a huge environment can pick up settings the
                    # caller never intended; pass through only what it needs to find the
                    # user's own credentials and config.
                    env=self._environment(),
                )
            except subprocess.TimeoutExpired as exc:
                raise classify_error("timeout")(
                    f"{self.name} timed out after {self.timeout:.0f}s"
                ) from exc
            except FileNotFoundError as exc:
                raise FatalProviderError(f"{self.executable} not found") from exc

            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()[-800:]
                raise classify_error(detail)(
                    f"{self.name} exited {proc.returncode}: {detail or '(no output)'}"
                )

            try:
                result = self.parse_output(proc.stdout, proc.stderr, workdir, request)
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise FatalProviderError(
                    f"could not read {self.name} output: {type(exc).__name__}: {exc}"
                ) from exc

        if not result.text.strip():
            raise FatalProviderError(f"{self.name} returned an empty response")

        return LLMResponse(
            text=result.text,
            model=self.model or request.model,
            provider=self.name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            usd=result.usd,
            wall_ms=int((time.monotonic() - started) * 1000),
            raw=result.raw or {},
        )

    def _environment(self) -> dict[str, str]:
        """Environment for the child. Inherits the user's, minus the pipeline's own knobs."""
        env = dict(os.environ)
        for key in list(env):
            if key.startswith("PIPELINE_"):
                env.pop(key, None)
        return env


# --------------------------------------------------------------------- claude


class ClaudeCLIProvider(CLIProvider):
    """Claude Code in print mode. Authenticates against a Claude subscription."""

    name = "claude-cli"
    executable = "claude"
    install_hint = "Install Claude Code and run `claude` once to sign in."

    #: Claude Code is an agent; for a completion role every tool is off.
    DISABLED_TOOLS = (
        "Bash", "Edit", "Write", "Read", "Glob", "Grep",
        "WebFetch", "WebSearch", "Task", "NotebookEdit",
    )

    def build_command(self, request: LLMRequest, workdir: Path) -> list[str]:
        command = [
            self.executable,
            "-p",
            "--output-format", "json",
            # Replace Claude Code's own system prompt rather than appending to it: the
            # stage's prompt is the whole instruction, and inheriting a coding agent's
            # persona is both wasteful and a source of off-contract behaviour.
            "--system-prompt", request.system,
            "--exclude-dynamic-system-prompt-sections",
            "--disallowed-tools", *self.DISABLED_TOOLS,
        ]
        model = self.model or request.model
        if model:
            command += ["--model", model]
        command += self.extra_args
        return command

    def stdin_for(self, request: LLMRequest) -> str:
        # The user prompt goes on stdin, not argv: stage prompts routinely exceed the
        # argument-length limit, and piping avoids shell-quoting the whole corpus.
        return request.user

    def parse_output(
        self, stdout: str, stderr: str, workdir: Path, request: LLMRequest
    ) -> CLIResult:
        payload = json.loads(stdout)
        if payload.get("is_error"):
            raise classify_error(str(payload.get("result", "")))(
                f"claude reported an error: {payload.get('result')}"
            )
        usage = payload.get("usage") or {}
        return CLIResult(
            text=str(payload.get("result", "")),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            # Claude Code reports real cost, including cache reads. Prefer it over any
            # price table: it is the number the user is actually billed.
            usd=payload.get("total_cost_usd"),
            raw={
                "session_id": payload.get("session_id"),
                "stop_reason": payload.get("stop_reason"),
                "num_turns": payload.get("num_turns"),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            },
        )


# ---------------------------------------------------------------------- codex


class CodexCLIProvider(CLIProvider):
    """OpenAI Codex in exec mode. Authenticates against a ChatGPT subscription."""

    name = "codex-cli"
    executable = "codex"
    install_hint = "Install the Codex CLI and run `codex login`."

    def build_command(self, request: LLMRequest, workdir: Path) -> list[str]:
        self._message_file = workdir / "message.txt"
        command = [
            self.executable, "exec",
            "--sandbox", "read-only",       # no writes, whatever the model decides to try
            "--skip-git-repo-check",        # the scratch workdir is not a repository
            "--json",                       # structured events, for token accounting
            "-o", str(self._message_file),  # the final message, clean
            "-",                            # read the prompt from stdin
        ]
        model = self.model or request.model
        if model:
            command += ["-m", model]
        command += self.extra_args
        return command

    def stdin_for(self, request: LLMRequest) -> str:
        # Codex has no separate system-prompt flag, so the stage's system prompt is
        # prepended. The boundary is marked explicitly so the model can see where its
        # instructions end and the payload begins.
        return f"{request.system}\n\n---\n\n{request.user}"

    def parse_output(
        self, stdout: str, stderr: str, workdir: Path, request: LLMRequest
    ) -> CLIResult:
        text = ""
        if self._message_file.exists():
            text = self._message_file.read_text(encoding="utf-8")

        input_tokens = output_tokens = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "turn.completed":
                usage = event.get("usage") or {}
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
            elif not text and event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    text = str(item.get("text", ""))

        model = self.model or request.model
        return CLIResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            # Codex reports tokens but not cost; a price is only quoted for models the pipeline
            # knows a rate for, and None otherwise so nothing reads as free.
            usd=token_cost(model, input_tokens or 0, output_tokens or 0) if model else None,
            raw={"events": stdout.count("\n")},
        )


# --------------------------------------------------------------------- gemini


class GeminiCLIProvider(CLIProvider):
    """Gemini CLI in headless mode."""

    name = "gemini-cli"
    executable = "gemini"
    install_hint = "Install the Gemini CLI and configure an auth method."

    _TOKEN_RE = re.compile(r'"(?P<key>input|output|prompt|candidates)[_a-zA-Z]*Token[sS]?"\s*:\s*(?P<n>\d+)')

    def build_command(self, request: LLMRequest, workdir: Path) -> list[str]:
        command = [self.executable, "-o", "json", "-p", "-"]
        model = self.model or request.model
        if model:
            command += ["-m", model]
        return command + self.extra_args

    def stdin_for(self, request: LLMRequest) -> str:
        return f"{request.system}\n\n---\n\n{request.user}"

    def parse_output(
        self, stdout: str, stderr: str, workdir: Path, request: LLMRequest
    ) -> CLIResult:
        payload = json.loads(stdout)
        if error := payload.get("error"):
            raise FatalProviderError(f"gemini: {error.get('message', error)}")
        stats = payload.get("stats") or {}
        return CLIResult(
            text=str(payload.get("response", "")),
            input_tokens=stats.get("promptTokenCount") or stats.get("inputTokens"),
            output_tokens=stats.get("candidatesTokenCount") or stats.get("outputTokens"),
            usd=None,
            raw={"session_id": payload.get("session_id")},
        )
