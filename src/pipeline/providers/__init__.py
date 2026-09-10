"""Model providers.

The pipeline talks to models through agent CLIs by default -- `claude`, `codex`, `gemini` --
which authenticate against a subscription rather than an API key. API providers and
offline test doubles use the same interface.

Use :func:`provider_for_stage` from pipeline code, so per-stage configuration in
``pipeline.toml`` is honoured. Use :func:`resolve_provider` when the caller has already
decided.
"""

from pipeline.providers.base import (
    MODEL_PRICES,
    FatalProviderError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    TransientProviderError,
    call_with_retry,
    classify_error,
    token_cost,
)
from pipeline.providers.cli import (
    ClaudeCLIProvider,
    CLIProvider,
    CodexCLIProvider,
    GeminiCLIProvider,
)
from pipeline.providers.fixture import DeclarationFixtureProvider, SectionFixtureProvider
from pipeline.providers.registry import (
    AUTO_ORDER,
    PROVIDERS,
    ProviderInfo,
    available_providers,
    provider_for_stage,
    resolve_auto,
    resolve_provider,
    stage_plan,
    StagePlan,
)
from pipeline.providers.replay import ReplayProvider, ScriptedProvider, request_key
from pipeline.providers.textfixture import TextFixtureProvider

__all__ = [
    "AUTO_ORDER", "CLIProvider", "ClaudeCLIProvider", "CodexCLIProvider",
    "DeclarationFixtureProvider", "FatalProviderError", "GeminiCLIProvider",
    "LLMProvider", "LLMRequest", "LLMResponse", "MODEL_PRICES", "PROVIDERS",
    "ProviderError", "ProviderInfo", "ReplayProvider", "ScriptedProvider",
    "SectionFixtureProvider", "TextFixtureProvider", "TransientProviderError",
    "available_providers", "call_with_retry", "classify_error", "provider_for_stage",
    "resolve_auto", "resolve_provider", "StagePlan", "stage_plan", "token_cost",
    "get_provider",
]


def get_provider(name: str = "auto", **kwargs) -> LLMProvider:
    """Backwards-compatible alias for :func:`resolve_provider`."""
    return resolve_provider(name, **kwargs)
