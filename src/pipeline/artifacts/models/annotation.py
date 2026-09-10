"""Stage 1 artifact: the Annotated Declaration IR.

Every field below is justified by a downstream task observed in the summer corpus
(report 01 §F). Fields that were proposed and rejected are recorded in
``files/reports/01-annotation-system-review.md`` §F.2 rather than carried here.

The human-readable annotated Markdown is *not* replaced by this; it remains the artifact
a person reads. This is the sidecar that makes the same content addressable.
"""

from __future__ import annotations

from pydantic import Field

from pipeline.artifacts.models.base import Artifact, Provenance
from pipeline.artifacts.models.enums import SourceItemKind

__all__ = [
    "AnnotatedDeclaration",
    "InformalDependency",
    "MathlibCandidate",
    "ProofStep",
    "OpenQuestion",
]


class InformalDependency(Artifact):
    """A dependency the *book* asserts, before any Lean exists.

    Report 01 §B6: the summer recorded these in prose only -- 176 of 226 declarations were
    cited by name in another declaration's docstring and by nothing else, while 224 of 226
    had zero Lean-code references. The informal graph and the formal graph never met.
    """

    target_id: str | None = Field(
        default=None, description="Declaration id, when the reference resolves."
    )
    raw_reference: str = Field(description="What the book wrote, e.g. 'theorem 2.3'.")
    role: str = Field(
        default="uses",
        description="uses | generalises | specialises | cited-by-book | deferred-to",
    )
    resolved: bool = Field(
        default=False, description="False when the reference could not be resolved to an id."
    )


class ProofStep(Artifact):
    """One step of the book's printed proof, in the book's own terms."""

    index: int = Field(ge=1)
    text: str
    uses: list[str] = Field(
        default_factory=list, description="Declaration ids or raw references this step invokes."
    )


class MathlibCandidate(Artifact):
    """A Mathlib name the annotator believes is relevant.

    ``status`` carries the single highest-signal token in the summer corpus: 446 instances
    of ``MISSING -- must be built`` across ten chapters. ``verified`` records whether the
    name was actually checked; report 02 §B7 measured the cost of not checking -- 12
    declarations written, proved, then archived as exact Mathlib duplicates.
    """

    name: str
    status: str = Field(default="uncertain", description="exists | missing | uncertain")
    note: str | None = None
    verified: bool = Field(
        default=False, description="True only if the identifier was mechanically confirmed."
    )


class OpenQuestion(Artifact):
    """Something the annotator could not settle and a human may need to."""

    question: str
    blocks_formalization: bool = False


class AnnotatedDeclaration(Artifact):
    """Machine-readable annotation for exactly one source item."""

    declaration_id: str
    chapter_id: str
    kind: SourceItemKind

    # --- what the book states, carried forward rather than re-derived ---
    stated_hypotheses: list[str] = Field(
        default_factory=list,
        description=(
            "Every hypothesis the book states, including ones stated once at the top of a "
            "section and inherited silently. Report 01 §D1: five theorems in the summer "
            "corpus are FALSE as formalized because a prose hypothesis had no field to "
            "travel in. This field carries a mandatory human gate."
        ),
    )
    conclusion: str | None = Field(
        default=None, description="The book's conclusion, restated compactly."
    )

    # --- retrieval and routing ---
    concepts: list[str] = Field(
        default_factory=list, description="Closed-vocabulary concept tags used for retrieval."
    )
    terminology: list[str] = Field(
        default_factory=list, description="Terms the book introduces or relies on here."
    )

    # --- dependencies ---
    informal_dependencies: list[InformalDependency] = Field(default_factory=list)

    # --- proof material (never Lean tactics) ---
    proof_strategy: str | None = Field(
        default=None, description="One- to three-sentence summary of the book's argument."
    )
    proof_steps: list[ProofStep] = Field(default_factory=list)

    # --- formalization guidance ---
    formalization_hints: list[str] = Field(
        default_factory=list,
        description="Representation hazards. The annotation's strongest observed output.",
    )
    mathlib_candidates: list[MathlibCandidate] = Field(default_factory=list)
    local_definition_hints: list[str] = Field(
        default_factory=list,
        description="Declaration ids of prior local definitions this statement needs.",
    )
    figure_dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "Figures the argument relies on. Stage 0 drops figures by design (204 sites); "
            "recording the dependency lets a reviewer see when a proof reasons from a "
            "picture that is not in the corpus."
        ),
    )

    questions: list[OpenQuestion] = Field(default_factory=list)

    # --- routing signal, computed once and reused ---
    difficulty: int | None = Field(
        default=None, ge=0, le=100, description="Raw difficulty grade, 0-100."
    )
    route: str | None = Field(default=None, description="inline | ladder | orchestrator | skip")

    source_fingerprint: str = Field(
        description="Fingerprint of the SourceItem this annotates; detects staleness."
    )
    provenance: Provenance

    @property
    def has_blocking_question(self) -> bool:
        return any(q.blocks_formalization for q in self.questions)
