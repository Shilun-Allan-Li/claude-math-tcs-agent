"""The four executable agents.

Each binds a prompt file, a context builder and a stage implementation into one typed
worker. The stage implementations in :mod:`pipeline.stages` are unchanged and remain the
place the contracts are enforced; these classes are the uniform surface the orchestrator
drives them through, and the reason no stage is reachable except through that surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.agents.base import Agent, AgentResult
from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.models import (
    AnnotatedDeclaration,
    CheckerFinding,
    ContextPackage,
    FormalizationProposal,
    ProofAttempt,
    SourceItem,
    Stage,
)
from pipeline.providers import LLMProvider

__all__ = ["Annotator", "Formalizer", "CheckerOrchestrator", "ProofWorker", "AGENTS"]


class Annotator(Agent):
    """SourceItem + AnnotationContext -> AnnotatedDeclaration."""

    name = "annotator"
    stage = Stage.ANNOTATE
    prompt_ref = ("annotate", "chapter")
    input_model = (SourceItem, ContextPackage)
    output_model = AnnotatedDeclaration
    description = "reads one source division and produces the annotated declaration IR"

    def build_context(self, registry: CorpusRegistry, target_id: str) -> ContextPackage | None:
        from pipeline.corpus.config import load_corpus
        from pipeline.stages.annotate import split_sections
        from pipeline.context.builders import build_annotation_context

        record = registry.require(target_id)
        chapter, section = record.source.chapter, record.source.section or "0"
        division = load_corpus().chapter(chapter)
        markdown = division.markdown.read_text(encoding="utf-8")
        text = next((t for n, _x, t in split_sections(markdown) if n == section), markdown)
        items = [
            r.source for r in registry.declarations_in_chapter(chapter)
            if (r.source.section or "0") == section
        ]
        return build_annotation_context(
            registry, chapter, chapter_markdown=text,
            chapter_title=division.title, source_items=items,
        )

    def execute(self, registry, target_id, *, provider=None, model=None, **kw) -> AgentResult:
        from pipeline.stages.annotate import annotate_chapter

        record = registry.require(target_id)
        section = record.source.section
        # The unit of work is a section, not a declaration: a definition stated in running
        # prose has no identity until the annotator quotes it, so it cannot be addressed
        # before the section it lives in has been read.
        out = annotate_chapter(
            registry, record.source.chapter, provider=provider, model=model,
            sections=[section] if section else None,
        )
        return AgentResult(
            agent=self.name, stage=self.stage, target_id=target_id,
            artifacts=list(out.annotations),
            context=out.context_packages[0] if out.context_packages else None,
            stage_run_id=out.runs[-1].id if out.runs else None,
            warnings=list(out.warnings),
            detail={"section": section, "annotated": len(out.annotations)},
        )


class Formalizer(Agent):
    """AnnotatedDeclaration + FormalizationContext -> FormalizationProposal."""

    name = "formalizer"
    stage = Stage.FORMALIZE
    prompt_ref = ("formalize", "declaration")
    input_model = (AnnotatedDeclaration, ContextPackage)
    output_model = FormalizationProposal
    description = "proposes a Lean statement; rule 6 forbids it from proving anything"

    def build_context(self, registry: CorpusRegistry, target_id: str) -> ContextPackage:
        from pipeline.context.builders import build_formalization_context

        return build_formalization_context(registry, target_id)

    def execute(self, registry, target_id, *, provider=None, model=None, **kw) -> AgentResult:
        from pipeline.stages.formalize import formalize_declaration

        out = formalize_declaration(registry, target_id, provider=provider, model=model)
        return AgentResult(
            agent=self.name, stage=self.stage, target_id=target_id,
            artifacts=[out.proposal], context=out.context,
            stage_run_id=out.run.id, warnings=list(out.warnings),
            detail={"status": out.proposal.status.value, "lean_name": out.proposal.lean_name},
        )


class CheckerOrchestrator(Agent):
    """SourceItem + AnnotatedDeclaration + FormalizationProposal -> CheckerFinding[].

    Four checkers, not one prompt: Lean integrity is deterministic and consults no model
    at all, and the other three each have their own prompt file. ``prompt_ref`` is
    therefore ``None`` — a single prompt reference here would be a lie about the shape.
    """

    name = "checker_orchestrator"
    stage = Stage.CHECK
    prompt_ref = None
    input_model = (SourceItem, AnnotatedDeclaration, FormalizationProposal)
    output_model = CheckerFinding
    requires_provider = False
    description = "runs the four checkers and collects their findings into one schema"

    def execute(
        self, registry, target_id, *, provider=None, module: str | None = None,
        lean_root: str | Path | None = None, checker_providers: dict | None = None, **kw,
    ) -> AgentResult:
        from pipeline.review import recompute_review_states
        from pipeline.checkers.orchestrator import run_checkers

        report = run_checkers(
            registry, module=module, declaration_ids=[target_id],
            lean_root=lean_root, **(checker_providers or {}),
        )
        findings = report.for_declaration(target_id)
        # Checking is not finished until the review queue reflects it: the human gate is
        # only meaningful if risk scores are on the record when it closes.
        registry.reload()
        recompute_review_states(registry)
        return AgentResult(
            agent=self.name, stage=self.stage, target_id=target_id,
            artifacts=list(findings), stage_run_id=report.runs[-1].id if report.runs else None,
            warnings=list(report.warnings),
            detail={
                "findings": len(findings),
                "blocking": sum(1 for f in findings if f.blocks_progression),
                "requires_human": sum(1 for f in findings if f.requires_human),
            },
        )


class ProofWorker(Agent):
    """ApprovedDeclaration + ProofContext -> ProofAttempt."""

    name = "proof_worker"
    stage = Stage.PROVE
    prompt_ref = ("prove", "declaration")
    input_model = (FormalizationProposal, ContextPackage)
    output_model = ProofAttempt
    description = "proves an approved statement; rule 7 forbids it from changing one"

    def build_context(self, registry: CorpusRegistry, target_id: str) -> ContextPackage:
        from pipeline.context.builders import build_proof_context

        return build_proof_context(registry, target_id)

    def execute(
        self, registry, target_id, *, provider=None, model=None,
        lean_root: str | Path | None = None, max_attempts: int = 3,
        require_approval: bool = True, **kw,
    ) -> AgentResult:
        from pipeline.stages.prove import prove_declaration

        out = prove_declaration(
            registry, target_id, provider=provider, model=model, lean_root=lean_root,
            max_attempts=max_attempts, require_approval=require_approval,
        )
        return AgentResult(
            agent=self.name, stage=self.stage, target_id=target_id,
            artifacts=list(out.attempts), context=out.context,
            stage_run_id=out.runs[-1].id if out.runs else None,
            detail={"outcome": out.outcome.value, "attempts": len(out.attempts)},
        )


#: The agent registry. One instance per stage; the orchestrator dispatches through this.
AGENTS: dict[Stage, Agent] = {
    Stage.ANNOTATE: Annotator(),
    Stage.FORMALIZE: Formalizer(),
    Stage.CHECK: CheckerOrchestrator(),
    Stage.PROVE: ProofWorker(),
}
