"""DeclarationRecord: one mathematical item, from textbook source to verified Lean.

This is the artifact that makes rule 2 real. Every other model in this package is a facet
of it, and the record keeps them side by side so that no stage has to reconstruct what an
earlier stage knew.

Rule 3 is visible in the shape: ``source`` and ``lean`` are separate sub-objects that
coexist. The Lean form never overwrites the source form, and ``mappings`` records exactly
how the two differ.
"""

from __future__ import annotations

from pydantic import Field

from pipeline.artifacts.models.annotation import AnnotatedDeclaration
from pipeline.artifacts.models.base import Artifact
from pipeline.artifacts.models.enums import (
    OBJECT_KINDS,
    CompileStatus,
    LeanDeclarationKind,
    SorryKind,
    SourceItemKind,
    TrustStatus,
)
from pipeline.artifacts.models.mapping import SourceLeanMapping
from pipeline.artifacts.models.review import ReviewState
from pipeline.artifacts.models.source import SourceItem

__all__ = ["DeclarationRecord", "LeanFacet", "TrustFacet", "DependencyFacet"]


class LeanFacet(Artifact):
    """The Lean side. Every field here is produced or confirmed by Lean tooling."""

    name: str | None = None
    declaration_kind: LeanDeclarationKind | None = None
    statement: str | None = None
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    module: str | None = None
    sorry_kind: SorryKind = SorryKind.NONE
    proof: str | None = Field(
        default=None,
        description=(
            "The accepted proof body, once one has been verified. Kept on the record rather "
            "than folded into the FormalizationProposal, because the proposal is what stage 2 "
            "produced and must stay comparable to what a reviewer approved."
        ),
    )


class TrustFacet(Artifact):
    """Whether this declaration may be relied upon. Rule 5: Lean decides, not an LLM."""

    compile_status: CompileStatus = CompileStatus.UNKNOWN
    direct_sorry: bool | None = None
    transitive_sorry: bool | None = None
    unfinished_construction: bool | None = None
    axioms: list[str] = Field(default_factory=list)
    status: TrustStatus = TrustStatus.UNKNOWN
    blocked_by: list[str] = Field(
        default_factory=list,
        description="Declaration ids whose untrusted state propagates here. Scheduler input.",
    )
    checked_at_fingerprint: str | None = Field(
        default=None, description="Lean source fingerprint the verdict was computed from."
    )


class DependencyFacet(Artifact):
    """Dependency views, kept denormalised on the record for fast rendering.

    The corpus graph is authoritative; these are a materialised projection refreshed by
    ``CorpusRegistry.refresh_dependency_facets``.
    """

    informal: list[str] = Field(default_factory=list)
    lean_local: list[str] = Field(default_factory=list)
    mathlib: list[str] = Field(default_factory=list)
    reverse: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(
        default_factory=list, description="Raw source references that resolved to no declaration."
    )


class DeclarationRecord(Artifact):
    """The aggregate. ``id`` is source-derived and never changes.

    Derived values (:attr:`is_theorem_like`, :attr:`is_foundational`,
    :attr:`reverse_dependency_count`) are plain properties, deliberately **not**
    serialized fields. Storing a derived value is how it goes stale; the view layer
    computes them when rendering, and the artifact on disk stays canonical.
    """

    id: str
    kind: SourceItemKind
    source: SourceItem
    annotation: AnnotatedDeclaration | None = None
    lean: LeanFacet = Field(default_factory=LeanFacet)
    mappings: list[SourceLeanMapping] = Field(default_factory=list)
    dependencies: DependencyFacet = Field(default_factory=DependencyFacet)
    trust: TrustFacet = Field(default_factory=TrustFacet)
    review: ReviewState

    proposal_id: str | None = Field(default=None, description="Current FormalizationProposal.")
    finding_ids: list[str] = Field(default_factory=list)
    proof_attempt_ids: list[str] = Field(default_factory=list)

    @property
    def is_theorem_like(self) -> bool:
        from pipeline.artifacts.models.enums import THEOREM_LIKE

        return self.kind in THEOREM_LIKE

    @property
    def is_foundational(self) -> bool:
        """A definition, or anything other declarations are stated in terms of.

        Report 03 §4: four of the six critical issues in chapters 1-3 are definitions.
        Foundational status is the largest single input to the review risk score.
        """
        if self.kind in (SourceItemKind.DEFINITION, SourceItemKind.NOTATION, SourceItemKind.CONSTRUCTION):
            return True
        return self.lean.declaration_kind in OBJECT_KINDS if self.lean.declaration_kind else False

    @property
    def reverse_dependency_count(self) -> int:
        return len(self.dependencies.reverse)

    @property
    def has_lean(self) -> bool:
        return self.lean.name is not None

    @property
    def is_trusted(self) -> bool:
        return self.trust.status is TrustStatus.FULLY_VERIFIED

    def fingerprint_inputs(self) -> tuple[str | None, ...]:
        """The content whose change should invalidate a human review decision."""
        return (self.source.fingerprint, self.lean.statement, self.lean.name)
