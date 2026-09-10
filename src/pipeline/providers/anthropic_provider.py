"""Anthropic provider.

Imported lazily so that the pipeline runs, and its tests pass, with no SDK and no key installed.
Credentials come from the environment only -- never a file in the repository. Report 00's
security note is the reason: the summer's extraction pipeline read its key from a text
file that sat beside the artifacts, in a directory literally named ``api keys``.
"""

from __future__ import annotations

import os
import time

from pipeline.providers.base import (
    FatalProviderError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    classify_error,
    token_cost,
)

__all__ = ["AnthropicProvider"]

ENV_KEY = "ANTHROPIC_API_KEY"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, timeout: float = 120.0) -> None:
        key = api_key or os.environ.get(ENV_KEY)
        if not key:
            raise FatalProviderError(
                f"{ENV_KEY} is not set. Export it, or use the replay provider for offline runs."
            )
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise FatalProviderError(
                "the anthropic SDK is not installed; `uv pip install -e '.[anthropic]'`"
            ) from exc
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout)

    def complete(self, request: LLMRequest) -> LLMResponse:
        content: list[dict[str, object]] = [{"type": "text", "text": request.user}]
        for image in request.images:
            import base64  # noqa: PLC0415

            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image).decode(),
                    },
                }
            )
        started = time.monotonic()
        try:
            message = self._client.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system,
                messages=[{"role": "user", "content": content}],
                stop_sequences=list(request.stop_sequences) or None,
            )
        except Exception as exc:  # noqa: BLE001 - the SDK raises many types
            raise classify_error(str(exc))(str(exc)) from exc

        text = "".join(block.text for block in message.content if block.type == "text")
        usage = getattr(message, "usage", None)
        inp = getattr(usage, "input_tokens", None)
        out = getattr(usage, "output_tokens", None)
        return LLMResponse(
            text=text,
            model=request.model,
            provider=self.name,
            input_tokens=inp,
            output_tokens=out,
            usd=token_cost(request.model, inp or 0, out or 0),
            wall_ms=int((time.monotonic() - started) * 1000),
            raw={"stop_reason": getattr(message, "stop_reason", None)},
        )
