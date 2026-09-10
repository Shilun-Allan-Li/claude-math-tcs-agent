"""Pipeline orchestration: stage running, run state, and the worker contract.

Nothing here talks to a model directly. The orchestrator drives typed workers whose
prompts are implementation details, and every stage boundary is an artifact on disk
rather than a message in a conversation.
"""

from pipeline.orchestrator.runner import (
    STAGE_FOR,
    PipelineError,
    PipelineOrchestrator,
    StepResult,
)
from pipeline.orchestrator.state import (
    STAGE_ORDER,
    DeclarationStage,
    DeclarationState,
    PipelineRun,
    RunEvent,
    RunStatus,
    RunStore,
    StepStatus,
    derive_stage,
)
from pipeline.orchestrator.worker import WORKERS, WorkerResult, WorkerSpec, describe_workers, worker_for

__all__ = [
    "PipelineOrchestrator", "StepResult", "PipelineError", "STAGE_FOR",
    "PipelineRun", "RunStore", "RunStatus", "RunEvent", "DeclarationState",
    "DeclarationStage", "StepStatus", "derive_stage", "STAGE_ORDER",
    "WorkerSpec", "WorkerResult", "WORKERS", "worker_for", "describe_workers",
]
