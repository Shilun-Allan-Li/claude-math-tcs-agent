"""The provider layer: subscription CLIs, resolution, and per-stage configuration.

None of these tests make a network or subscription call. The CLI providers are exercised
against a fake executable, which is the point: the contract a client depends on is *how it
invokes* the CLI and *how it reads the result*, and both are testable without spending
anyone's quota.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from pipeline.providers import (
    AUTO_ORDER,
    ClaudeCLIProvider,
    CodexCLIProvider,
    FatalProviderError,
    GeminiCLIProvider,
    LLMRequest,
    available_providers,
    resolve_provider,
    stage_plan,
)
from pipeline.settings import Settings, StageSettings, load_settings


def _fake_executable(directory: Path, name: str, script: str) -> Path:
    """Write an executable shell stub that stands in for an agent CLI."""
    path = directory / name
    path.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def request_():
    return LLMRequest(system="SYSTEM PROMPT", user="USER PROMPT", model="opus", max_tokens=100)


class TestClaudeCLI:
    def test_the_command_disables_every_tool(self, request_, tmp_path):
        command = ClaudeCLIProvider().build_command(request_, tmp_path)
        assert "--disallowed-tools" in command
        for tool in ("Bash", "Edit", "Write", "WebFetch", "Task"):
            assert tool in command

    def test_it_replaces_rather_than_appends_the_system_prompt(self, request_, tmp_path):
        """Inheriting a coding agent's persona is wasteful and off-contract."""
        command = ClaudeCLIProvider().build_command(request_, tmp_path)
        assert "--system-prompt" in command
        assert "--append-system-prompt" not in command
        assert command[command.index("--system-prompt") + 1] == "SYSTEM PROMPT"

    def test_the_user_prompt_goes_on_stdin_not_argv(self, request_, tmp_path):
        provider = ClaudeCLIProvider()
        assert provider.stdin_for(request_) == "USER PROMPT"
        assert "USER PROMPT" not in provider.build_command(request_, tmp_path)

    def test_a_real_invocation_is_parsed_for_text_usage_and_cost(self, request_, tmp_path):
        payload = {
            "result": "PONG", "is_error": False, "subtype": "success", "num_turns": 1,
            "session_id": "abc", "stop_reason": "end_turn", "total_cost_usd": 0.0643,
            "usage": {"input_tokens": 2, "output_tokens": 5, "cache_read_input_tokens": 6790},
        }
        _fake_executable(tmp_path, "claude", f"cat > /dev/null; echo '{json.dumps(payload)}'")
        provider = ClaudeCLIProvider(executable=str(tmp_path / "claude"))
        response = provider.complete(request_)
        assert response.text == "PONG"
        assert response.provider == "claude-cli"
        assert (response.input_tokens, response.output_tokens) == (2, 5)
        assert response.usd == 0.0643, "the CLI's own cost is preferred over a price table"
        assert response.raw["cache_read_input_tokens"] == 6790

    def test_an_error_result_is_raised_not_returned(self, request_, tmp_path):
        payload = {"result": "rate limit exceeded", "is_error": True}
        _fake_executable(tmp_path, "claude", f"cat > /dev/null; echo '{json.dumps(payload)}'")
        with pytest.raises(Exception, match="rate limit"):
            ClaudeCLIProvider(executable=str(tmp_path / "claude")).complete(request_)

    def test_a_nonzero_exit_is_reported_with_its_output(self, request_, tmp_path):
        _fake_executable(tmp_path, "claude", "cat > /dev/null; echo 'not signed in' >&2; exit 1")
        with pytest.raises(FatalProviderError, match="not signed in"):
            ClaudeCLIProvider(executable=str(tmp_path / "claude")).complete(request_)

    def test_an_empty_response_is_an_error(self, request_, tmp_path):
        _fake_executable(tmp_path, "claude", 'cat > /dev/null; echo \'{"result":"  "}\'')
        with pytest.raises(FatalProviderError, match="empty response"):
            ClaudeCLIProvider(executable=str(tmp_path / "claude")).complete(request_)


class TestCodexCLI:
    def test_the_sandbox_is_read_only(self, request_, tmp_path):
        command = CodexCLIProvider().build_command(request_, tmp_path)
        assert command[:2] == ["codex", "exec"]
        assert "--sandbox" in command and "read-only" in command
        assert "--skip-git-repo-check" in command

    def test_the_system_prompt_is_prepended_with_a_visible_boundary(self, request_):
        stdin = CodexCLIProvider().stdin_for(request_)
        assert stdin.startswith("SYSTEM PROMPT")
        assert stdin.endswith("USER PROMPT")
        assert "---" in stdin

    def test_text_comes_from_the_message_file_and_usage_from_the_events(
        self, request_, tmp_path
    ):
        events = "\n".join([
            json.dumps({"type": "thread.started", "thread_id": "t"}),
            json.dumps({"type": "item.completed",
                        "item": {"type": "agent_message", "text": "PONG"}}),
            json.dumps({"type": "turn.completed",
                        "usage": {"input_tokens": 15398, "output_tokens": 6}}),
        ])
        _fake_executable(
            tmp_path, "codex",
            'cat > /dev/null\n'
            'for a in "$@"; do prev=$last; last=$a; if [ "$prev" = "-o" ]; then out=$a; fi; done\n'
            'printf "PONG" > "$out"\n'
            f"cat <<'EOF'\n{events}\nEOF\n",
        )
        provider = CodexCLIProvider(executable=str(tmp_path / "codex"))
        response = provider.complete(request_)
        assert response.text == "PONG"
        assert (response.input_tokens, response.output_tokens) == (15398, 6)

    def test_an_unpriced_model_reports_no_cost_rather_than_zero(self, request_, tmp_path):
        """A missing price must not read as free in a budget report."""
        _fake_executable(
            tmp_path, "codex",
            'cat > /dev/null\n'
            'for a in "$@"; do prev=$last; last=$a; if [ "$prev" = "-o" ]; then out=$a; fi; done\n'
            'printf "PONG" > "$out"\n',
        )
        provider = CodexCLIProvider(executable=str(tmp_path / "codex"), model="gpt-unknown")
        assert provider.complete(request_).usd is None


