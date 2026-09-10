"""A provider that returns recorded plain-text responses, keyed by declaration id.

Used for the proof stage, whose responses are Lean tactic blocks rather than JSON.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline.providers.base import FatalProviderError, LLMProvider, LLMRequest, LLMResponse

__all__ = ["TextFixtureProvider"]

_DECLARATION_RE = re.compile(r"^Declaration:\s*(?P<id>[a-z0-9.\-]+)\s*$", re.M)


class TextFixtureProvider(LLMProvider):
    name = "fixture"

    def __init__(
        self,
        directory: str | Path,
        *,
        model: str = "claude-opus-5",
        override: str | None = None,
    ) -> None:
        self.dir = Path(directory)
        self.model = model
        #: When set, every call returns this file's contents regardless of target. Used to
        #: exercise a specific worker behaviour, such as declining the statement.
        self.override = override
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self.override:
            path = self.dir / self.override
        else:
            m = _DECLARATION_RE.search(request.user)
            if not m:
                raise FatalProviderError("no declaration id in the prompt")
            path = self.dir / f"{m.group('id')}.txt"
        if not path.exists():
            raise FatalProviderError(f"no recorded proof at {path}")
        text = path.read_text(encoding="utf-8")
        return LLMResponse(
            text=text, model=self.model, provider=self.name,
            input_tokens=len(request.user) // 4, output_tokens=len(text) // 4,
            usd=0.0, wall_ms=0,
        )
