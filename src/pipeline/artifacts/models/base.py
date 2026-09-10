"""Shared base class and field types for pipeline artifacts.

Two policies are enforced here rather than repeated in every model:

* ``extra="forbid"`` -- an artifact carrying an unknown field is a bug in whatever
  produced it, not something to silently keep. Milestone 1 requires invalid artifacts to
  fail loudly.
* ``validate_assignment=True`` -- mutating a loaded artifact re-runs validation, so a
  pipeline stage cannot quietly write a bad value into a good record.
"""

from __future__ import annotations

import datetime as _dt
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Artifact", "Confidence", "utc_now", "Provenance"]


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


#: Agent-reported confidence. Deterministic checkers must report exactly 1.0.
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class Artifact(BaseModel):
    """Base class for every persisted artifact.

    Two policies are enforced here rather than repeated in every model, and both exist
    because an artifact that can be wrong silently is worse than no artifact.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=False,
        frozen=False,
    )


class Provenance(Artifact):
    """Where an artifact came from and what it was produced against.

    Report 01 §B4 is the reason this exists and is required on every agent-produced
    artifact: the summer's annotations asserted repository facts with no record of the
    repository state they were written against, and those assertions went silently false.
    """

    producer: str = Field(description="Component that produced the artifact, e.g. 'annotator'.")
    provider: str | None = Field(
        default=None, description="LLM provider, or None for deterministic producers."
    )
    model: str | None = Field(default=None, description="Model id, or None if deterministic.")
    prompt_version: str | None = Field(
        default=None, description="Version-controlled prompt identifier, e.g. 'annotate/v1'."
    )
    context_package_id: str | None = Field(
        default=None, description="ContextPackage this artifact was generated from."
    )
    input_fingerprint: str | None = Field(
        default=None, description="Fingerprint of the exact input content (staleness check)."
    )
    corpus_version: int | None = Field(
        default=None, description="Corpus registry version this was generated against."
    )
    created_at: _dt.datetime = Field(default_factory=utc_now)

    @property
    def is_deterministic(self) -> bool:
        return self.model is None
