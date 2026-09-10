"""Version-controlled prompt registry.

Requirement: prompts are artifacts, not string literals buried in application code, and
every LLM-generated artifact records the prompt version it came from.

Layout::

    prompts/<stage>/<name>/v<N>.md

A prompt file is Markdown with an optional YAML-ish front matter block delimited by
``---`` lines. Only three keys are read -- ``model``, ``max_tokens``, ``description`` --
so a prompt can carry its own default model without a separate config file.

The body is split on a line reading ``## USER`` into system and user parts. Everything
before it is the system prompt; everything after is the user template, rendered with
``str.format``-style ``{placeholders}``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pipeline.corpus.config import REPO_ROOT

__all__ = ["Prompt", "load_prompt", "latest_version", "available_prompts", "PROMPTS_DIR"]

PROMPTS_DIR = REPO_ROOT / "prompts"

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.S)
_USER_SPLIT_RE = re.compile(r"^##\s+USER\s*$", re.M)


class PromptError(RuntimeError):
    pass


@dataclass(frozen=True)
class Prompt:
    """One versioned prompt."""

    stage: str
    name: str
    version: str
    system: str
    user_template: str
    model: str | None
    max_tokens: int
    description: str
    path: Path

    @property
    def id(self) -> str:
        """The value recorded in ``Provenance.prompt_version``."""
        return f"{self.stage}/{self.name}/{self.version}"

    def render(self, **values: object) -> str:
        """Fill the user template. A missing placeholder is an error, not an empty string."""
        try:
            return self.user_template.format(**values)
        except KeyError as exc:
            raise PromptError(f"{self.id} needs placeholder {exc.args[0]!r}") from exc


def _parse(text: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    m = _FRONT_MATTER_RE.match(text)
    body = text
    if m:
        for line in m.group("body").splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        body = text[m.end() :]
    return meta, body


@cache
def load_prompt(stage: str, name: str, version: str | None = None) -> Prompt:
    """Load a prompt. ``version=None`` resolves to the highest ``vN`` present."""
    directory = PROMPTS_DIR / stage / name
    if not directory.is_dir():
        raise PromptError(f"no prompt directory {directory}")
    resolved = version or latest_version(stage, name)
    path = directory / f"{resolved}.md"
    if not path.exists():
        raise PromptError(f"no prompt {stage}/{name}/{resolved} at {path}")

    meta, body = _parse(path.read_text(encoding="utf-8"))
    parts = _USER_SPLIT_RE.split(body, maxsplit=1)
    if len(parts) != 2:
        raise PromptError(f"{path} has no '## USER' section separating system from user prompt")
    return Prompt(
        stage=stage,
        name=name,
        version=resolved,
        system=parts[0].strip(),
        user_template=parts[1].strip(),
        model=meta.get("model"),
        max_tokens=int(meta.get("max_tokens", "4096")),
        description=meta.get("description", ""),
        path=path,
    )


def latest_version(stage: str, name: str) -> str:
    directory = PROMPTS_DIR / stage / name
    versions = sorted(
        (p.stem for p in directory.glob("v*.md")),
        key=lambda v: int(v.lstrip("v") or 0),
    )
    if not versions:
        raise PromptError(f"no versions in {directory}")
    return versions[-1]


def available_prompts() -> list[str]:
    if not PROMPTS_DIR.exists():
        return []
    return sorted(
        f"{p.parent.parent.name}/{p.parent.name}/{p.stem}"
        for p in PROMPTS_DIR.glob("*/*/v*.md")
    )
