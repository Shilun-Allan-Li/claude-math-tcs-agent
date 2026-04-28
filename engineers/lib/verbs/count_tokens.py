"""Verb: count-tokens — count tokens for a given model.

Uses tiktoken if installed (for OpenAI-family models). Falls back to a
char/3.5 approximation for everything else, marking the report
`approximate: true`.
"""

from __future__ import annotations

from pathlib import Path


def run(args: dict, request_id: str) -> dict:
    """args: {"path": str | "text": str, "model": str}"""
    if "text" in args:
        text = args["text"]
    elif "path" in args:
        text = Path(args["path"]).read_text(errors="replace")
    else:
        raise ValueError("must provide either 'text' or 'path'")

    model = args.get("model", "claude")
    char_count = len(text)

    tokens, approximate = _count(text, model)
    return {
        "model": model,
        "tokens": tokens,
        "char_count": char_count,
        "approximate": approximate,
    }


def _count(text: str, model: str) -> tuple[int, bool]:
    try:
        import tiktoken  # type: ignore
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), False
    except ImportError:
        # Anthropic-friendly approximation; conservative.
        return max(1, round(len(text) / 3.5)), True
