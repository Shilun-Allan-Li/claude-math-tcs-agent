"""PipelineOrchestrator: the stage runner.

Every stage executes through exactly one path, and it is this one:

    load artifact
    -> build bounded context
    -> invoke worker
    -> validate output
    -> persist artifact
    -> update corpus graph
    -> update run state
    -> schedule eligible next stage

Steps 1-6 are the stage functions' own work and are already implemented and tested;
this class owns 7 and 8, and owns the guarantee that no other route into a stage exists.

The property that matters is what is *absent*: :meth:`step` takes a registry, a run, and
a declaration id. There is no conversation parameter, no transcript, no accumulated
history. Everything a worker learns about earlier stages arrives through a
:class:`ContextPackage` built by deterministic query against the corpus graph, which is
why :meth:`resume` can pick up a half-finished run in a process that has never spoken to
a model.

Failure is structured rather than fatal. A stage that raises is recorded against the
declaration with its error kind, the run continues with the other declarations, and the
failed one is left at the stage it reached -- so a re-run retries exactly it.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.models import Stage, StageRun
from pipeline.orchestrator.state import (
    STAGE_ORDER,
    DeclarationStage,
    PipelineRun,
    RunEvent,
    RunStatus,
    RunStore,
    StepStatus,
    derive_stage,
)
from pipeline.orchestrator.worker import WorkerResult, WorkerSpec, worker_for
from pipeline.artifacts.store import ArtifactStore

__all__ = ["PipelineOrchestrator", "StepResult", "PipelineError", "STAGE_FOR"]

#: Which worker advances a declaration out of a given stage.
STAGE_FOR: dict[DeclarationStage, Stage] = {
    DeclarationStage.INGESTED: Stage.ANNOTATE,
    DeclarationStage.ANNOTATED: Stage.FORMALIZE,
    DeclarationStage.FORMALIZED: Stage.CHECK,
    DeclarationStage.CHECKED: Stage.REVIEW,   # human gate; no worker
    DeclarationStage.APPROVED: Stage.PROVE,
}


class PipelineError(RuntimeError):
    pass


@dataclass
class StepResult:
    declaration_id: str
    stage: Stage
    status: StepStatus
    from_stage: DeclarationStage
    to_stage: DeclarationStage
    artifacts: list[Any] = field(default_factory=list)
    context_package_id: str | None = None
    stage_run_id: str | None = None
    wall_ms: int = 0
    error: str | None = None
    error_kind: str | None = None
    warnings: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is StepStatus.OK

    def as_dict(self) -> dict[str, Any]:
        return {
            "declaration_id": self.declaration_id,
            "stage": self.stage.value,
            "status": self.status.value,
            "transition": f"{self.from_stage.value} -> {self.to_stage.value}",
            "artifacts": len(self.artifacts),
            "context_package_id": self.context_package_id,
            "stage_run_id": self.stage_run_id,
            "wall_ms": self.wall_ms,
            "error": self.error,
            "error_kind": self.error_kind,
            "warnings": self.warnings,
            "detail": self.detail,
        }


class PipelineOrchestrator:
    """Drives declarations through the pipeline, one bounded step at a time."""

    def __init__(
        self,
        registry: CorpusRegistry,
        run: PipelineRun,
        run_store: RunStore,
        *,
        providers: dict[str, Any] | None = None,
        stage_options: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.registry = registry
        self.run = run
        self.run_store = run_store
        #: One provider per stage name ("annotate", "formalize", "prove"). Absent means
        #: the stage cannot run and is reported as blocked rather than crashing.
        self.providers = providers or {}
        #: Per-stage keyword arguments (Lean module, lean_root, checker providers, ...).
        self.stage_options = stage_options or {}

    # ------------------------------------------------------------------ lifecycle

    @classmethod
    def start(
        cls,
        registry: CorpusRegistry,
        *,
        run_id: str,
        targets: Sequence[str],
        stop_after: DeclarationStage | None = DeclarationStage.CHECKED,
        providers: dict[str, Any] | None = None,
        stage_options: dict[str, dict[str, Any]] | None = None,
    ) -> PipelineOrchestrator:
        run = PipelineRun(
            id=run_id,
            corpus=registry.store.corpus,
            status=RunStatus.QUEUED,
            targets=list(targets),
            stop_after=stop_after,
        )
        store = RunStore(registry.store.directory)
        orch = cls(registry, run, store, providers=providers, stage_options=stage_options)
        orch.sync_from_artifacts()
        run.record(RunEvent(kind="status", message=f"run {run_id} queued with {len(targets)} targets"))
        store.save(run)
        return orch

    @classmethod
    def resume(
        cls,
        data_dir: str | Path,
        corpus: str,
        run_id: str,
        *,
        providers: dict[str, Any] | None = None,
        stage_options: dict[str, dict[str, Any]] | None = None,
    ) -> PipelineOrchestrator:
        """Rebuild an orchestrator from disk alone.

        Nothing is carried in from the process that started the run: the registry is
        re-read from the artifact store, every declaration's stage is recomputed from its
        artifacts, and the run record supplies only the target list and the event history.
        """
        registry = CorpusRegistry.load(ArtifactStore(data_dir, corpus=corpus))
        store = RunStore(registry.store.directory)
        run = store.load(run_id)
        orch = cls(registry, run, store, providers=providers, stage_options=stage_options)
        orch.sync_from_artifacts()
        run.record(RunEvent(kind="status", message=f"resumed run {run_id} from persisted state"))
        store.save(run)
        return orch

    def sync_from_artifacts(self) -> None:
        """Recompute every target's stage from the artifact store.

        Called on start and on resume. Artifacts win over run bookkeeping, always.
        """
        for declaration_id in self.run.targets:
            record = self.registry.get(declaration_id)
            if record is None:
                continue
            state = self.run.state_for(declaration_id)
            state.stage = derive_stage(record)
            if state.status is StepStatus.BLOCKED:
                # The declaration exists now, so whatever blocked it has resolved.
                state.status = StepStatus.OK
                state.blocked_reason = None

    # ------------------------------------------------------------------ scheduling

    def next_stage(self, declaration_id: str) -> Stage | None:
        """The stage that would run next, or None if the declaration is done or gated."""
        state = self.run.state_for(declaration_id)
        if self.run.stop_after is not None:
            if STAGE_ORDER.index(state.stage) >= STAGE_ORDER.index(self.run.stop_after):
                return None
        return STAGE_FOR.get(state.stage)

    def eligible(self) -> list[tuple[str, Stage]]:
        """Every (declaration, stage) pair that could run right now.

        Order is dependency-first: the corpus graph's topological order, so a definition
        is formalized before the theorem stated in terms of it.
        """
        order = self.registry.graph.topological_order() or []
        rank = {node: i for i, node in enumerate(order)}
        pairs: list[tuple[str, Stage]] = []
        for declaration_id in self.run.targets:
            state = self.run.state_for(declaration_id)
            if state.status in (StepStatus.FAILED, StepStatus.BLOCKED):
                # Both are skipped for the rest of this pass. The difference is what
                # happens next time: sync_from_artifacts clears BLOCKED when the reason
                # for it has gone away, while FAILED needs a deliberate re-run.
                continue
            stage = self.next_stage(declaration_id)
            if stage is None or stage is Stage.REVIEW:
                continue
            pairs.append((declaration_id, stage))
        pairs.sort(key=lambda p: (rank.get(p[0], len(rank)), p[0]))
        return pairs

    # ------------------------------------------------------------------- execution

    def step(self, declaration_id: str, stage: Stage) -> StepResult:
        """Run exactly one stage for one declaration, through the canonical sequence."""
        state = self.run.state_for(declaration_id)
        from_stage = state.stage
        started = time.monotonic()

        # 1. load artifact -- authoritative, from the store, never from a caller.
        record = self.registry.get(declaration_id)
        if record is None:
            # Not necessarily an error: a definition the book states in running prose has
            # no identity until the annotator quotes it, so a target named ahead of its
            # own creation is *pending*, not broken. Blocked is retryable; failed is not.
            return self._block(
                declaration_id, stage, from_stage,
                f"no declaration {declaration_id!r} in the corpus yet "
                f"(prose-discovered items appear only after their section is annotated)",
            )

        spec: WorkerSpec = worker_for(stage)
        provider = self.providers.get(stage.value)
        if spec.requires_provider and provider is None:
            return self._block(
                declaration_id, stage, from_stage,
                f"no provider configured for stage {stage.value!r}",
            )

        options = dict(self.stage_options.get(stage.value, {}))

        # 2. build bounded context -- a deterministic graph query, recorded as an artifact.
        context_id: str | None = None
        if spec.build_context is not None:
            try:
                package = spec.build_context(self.registry, declaration_id)
                context_id = package.id
            except Exception as exc:  # noqa: BLE001 - a context failure is a stage failure
                return self._fail(
                    declaration_id, stage, from_stage,
                    f"context build failed: {type(exc).__name__}: {exc}", "fatal",
                    int((time.monotonic() - started) * 1000),
                )

        # 3-6. invoke worker; the adapter validates, persists, and updates the graph.
        try:
            result: WorkerResult = spec.execute(
                self.registry, declaration_id, provider=provider, **options
            )
        except Exception as exc:  # noqa: BLE001 - structured failure, never a crashed run
            kind = "validation" if type(exc).__name__.endswith("Error") else "fatal"
            return self._fail(
                declaration_id, stage, from_stage,
                f"{type(exc).__name__}: {exc}", kind,
                int((time.monotonic() - started) * 1000),
            )

        # 4b. validate output against the declared schema. The stage functions construct
        # typed artifacts already; this asserts the worker returned what it promised
        # rather than trusting the adapter.
        for artifact in result.artifacts:
            if not isinstance(artifact, spec.output_model):
                return self._fail(
                    declaration_id, stage, from_stage,
                    f"{spec.name} returned {type(artifact).__name__}, "
                    f"expected {spec.output_model.__name__}",
                    "validation", int((time.monotonic() - started) * 1000),
                )

        # 6b. refresh the denormalised graph projection and re-read the store, so the
        # next step sees this one's edges.
        self.registry.reload()
        self.registry.refresh_dependency_facets()

        # 7. update run state.
        record = self.registry.get(declaration_id)
        to_stage = derive_stage(record) if record is not None else spec.produces
        state.stage = to_stage
        state.status = StepStatus.OK
        state.attempts += 1
        state.error = None
        state.error_kind = None
        state.last_stage_run_id = result.stage_run_id
        # The package the worker actually used wins over the one the orchestrator built
        # for the pre-flight: for a stage whose unit of work is wider than a declaration
        # (annotation runs per section) they are not the same package.
        state.last_context_package_id = (
            result.context.id if result.context is not None else context_id
        )

        wall = int((time.monotonic() - started) * 1000)
        self.run.record(RunEvent(
            kind="stage_ok", declaration_id=declaration_id, stage=stage.value,
            run_id=result.stage_run_id,
            message=f"{from_stage.value} -> {to_stage.value}"
                    + (f"  ({result.detail})" if result.detail else ""),
        ))
        self.run_store.save(self.run)

        return StepResult(
            declaration_id=declaration_id, stage=stage, status=StepStatus.OK,
            from_stage=from_stage, to_stage=to_stage,
            artifacts=result.artifacts,
            context_package_id=state.last_context_package_id,
            stage_run_id=result.stage_run_id, wall_ms=wall,
            warnings=list(result.warnings), detail=dict(result.detail),
        )

    def advance(self, declaration_id: str, *, max_steps: int = 8) -> list[StepResult]:
        """Run stages for one declaration until it is gated, done, or fails."""
        results: list[StepResult] = []
        for _ in range(max_steps):
            stage = self.next_stage(declaration_id)
            if stage is None or stage is Stage.REVIEW:
                break
            result = self.step(declaration_id, stage)
            results.append(result)
            if not result.ok:
                break
        return results

    def run_until_gate(self, *, max_steps: int = 64) -> list[StepResult]:
        """Drive every target as far as the run's gate allows.

        Re-derives the eligible set after each step rather than planning the whole run
        up front: a step can change what else is eligible (a formalized definition
        unblocks the theorem that cites it), and a plan computed in advance would be
        wrong the moment it was executed.
        """
        self._set_status(RunStatus.RUNNING)
        results: list[StepResult] = []
        for _ in range(max_steps):
            pending = self.eligible()
            if not pending:
                break
            declaration_id, stage = pending[0]
            results.append(self.step(declaration_id, stage))
        self._settle()
        return results

    # -------------------------------------------------------------------- helpers

    def _set_status(self, status: RunStatus, message: str = "") -> None:
        if self.run.status is not status:
            self.run.status = status
            self.run.record(RunEvent(kind="status", message=message or status.value))
            self.run_store.save(self.run)

    def _settle(self) -> None:
        """Decide the run's status from where its declarations actually are."""
        states = [self.run.state_for(d) for d in self.run.targets]
        if not states:
            self._set_status(RunStatus.QUEUED)
            return
        blocked = [s for s in states if s.status is StepStatus.BLOCKED]
        if blocked and not any(s.status is StepStatus.FAILED for s in states):
            self._set_status(
                RunStatus.QUEUED,
                f"{len(blocked)} target(s) not yet addressable; re-run or resume to retry",
            )
            return
        if any(s.status is StepStatus.FAILED for s in states):
            failed = ", ".join(self.run.failed)
            self._set_status(RunStatus.FAILED, f"declarations failed: {failed}")
            return
        stages = {s.stage for s in states}
        if stages == {DeclarationStage.PROVED}:
            self._set_status(RunStatus.VERIFIED, "every target is proved")
            return
        if any(s.stage is DeclarationStage.APPROVED for s in states):
            self._set_status(RunStatus.PROVING, "approved declarations are ready to prove")
            return
        if all(
            STAGE_ORDER.index(s.stage) >= STAGE_ORDER.index(DeclarationStage.CHECKED)
            for s in states
        ):
            self._set_status(
                RunStatus.WAITING_FOR_HUMAN_REVIEW,
                "all targets checked; the review gate is closed until a human decides",
            )
            self.run.record(RunEvent(
                kind="gate",
                message="WAITING_FOR_HUMAN_REVIEW — no declaration advances without a human decision",
            ))
            self.run_store.save(self.run)
            return
        self._set_status(RunStatus.RUNNING)

    def _fail(
        self, declaration_id: str, stage: Stage, from_stage: DeclarationStage,
        error: str, kind: str, wall: int,
    ) -> StepResult:
        state = self.run.state_for(declaration_id)
        state.status = StepStatus.FAILED
        state.attempts += 1
        state.error = error
        state.error_kind = kind
        self.run.record(RunEvent(
            kind="stage_failed", declaration_id=declaration_id, stage=stage.value,
            message=f"[{kind}] {error}",
        ))
        self.registry.store.append("runs", StageRun(
            id=f"run-{stage.value}-{declaration_id}-{int(time.time() * 1000) % 10**9}",
            stage=stage, target_id=declaration_id, status="failed",
            error=error, error_kind=kind, wall_ms=wall,
        ))
        self.run_store.save(self.run)
        return StepResult(
            declaration_id=declaration_id, stage=stage, status=StepStatus.FAILED,
            from_stage=from_stage, to_stage=from_stage,
            error=error, error_kind=kind, wall_ms=wall,
        )

    def _block(
        self, declaration_id: str, stage: Stage, from_stage: DeclarationStage, reason: str
    ) -> StepResult:
        state = self.run.state_for(declaration_id)
        state.status = StepStatus.BLOCKED
        state.blocked_reason = reason
        self.run.record(RunEvent(
            kind="stage_failed", declaration_id=declaration_id, stage=stage.value,
            message=f"[blocked] {reason}",
        ))
        self.run_store.save(self.run)
        return StepResult(
            declaration_id=declaration_id, stage=stage, status=StepStatus.BLOCKED,
            from_stage=from_stage, to_stage=from_stage, error=reason, error_kind="blocked",
        )

    # ---------------------------------------------------------------------- views

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run.id,
            "corpus": self.run.corpus,
            "status": self.run.status.value,
            "targets": len(self.run.targets),
            "stop_after": self.run.stop_after.value if self.run.stop_after else None,
            "by_stage": self.run.counts(),
            "failed": self.run.failed,
            "events": len(self.run.events),
            "updated_at": self.run.updated_at.isoformat(),
        }
