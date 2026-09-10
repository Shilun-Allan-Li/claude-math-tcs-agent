"""Stage 2 artifact: a proposed Lean declaration.

Rule 6: this stage produces *statements*, not proofs. Report 02 §A.5 records what happens
without a machine-checkable contract -- commit ``9468218`` shipped 29 proved theorems
under a message asserting "Every proof body is `sorry`", and nothing checked.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from pipeline.artifacts.models.base import Artifact, Provenance
from pipeline.artifacts.models.enums import (
    OBJECT_KINDS,
    LeanDeclarationKind,
    ProposalStatus,
    SorryKind,
)
from pipeline.artifacts.models.mapping import SourceLeanMapping

__all__ = ["FormalizationProposal", "DesignWarning", "MathlibRelation"]


class DesignWarning(Artifact):
    """A hazard the formalizer noticed while writing the statement.

    The typed successor to the 508 free-text ``warning`` markers in the summer's Lean
    docstrings (report 02 §B3). The generator was not blind -- it was unheard.
    """

    code: str = Field(description="Short stable code, e.g. 'carrier-type-change'.")
    message: str
    blocks: bool = Field(
        default=False, description="True when the warning should prevent auto-approval."
    )


class MathlibRelation(Artifact):
    name: str
    relation: str = Field(description="alias | stronger | weaker | related")
    verified: bool = False


class FormalizationProposal(Artifact):
    """A proposed Lean declaration for one annotated declaration."""

    id: str = Field(description="'<declaration_id>/f<N>' -- stable per declaration.")
    declaration_id: str
    status: ProposalStatus

    # --- the Lean surface ---
    lean_name: str | None = Field(default=None, description="Fully qualified, e.g. 'SimpleGraph.foo'.")
    namespace: str | None = None
    declaration_kind: LeanDeclarationKind | None = None
    imports: list[str] = Field(default_factory=list, description="Precise Mathlib modules.")
    variables: list[str] = Field(
        default_factory=list, description="Section variables, e.g. '{V : Type*}'."
    )
    typeclasses: list[str] = Field(default_factory=list, description="e.g. '[Fintype V]'.")
    statement: str | None = Field(
        default=None, description="The full Lean declaration text, body included."
    )
    sorry_kind: SorryKind = Field(
        default=SorryKind.NONE,
        description=(
            "Which kind of `sorry` the body carries. OBJECT_PENDING is the one that "
            "matters: report 02 §B4 -- 13 opaque `def := sorry` constants made 18+ "
            "theorems vacuous rather than merely unproved."
        ),
    )

    # --- rule 3 bookkeeping ---
    mappings: list[SourceLeanMapping] = Field(default_factory=list)
    hypotheses_added: list[str] = Field(
        default_factory=list,
        description="Hypotheses in the Lean statement with no source counterpart, each justified.",
    )
    hypotheses_dropped: list[str] = Field(
        default_factory=list,
        description="Source hypotheses absent from the Lean statement. Any entry is high risk.",
    )
    design_warnings: list[DesignWarning] = Field(default_factory=list)
    mathlib_candidates: list[MathlibRelation] = Field(default_factory=list)

    needs_design_reason: str | None = Field(
        default=None, description="Required when status is NEEDS_DESIGN."
    )
    failure_reason: str | None = Field(default=None, description="Required when status is FAILED.")

    annotation_fingerprint: str = Field(description="Fingerprint of the AnnotatedDeclaration.")
    provenance: Provenance

    @model_validator(mode="after")
    def _status_consistency(self) -> FormalizationProposal:
        if self.status is ProposalStatus.PROPOSED:
            missing = [f for f in ("lean_name", "declaration_kind", "statement") if not getattr(self, f)]
            if missing:
                raise ValueError(f"PROPOSED proposal is missing {', '.join(missing)}")
        if self.status is ProposalStatus.NEEDS_DESIGN and not self.needs_design_reason:
            raise ValueError("NEEDS_DESIGN requires needs_design_reason")
        if self.status is ProposalStatus.FAILED and not self.failure_reason:
            raise ValueError("FAILED requires failure_reason")
        return self

    @model_validator(mode="after")
    def _sorry_kind_matches_declaration_kind(self) -> FormalizationProposal:
        """OBJECT_PENDING is only meaningful for object-introducing declarations.

        Enforcing this is the whole point of splitting `sorry` kinds: a `theorem` whose
        body is `sorry` is unproved, while a `def` whose body is `sorry` is *opaque*, and
        the model must not let the two be recorded interchangeably.
        """
        kind = self.declaration_kind
        if kind is None:
            return self
        if self.sorry_kind is SorryKind.OBJECT_PENDING and kind not in OBJECT_KINDS:
            raise ValueError(
                f"sorry_kind=object_pending is invalid for declaration_kind={kind.value}; "
                "an unfinished proof is proof_pending"
            )
        if self.sorry_kind is SorryKind.PROOF_PENDING and kind in OBJECT_KINDS:
            raise ValueError(
                f"sorry_kind=proof_pending is invalid for declaration_kind={kind.value}; "
                "an unfinished object is object_pending"
            )
        return self
