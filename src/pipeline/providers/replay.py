"""Deterministic providers for tests and offline development.

Every LLM-backed stage must be exercisable without a network or a key. Two implementations:

* :class:`ReplayProvider` serves recorded responses keyed by a hash of the request, so a
  test asserts against a real captured model output rather than a mock's fiction.
* :class:`ScriptedProvider` returns a caller-supplied function's output, for testing the
  stage's handling of malformed, refusing or truncated responses.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from pipeline.providers.base import (
    FatalProviderError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)

__all__ = ["ReplayProvider", "ScriptedProvider", "request_key"]


def request_key(request: LLMRequest) -> str:
    """Stable key for a request. Images contribute their digest, not their bytes."""
    payload = {
        "system": request.system,
        "user": request.user,
        "model": request.model,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "images": [hashlib.sha256(i).hexdigest() for i in request.images],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class ReplayProvider(LLMProvider):
    """Serve responses from a cassette directory, recording new ones when allowed."""

    name = "replay"

    def __init__(self, cassette_dir: str | Path, *, record_with: LLMProvider | None = None) -> None:
        self.dir = Path(cassette_dir)
        self.record_with = record_with
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        key = request_key(request)
        path = self.dir / f"{key}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return LLMResponse(
                text=data["text"], model=data["model"], provider=self.name,
                input_tokens=data.get("input_tokens"), output_tokens=data.get("output_tokens"),
                usd=data.get("usd"), wall_ms=data.get("wall_ms"), raw=data.get("raw", {}),
            )
        if self.record_with is None:
            raise FatalProviderError(
                f"no recorded response for request {key} in {self.dir}; "
                "run with a live provider and --record to capture one"
            )
        response = self.record_with.complete(request)
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "text": response.text, "model": response.model,
                    "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                    "usd": response.usd, "wall_ms": response.wall_ms,
                    "_request": {"system": request.system[:400], "user": request.user[:2000]},
                },
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return response


class ScriptedProvider(LLMProvider):
    """Return whatever a supplied callable produces. For failure-path tests."""

    name = "scripted"

    def __init__(self, handler: Callable[[LLMRequest], str | LLMResponse]) -> None:
        self.handler = handler
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        result = self.handler(request)
        if isinstance(result, LLMResponse):
            return result
        return LLMResponse(
            text=result, model=request.model, provider=self.name,
            input_tokens=len(request.user) // 4, output_tokens=len(result) // 4, usd=0.0,
        )
