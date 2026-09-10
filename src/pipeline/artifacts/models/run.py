"""StageRun: structured execution record for every pipeline invocation.

The observability requirement. Report 04 §B8 is the motivating failure: the summer's one
hard stop was an account usage limit, and nothing in the proof loop recorded tokens or
cost, so the event is only known because a human wrote it down afterwards.

A failed run is an inspectable artifact, not a log line. Retries are counted, never silent.
"""

from __future__ import annotations

import datetime as _dt

from pydantic import Field

from pipeline.artifacts.models.base import Artifact, utc_now
from pipeline.artifacts.models.enums import Stage

__all__ = ["StageRun"]


class StageRun(Artifact):
    id: str
    stage: Stage
    target_id: str | None = Field(default=None, description="Declaration or chapter id.")
    status: str = Field(default="running", description="running | ok | failed | skipped")

    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    context_package_id: str | None = None

    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    usd: float | None = Field(default=None, ge=0)

    started_at: _dt.datetime = Field(default_factory=utc_now)
    finished_at: _dt.datetime | None = None
    wall_ms: int | None = Field(default=None, ge=0)

    retries: int = Field(default=0, ge=0)
    error: str | None = None
    error_kind: str | None = Field(default=None, description="transient | fatal | validation")

    @property
    def ok(self) -> bool:
        return self.status == "ok"
