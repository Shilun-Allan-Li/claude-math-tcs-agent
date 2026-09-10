"""Pipeline settings: which provider and model each stage uses.

Resolution order, most specific first:

1. an explicit argument (``--provider`` / ``--model`` on the command line);
2. environment: ``PIPELINE_PROVIDER`` / ``PIPELINE_MODEL``, or the per-stage
   ``PIPELINE_PROVIDER_<STAGE>`` / ``PIPELINE_MODEL_<STAGE>``;
3. the ``[stage.<name>]`` table in ``pipeline.toml``;
4. the ``[provider]`` defaults in ``pipeline.toml``;
5. ``auto`` -- the first usable provider found on this machine.

The file is optional. With no configuration at all, the pipeline finds whichever agent CLI is
installed and uses it, so a fresh clone works for anyone who is already signed in to
Claude or ChatGPT.

Prompts still carry a suggested model in their front matter; that is a *hint* for a
provider that understands the name, and settings override it. Model names are not portable
across providers, which is why the pairing lives here rather than in the prompt.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from pipeline.corpus.config import REPO_ROOT

__all__ = ["Settings", "StageSettings", "load_settings", "SETTINGS_FILENAME"]

SETTINGS_FILENAME = "pipeline.toml"


@dataclass(frozen=True)
class StageSettings:
    provider: str | None = None
    model: str | None = None
    #: Extra argv appended to a CLI provider's command, for per-stage tuning.
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class Settings:
    default_provider: str = "auto"
    default_model: str | None = None
    provider_defaults: dict[str, StageSettings] = field(default_factory=dict)
    stages: dict[str, StageSettings] = field(default_factory=dict)
    path: Path | None = None

    def for_stage(
        self, stage: str, *, provider: str | None = None, model: str | None = None
    ) -> StageSettings:
        """Resolve the provider and model for one stage."""
        env_stage = stage.upper().replace("-", "_")
        resolved_provider = (
            provider
            or os.environ.get(f"PIPELINE_PROVIDER_{env_stage}")
            or os.environ.get("PIPELINE_PROVIDER")
            or self.stages.get(stage, StageSettings()).provider
            or self.default_provider
        )
        resolved_model = (
            model
            or os.environ.get(f"PIPELINE_MODEL_{env_stage}")
            or os.environ.get("PIPELINE_MODEL")
            or self.stages.get(stage, StageSettings()).model
        )
        if resolved_model is None and resolved_provider != "auto":
            resolved_model = self.provider_defaults.get(
                resolved_provider, StageSettings()
            ).model
        if resolved_model is None:
            resolved_model = self.default_model
        extra = (
            self.stages.get(stage, StageSettings()).extra_args
            or self.provider_defaults.get(resolved_provider, StageSettings()).extra_args
        )
        return StageSettings(provider=resolved_provider, model=resolved_model, extra_args=extra)


def _stage_settings(raw: dict[str, Any]) -> StageSettings:
    return StageSettings(
        provider=raw.get("provider"),
        model=raw.get("model"),
        extra_args=tuple(raw.get("extra_args", ())),
    )


@cache
def load_settings(path: str | Path | None = None) -> Settings:
    """Load ``pipeline.toml``. Absent file means defaults, not an error."""
    target = Path(path) if path else REPO_ROOT / SETTINGS_FILENAME
    if not target.exists():
        return Settings()
    data = tomllib.loads(target.read_text(encoding="utf-8"))

    provider_table = data.get("provider", {})
    provider_defaults = {
        key: _stage_settings(value)
        for key, value in provider_table.items()
        if isinstance(value, dict)
    }
    return Settings(
        default_provider=provider_table.get("default", "auto"),
        default_model=provider_table.get("model"),
        provider_defaults=provider_defaults,
        stages={
            name: _stage_settings(value)
            for name, value in data.get("stage", {}).items()
            if isinstance(value, dict)
        },
        path=target,
    )
