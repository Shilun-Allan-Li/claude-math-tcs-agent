"""Worker specifications: the five separable concerns of one agent-backed stage.

A stage is not a prompt. It is a typed function with a persistence contract, and the
prompt is one replaceable part of it. Naming the parts is the point of this module:

1. **worker interface** -- ``WorkerSpec.name`` / ``stage`` / ``input_model`` /
   ``output_model``: what goes in, what comes out, both typed.
2. **prompt template** -- ``prompt``: a ``(stage, name)`` pair resolved against the
   version-controlled Markdown under ``prompts/``. Never inline, never accumulated.
3. **context builder** -- ``build_context``: a deterministic query against the corpus
   graph producing a :class:`ContextPackage`. This is the only channel by which a worker
   learns what earlier stages produced.
4. **output schema** -- ``output_model``: a pydantic artifact with ``extra="forbid"``.
   A response that does not validate is a failed run, not a warning.
5. **execution adapter** -- ``execute``: binds a provider to the above and returns the
   persisted artifact.

The executable workers live in :mod:`pipeline.agents`; this module is the thin table the
orchestrator dispatches through, kept so the stage -> worker mapping has one home and can
be printed. Concerns 1-5 above are properties of the agent classes, not of this table.

The load-bearing property: every ``execute`` below takes a registry and a declaration id
and nothing else. No stage receives, or can receive, a transcript of an earlier stage.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.artifacts.models import (
    AnnotatedDeclaration,
    CheckerFinding,
    ContextPackage,
    FormalizationProposal,
    ProofAttempt,
    SourceItem,
    Stage,
)
from pipeline.orchestrator.state import DeclarationStage

__all__ = ["WorkerSpec", "WorkerResult", "WORKERS", "worker_for", "describe_workers"]


@dataclass
class WorkerResult:
    """What one worker invocation produced, before the orchestrator records it."""

    artifacts: list[Any]
    context: ContextPackage | None = None
    stage_run_id: str | None = None
    warnings: list[str] = None  # type: ignore[assignment]
    detail: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []
        if self.detail is None:
            self.detail = {}


@dataclass(frozen=True)
class WorkerSpec:
    """One stage, with its five concerns held apart and separately replaceable."""

    name: str
    stage: Stage
    produces: DeclarationStage
    input_model: tuple[type, ...]
    output_model: type
    prompt: tuple[str, str] | None
    build_context: Callable[..., ContextPackage] | None
    execute: Callable[..., WorkerResult]
    requires_provider: bool = True
    description: str = ""


# ------------------------------------------------------------------ the registry


def _spec_from_agent(agent) -> WorkerSpec:
    """Project an :class:`~pipeline.agents.Agent` onto the orchestrator's table."""
    from pipeline.agents.base import Agent
    from pipeline.orchestrator.state import DeclarationStage

    produces = {
        Stage.ANNOTATE: DeclarationStage.ANNOTATED,
        Stage.FORMALIZE: DeclarationStage.FORMALIZED,
        Stage.CHECK: DeclarationStage.CHECKED,
        Stage.PROVE: DeclarationStage.PROVED,
    }[agent.stage]

    def execute(registry, declaration_id, **kw) -> WorkerResult:
        result = agent.run(registry, declaration_id, **kw)
        return WorkerResult(
            artifacts=result.artifacts, context=result.context,
            stage_run_id=result.stage_run_id, warnings=list(result.warnings),
            detail=dict(result.detail),
        )

    def build_context(registry, declaration_id, **kw):
        return agent.build_context(registry, declaration_id)

    has_ctx = type(agent).build_context is not Agent.build_context
    return WorkerSpec(
        name=agent.name, stage=agent.stage, produces=produces,
        input_model=agent.input_model, output_model=agent.output_model,
        prompt=agent.prompt_ref,
        build_context=build_context if has_ctx else None,
        execute=execute,
        requires_provider=agent.requires_provider,
        description=agent.description,
    )


def _build_registry() -> dict[Stage, WorkerSpec]:
    from pipeline.agents import AGENTS

    return {stage: _spec_from_agent(agent) for stage, agent in AGENTS.items()}


WORKERS: dict[Stage, WorkerSpec] = _build_registry()


def worker_for(stage: Stage) -> WorkerSpec:
    if stage not in WORKERS:
        raise KeyError(f"no worker for stage {stage.value!r}")
    return WORKERS[stage]


def describe_workers() -> list[dict[str, Any]]:
    """The worker table, for ``pipeline workers`` and for the docs."""
    out = []
    for spec in WORKERS.values():
        out.append({
            "worker": spec.name,
            "stage": spec.stage.value,
            "produces": spec.produces.value,
            "input": [m.__name__ for m in spec.input_model],
            "output": spec.output_model.__name__,
            "prompt": "/".join(spec.prompt) if spec.prompt else None,
            "context_builder": "agent.build_context" if spec.build_context else None,
            "requires_provider": spec.requires_provider,
            "description": spec.description,
        })
    return out
