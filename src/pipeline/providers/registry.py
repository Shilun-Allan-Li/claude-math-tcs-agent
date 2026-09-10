"""Provider discovery and resolution.

``auto`` is the important case. It asks each known provider whether it can run on this
machine and picks the first that can, preferring subscription CLIs over API keys — because
a subscription is what most people already have, and because an API key is a credential to
manage whereas a signed-in CLI is not.

The ordering is deliberate and stable, so `auto` is predictable rather than surprising.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pipeline.providers.base import FatalProviderError, LLMProvider
from pipeline.providers.cli import (
    ClaudeCLIProvider,
    CLIProvider,
    CodexCLIProvider,
    GeminiCLIProvider,
)

__all__ = [
    "PROVIDERS",
    "AUTO_ORDER",
    "ProviderInfo",
    "available_providers",
    "resolve_auto",
    "resolve_provider",
    "provider_for_stage",
    "stage_plan",
    "StagePlan",
]

#: Every provider the pipeline knows, by name.
PROVIDERS: dict[str, type] = {
    "claude-cli": ClaudeCLIProvider,
    "codex-cli": CodexCLIProvider,
    "gemini-cli": GeminiCLIProvider,
}

#: What ``auto`` tries, in order. Subscription CLIs first; an API key is the fallback.
AUTO_ORDER: tuple[str, ...] = ("claude-cli", "codex-cli", "gemini-cli", "anthropic")


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    kind: str  # "subscription-cli" | "api-key" | "test"
    available: bool
    reason: str | None = None
    note: str = ""


def _anthropic_available() -> tuple[bool, str | None]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY is not set"
    try:
        import anthropic  # noqa: F401, PLC0415
    except ImportError:
        return False, "the anthropic SDK is not installed (`uv pip install -e '.[anthropic]'`)"
    return True, None


def available_providers() -> list[ProviderInfo]:
    """What can actually run here, and why anything cannot."""
    infos: list[ProviderInfo] = []
    for name, cls in PROVIDERS.items():
        reason = cls.unavailable_reason()
        infos.append(ProviderInfo(
            name=name, kind="subscription-cli", available=reason is None, reason=reason,
            note="uses your existing subscription; no API key",
        ))
    ok, reason = _anthropic_available()
    infos.append(ProviderInfo(
        name="anthropic", kind="api-key", available=ok, reason=reason,
        note="per-token billing against an API key",
    ))
    for name, note in (
        ("replay", "serves recorded responses from a cassette directory"),
        ("fixture", "serves recorded per-declaration fixtures; used by the test suite"),
    ):
        infos.append(ProviderInfo(name=name, kind="test", available=True, note=note))
    return infos


def resolve_auto() -> str:
    """The concrete provider name ``auto`` selects here, or raise with what was checked."""
    for candidate in AUTO_ORDER:
        cls = PROVIDERS.get(candidate)
        if cls is not None and cls.unavailable_reason() is None:
            return candidate
        if candidate == "anthropic" and _anthropic_available()[0]:
            return "anthropic"
    raise FatalProviderError(
        "no model provider is available. The pipeline needs one of:\n"
        "  * an agent CLI you are signed in to -- install Claude Code (`claude`) or "
        "the Codex CLI (`codex`); no API key needed\n"
        "  * ANTHROPIC_API_KEY, with `uv pip install -e '.[anthropic]'`\n"
        "  * `--fixtures <dir>` to replay recorded responses offline\n"
        "Run `pipeline providers` to see what was checked."
    )


def resolve_provider(
    name: str | None = None, *, model: str | None = None, **kwargs
) -> LLMProvider:
    """Build a provider. ``None`` or ``"auto"`` picks the best available one.

    Raises :class:`FatalProviderError` with an actionable message when nothing is usable,
    rather than failing later inside a stage with something opaque.
    """
    requested = name or "auto"
    if requested == "auto":
        requested = resolve_auto()

    if requested in PROVIDERS:
        cls = PROVIDERS[requested]
        if reason := cls.unavailable_reason():
            raise FatalProviderError(f"provider {requested!r} is not usable: {reason}")
        return cls(model=model, **kwargs)

    if requested == "anthropic":
        ok, reason = _anthropic_available()
        if not ok:
            raise FatalProviderError(f"provider 'anthropic' is not usable: {reason}")
        from pipeline.providers.anthropic_provider import AnthropicProvider  # noqa: PLC0415

        return AnthropicProvider(**kwargs)

    if requested == "replay":
        from pipeline.providers.replay import ReplayProvider  # noqa: PLC0415

        return ReplayProvider(**kwargs)

    known = ", ".join([*PROVIDERS, "anthropic", "replay", "auto"])
    raise FatalProviderError(f"unknown provider {requested!r}; known: {known}")


@dataclass(frozen=True)
class StagePlan:
    """What a stage will actually use, after settings, env and ``auto`` are applied."""

    stage: str
    provider: str
    model: str | None
    extra_args: tuple[str, ...] = ()


def stage_plan(
    stage: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    resolve: bool = True,
) -> StagePlan:
    """Decide the provider and model for a stage without constructing anything.

    Shared by :func:`provider_for_stage` and by ``pipeline providers``, so what the command
    reports is exactly what a run will do. ``resolve=False`` leaves ``auto`` unexpanded,
    which is useful when nothing is installed and the command should still print a table.
    """
    from pipeline.settings import StageSettings, load_settings  # noqa: PLC0415

    settings = load_settings()
    resolved = settings.for_stage(stage, provider=provider, model=model)
    concrete = resolved.provider or "auto"
    if concrete == "auto" and resolve:
        concrete = resolve_auto()

    # A model named in `[provider.<name>]` applies once `auto` has picked that provider,
    # which is only knowable here -- settings deliberately does not import the registry.
    defaults = settings.provider_defaults.get(concrete, StageSettings())
    return StagePlan(
        stage=stage,
        provider=concrete,
        model=resolved.model or defaults.model,
        extra_args=resolved.extra_args or defaults.extra_args,
    )


def provider_for_stage(
    stage: str, *, provider: str | None = None, model: str | None = None, **kwargs
) -> LLMProvider:
    """Resolve the provider for a named pipeline stage, honouring settings and env."""
    plan = stage_plan(stage, provider=provider, model=model)
    cls = PROVIDERS.get(plan.provider)
    if plan.extra_args and cls is not None and issubclass(cls, CLIProvider):
        kwargs.setdefault("extra_args", plan.extra_args)
    return resolve_provider(plan.provider, model=plan.model, **kwargs)
