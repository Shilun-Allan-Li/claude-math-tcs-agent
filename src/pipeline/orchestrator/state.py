"""Run state: the pipeline's memory, on disk rather than in a conversation.

This is the piece that makes "a fresh process can resume the run" true. Two facts are
kept strictly apart:

* **Artifact state** -- what the pipeline produced -- lives in the :class:`ArtifactStore`
  and is authoritative. :func:`derive_stage` reads a declaration's stage back out of its
  artifacts alone, so a run's progress can always be recomputed from what is on disk.
* **Run state** -- which declarations this particular invocation is driving, what it has
  attempted, and what failed -- lives here.

The second is deliberately not trusted over the first. On resume the orchestrator
recomputes every declaration's stage from artifacts and only then replays run bookkeeping,
so a run record that disagrees with the artifacts loses. A run file that could contradict
the artifacts it describes would be exactly the "assertions about a repository state
nothing recorded" failure the rest of this project is built to prevent.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from pipeline.artifacts.models import DeclarationRecord, ReviewStatus, TrustStatus
from pipeline.artifacts.models.base import Artifact, utc_now

__all__ = [
    "RunStatus",
    "DeclarationStage",
    "StepStatus",
    "RunEvent",
    "DeclarationState",
    "PipelineRun",
    "RunStore",
    "derive_stage",
    "STAGE_ORDER",
]


class RunStatus(StrEnum):
    """Lifecycle of one pipeline run."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"
    PROVING = "PROVING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class DeclarationStage(StrEnum):
    """How far one declaration has travelled. Derived from artifacts, never asserted."""

    INGESTED = "INGESTED"
    ANNOTATED = "ANNOTATED"
    FORMALIZED = "FORMALIZED"
    CHECKED = "CHECKED"
    APPROVED = "APPROVED"
    PROVED = "PROVED"


#: Progression order. Index comparison decides what may run next.
STAGE_ORDER: tuple[DeclarationStage, ...] = (
    DeclarationStage.INGESTED,
    DeclarationStage.ANNOTATED,
    DeclarationStage.FORMALIZED,
    DeclarationStage.CHECKED,
    DeclarationStage.APPROVED,
    DeclarationStage.PROVED,
)


class StepStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


def derive_stage(record: DeclarationRecord) -> DeclarationStage:
    """Read a declaration's stage back out of its own artifacts.

    Ordered most-advanced first. Nothing here consults run state, which is what lets a
    fresh process reconstruct progress from the store alone.

    ``PROVED`` requires human approval as well as a clean Lean verdict, deliberately. A
    definition with a real body compiles ``FULLY_VERIFIED`` the moment it is checked, and
    reading that alone as "done" would walk it past the review gate -- which is the one
    place a person decides whether the Lean says what the book says. Lean can tell us a
    construction is complete; it cannot tell us it is *faithful*.
    """
    approved = record.review.status is ReviewStatus.APPROVED
    if approved and record.has_lean and record.trust.status is TrustStatus.FULLY_VERIFIED:
        return DeclarationStage.PROVED
    if approved:
        return DeclarationStage.APPROVED
    if record.finding_ids or record.trust.status is not TrustStatus.UNKNOWN:
        return DeclarationStage.CHECKED
    if record.has_lean or record.proposal_id:
        return DeclarationStage.FORMALIZED
    if record.annotation is not None:
        return DeclarationStage.ANNOTATED
    return DeclarationStage.INGESTED


class RunEvent(Artifact):
    """One thing that happened, in order. The run timeline's backing data."""

    at: _dt.datetime = Field(default_factory=utc_now)
    kind: str = Field(description="stage_ok | stage_failed | gate | status | note")
    declaration_id: str | None = None
    stage: str | None = None
    message: str = ""
    run_id: str | None = Field(default=None, description="StageRun id, when one was recorded.")


class DeclarationState(Artifact):
    """Per-declaration bookkeeping for one run."""

    declaration_id: str
    stage: DeclarationStage = DeclarationStage.INGESTED
    status: StepStatus = StepStatus.OK
    attempts: int = Field(default=0, ge=0)
    last_stage_run_id: str | None = None
    last_context_package_id: str | None = None
    error: str | None = None
    error_kind: str | None = None
    blocked_reason: str | None = None


class PipelineRun(Artifact):
    """One invocation of the pipeline over a set of declarations."""

    id: str
    corpus: str
    status: RunStatus = RunStatus.QUEUED
    targets: list[str] = Field(default_factory=list)
    declarations: dict[str, DeclarationState] = Field(default_factory=dict)
    events: list[RunEvent] = Field(default_factory=list)
    stop_after: DeclarationStage | None = Field(
        default=None,
        description="Gate: the run halts rather than advancing past this stage.",
    )
    created_at: _dt.datetime = Field(default_factory=utc_now)
    updated_at: _dt.datetime = Field(default_factory=utc_now)

    def state_for(self, declaration_id: str) -> DeclarationState:
        if declaration_id not in self.declarations:
            self.declarations[declaration_id] = DeclarationState(declaration_id=declaration_id)
        return self.declarations[declaration_id]

    def record(self, event: RunEvent) -> None:
        # Reassigning rather than mutating in place: Artifact sets validate_assignment,
        # and an appended-to list would slip past validation entirely.
        self.events = [*self.events, event]
        self.updated_at = utc_now()

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for st in self.declarations.values():
            out[st.stage.value] = out.get(st.stage.value, 0) + 1
        return dict(sorted(out.items()))

    @property
    def failed(self) -> list[str]:
        return sorted(d for d, s in self.declarations.items() if s.status is StepStatus.FAILED)


class RunStore:
    """Persists :class:`PipelineRun` as one JSON file per run.

    Separate from :class:`~pipeline.artifacts.store.ArtifactStore` on purpose: artifacts are the
    product and are content-addressed and idempotent, while a run is an episode with a
    beginning and an end. Mixing them would make a re-run look like a changed artifact.
    """

    DIRNAME = "pipeline-runs"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory) / self.DIRNAME

    def path(self, run_id: str) -> Path:
        return self.directory / f"{run_id}.json"

    def save(self, run: PipelineRun) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        run.updated_at = utc_now()
        target = self.path(run.id)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, target)
        return target

    def load(self, run_id: str) -> PipelineRun:
        target = self.path(run_id)
        if not target.exists():
            raise FileNotFoundError(f"no pipeline run {run_id!r} at {target}")
        return PipelineRun.model_validate_json(target.read_text(encoding="utf-8"))

    def list_runs(self) -> list[PipelineRun]:
        if not self.directory.exists():
            return []
        runs = [
            PipelineRun.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self.directory.glob("*.json"))
        ]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

    def latest(self) -> PipelineRun | None:
        runs = self.list_runs()
        return runs[0] if runs else None
