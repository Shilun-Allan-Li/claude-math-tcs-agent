"""Provider abstraction for LLM-backed stages.

Requirements this encodes, from the brief and from the forensic reports:

* **No permanent conversation.** A provider takes a request and returns a response. There
  is no session object, because a session is state that escapes the artifact model
  (rule 1). Report 06 §D measured the alternative: twelve mutually-blind chapter agents
  producing twelve colliding declaration names.
* **Per-stage model configuration**, so the annotator and the proof worker can differ.
* **Usage and cost on every response.** Report 04 §B8: the summer's one hard stop was an
  account usage limit and nothing in the loop recorded tokens.
* **Transient vs fatal retry classification.** Lifted from ``tcslib/proofmatch/agents.py``,
  which distinguished the two correctly; a schema rejection or a content filter must fail
  fast rather than burn three attempts.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

__all__ = [
    "LLMRequest",
    "LLMResponse",
    "LLMProvider",
    "ProviderError",
    "TransientProviderError",
    "FatalProviderError",
    "MODEL_PRICES",
    "token_cost",
    "call_with_retry",
]


class ProviderError(RuntimeError):
    pass


class TransientProviderError(ProviderError):
    """Worth retrying: rate limits, overload, timeouts, 5xx."""


class FatalProviderError(ProviderError):
    """Not worth retrying: bad request, schema rejection, content filter, auth."""


#: USD per million input / output tokens. Kept beside the provider so a cost figure is
#: never a guess. Update when pricing changes; the value is recorded per run anyway.
MODEL_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5": (Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5-20251001": (Decimal("1.00"), Decimal("5.00")),
}


def token_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD for a call, or None when the model's price is unknown.

    Returning None rather than 0.0 matters: an unknown price must not silently read as
    free in a budget report.
    """
    price = MODEL_PRICES.get(model)
    if price is None:
        return None
    inp, out = price
    total = (Decimal(input_tokens) * inp + Decimal(output_tokens) * out) / Decimal(1_000_000)
    return float(total)


@dataclass(frozen=True)
class LLMRequest:
    """One self-contained call. No history, by construction."""

    system: str
    user: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.0
    stop_sequences: Sequence[str] = ()
    images: Sequence[bytes] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    usd: float | None = None
    wall_ms: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Minimal surface every provider implements."""

    name: str = "abstract"

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute one request. Raise Transient/FatalProviderError on failure."""

    def close(self) -> None:  # pragma: no cover - most providers need nothing
        return None


#: Substrings marking a failure a retry can plausibly fix.
_TRANSIENT_MARKERS = (
    "connection reset", "connection error", "connection closed", "timed out", "timeout",
    "overloaded", "rate limit", "429", "500", "502", "503", "504", "529",
    "internal server error", "service unavailable", "temporarily",
)


def classify_error(detail: str) -> type[ProviderError]:
    lowered = (detail or "").casefold()
    return (
        TransientProviderError
        if any(marker in lowered for marker in _TRANSIENT_MARKERS)
        else FatalProviderError
    )


def call_with_retry(
    provider: LLMProvider,
    request: LLMRequest,
    *,
    attempts: int = 3,
    backoff_seconds: float = 2.0,
    sleep=time.sleep,
) -> tuple[LLMResponse, int]:
    """Call a provider with bounded retries. Returns (response, retries_used).

    Retries are counted and surfaced, never silent: the caller records the count on the
    :class:`~pipeline.artifacts.models.run.StageRun` so a flaky stage is visible rather than merely slow.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return provider.complete(request), attempt
        except FatalProviderError:
            raise
        except TransientProviderError as exc:
            last = exc
            if attempt == attempts - 1:
                break
            sleep(backoff_seconds * (2**attempt))
    raise TransientProviderError(f"exhausted {attempts} attempts: {last}") from last