class TestGeminiCLI:
    def test_a_structured_error_is_surfaced(self, request_, tmp_path):
        payload = {"error": {"message": "Please set an Auth method", "code": 41}}
        _fake_executable(tmp_path, "gemini", f"cat > /dev/null; echo '{json.dumps(payload)}'")
        with pytest.raises(FatalProviderError, match="Auth method"):
            GeminiCLIProvider(executable=str(tmp_path / "gemini")).complete(request_)


class TestSharedCLIBehaviour:
    def test_images_are_refused_with_a_pointer_to_what_does_work(self, tmp_path):
        request = LLMRequest(system="s", user="u", model="m", images=(b"PNG",))
        with pytest.raises(FatalProviderError, match="API provider"):
            ClaudeCLIProvider(executable=str(_fake_executable(tmp_path, "claude", "true"))).complete(request)

    def test_a_missing_executable_says_how_to_install_it(self):
        class Missing(ClaudeCLIProvider):
            executable = "definitely-not-installed-xyz"

        reason = Missing.unavailable_reason()
        assert reason and "not on PATH" in reason
        with pytest.raises(FatalProviderError, match="not on PATH"):
            Missing().complete(LLMRequest(system="s", user="u", model="m"))

    def test_pipeline_own_env_is_not_leaked_into_the_child(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIPELINE_PROVIDER", "codex-cli")
        monkeypatch.setenv("PATH_MARKER", "kept")
        env = ClaudeCLIProvider()._environment()
        assert "PIPELINE_PROVIDER" not in env
        assert env.get("PATH_MARKER") == "kept"


class TestResolution:
    def test_auto_prefers_subscription_clis_over_api_keys(self):
        assert AUTO_ORDER.index("claude-cli") < AUTO_ORDER.index("anthropic")
        assert AUTO_ORDER.index("codex-cli") < AUTO_ORDER.index("anthropic")

    def test_availability_explains_every_unavailable_option(self):
        for info in available_providers():
            assert info.available or info.reason, f"{info.name} is unavailable with no reason"

    def test_an_unknown_provider_lists_the_known_ones(self):
        with pytest.raises(FatalProviderError, match="known:"):
            resolve_provider("not-a-provider")

    def test_an_explicitly_named_unusable_provider_says_why(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(FatalProviderError, match="ANTHROPIC_API_KEY"):
            resolve_provider("anthropic")


class TestStageConfiguration:
    def test_settings_are_optional(self, tmp_path):
        load_settings.cache_clear()
        settings = load_settings(tmp_path / "absent.toml")
        assert settings.default_provider == "auto"
        load_settings.cache_clear()

    def test_a_stage_table_overrides_the_default(self, tmp_path):
        (tmp_path / "pipeline.toml").write_text(
            '[provider]\ndefault = "claude-cli"\n\n[stage.prove]\nprovider = "codex-cli"\n',
            encoding="utf-8",
        )
        load_settings.cache_clear()
        settings = load_settings(tmp_path / "pipeline.toml")
        assert settings.for_stage("annotate").provider == "claude-cli"
        assert settings.for_stage("prove").provider == "codex-cli"
        load_settings.cache_clear()

    def test_environment_beats_the_file(self, monkeypatch):
        settings = Settings(default_provider="claude-cli",
                            stages={"prove": StageSettings(provider="codex-cli")})
        monkeypatch.setenv("PIPELINE_PROVIDER", "gemini-cli")
        assert settings.for_stage("prove").provider == "gemini-cli"

    def test_a_per_stage_variable_beats_the_global_one(self, monkeypatch):
        settings = Settings(default_provider="claude-cli")
        monkeypatch.setenv("PIPELINE_PROVIDER", "gemini-cli")
        monkeypatch.setenv("PIPELINE_PROVIDER_PROVE", "codex-cli")
        assert settings.for_stage("prove").provider == "codex-cli"
        assert settings.for_stage("annotate").provider == "gemini-cli"

    def test_an_explicit_argument_beats_everything(self, monkeypatch):
        settings = Settings(default_provider="claude-cli")
        monkeypatch.setenv("PIPELINE_PROVIDER", "gemini-cli")
        assert settings.for_stage("prove", provider="codex-cli").provider == "codex-cli"

    def test_the_reported_plan_is_what_a_run_will_use(self):
        """`pipeline providers` and the pipeline must not disagree."""
        plan = stage_plan("annotate", provider="claude-cli", model="sonnet")
        assert plan.provider == "claude-cli" and plan.model == "sonnet"

    def test_a_provider_default_model_applies_once_auto_has_chosen(self):
        """`[provider.<name>] model` is only reachable after `auto` picks that provider."""
        settings = Settings(
            default_provider="auto",
            provider_defaults={"claude-cli": StageSettings(model="opus")},
        )
        # Settings alone cannot expand `auto` -- it deliberately does not import the
        # registry -- so the model is still unresolved here...
        assert settings.for_stage("annotate").model is None
        # ...and the registry, which can, supplies it.
        assert stage_plan("annotate", provider="claude-cli").model == "opus"
