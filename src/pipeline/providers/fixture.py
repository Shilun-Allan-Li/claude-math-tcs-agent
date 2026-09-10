"""A provider that answers from recorded per-section fixtures.

Used by the annotation and formalization tests so that both stages are exercised end to
end -- context building, response parsing, contract enforcement, identity assignment,
graph updates, digest construction -- without a key or a network.

The fixture payloads under ``fixtures/`` are derived from real source material and from a
real annotation of it, so what the stage consumes is representative rather than invented. Where a test needs a *malformed* response, use
:class:`~pipeline.providers.replay.ScriptedProvider` instead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.providers.base import FatalProviderError, LLMProvider, LLMRequest, LLMResponse

__all__ = ["SectionFixtureProvider", "DeclarationFixtureProvider"]

_SECTION_RE = re.compile(r"section\s+(?P<section>[\d.]+)\.")
_DECLARATION_RE = re.compile(
    r'"declaration_id":\s*"(?P<id>[a-z0-9.\-]+)"'
    r"|^Declaration:\s*(?P<id2>[a-z0-9.\-]+)\s*$",
    re.M,
)


class SectionFixtureProvider(LLMProvider):
    """Dispatches on the section number named in the rendered user prompt."""

    name = "fixture"

    def __init__(self, directory: str | Path, *, model: str = "claude-opus-5") -> None:
        self.dir = Path(directory)
        self.model = model
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        m = _SECTION_RE.search(request.user)
        if not m:
            raise FatalProviderError("fixture provider could not find a section number in the prompt")
        section = m.group("section")
        path = self.dir / f"section-{section}.json"
        if not path.exists():
            raise FatalProviderError(f"no fixture for section {section} at {path}")
        text = path.read_text(encoding="utf-8")
        json.loads(text)  # fail loudly if the fixture itself is malformed
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            input_tokens=len(request.user) // 4,
            output_tokens=len(text) // 4,
            usd=0.0,
            wall_ms=0,
        )


class DeclarationFixtureProvider(LLMProvider):
    """Dispatches on the declaration id embedded in the rendered prompt."""

    name = "fixture"

    def __init__(
        self, directory: str | Path, *, model: str = "claude-opus-5", missing_ok: bool = False
    ) -> None:
        self.dir = Path(directory)
        self.model = model
        self.missing_ok = missing_ok
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        m = _DECLARATION_RE.search(request.user)
        if not m:
            raise FatalProviderError("fixture provider found no declaration id in the prompt")
        decl_id = m.group("id") or m.group("id2")
        path = self.dir / f"{decl_id}.json"
        if not path.exists():
            if self.missing_ok:
                # Nothing recorded for this declaration: an empty finding list, which is a
                # legitimate answer for a checker and keeps a partial fixture set usable.
                return LLMResponse(text="[]", model=self.model, provider=self.name,
                                   input_tokens=0, output_tokens=1, usd=0.0, wall_ms=0)
            raise FatalProviderError(f"no fixture for {decl_id} at {path}")
        text = path.read_text(encoding="utf-8")
        json.loads(text)
        return LLMResponse(
            text=text, model=self.model, provider=self.name,
            input_tokens=len(request.user) // 4, output_tokens=len(text) // 4,
            usd=0.0, wall_ms=0,
        )
