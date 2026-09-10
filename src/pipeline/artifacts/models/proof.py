"""ProofAttempt: one bounded attempt at closing a proof obligation.

These traces are the training data for the eventual prover agent, so they are recorded
even when they fail -- especially when they fail. Report 04 §G specifies the fields; the
summer recorded none of them, which is why the one instrumented session survives only as
a hand-written report.

Rule 7 is enforced structurally: ``approved_statement_fingerprint`` pins what the worker
was given, and ``STATEMENT_REVIEW_REQUIRED`` is a first-class outcome rather than an
excuse to edit the theorem.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from pipeline.artifacts.models.base import Artifact, Provenance
from pipeline.artifacts.models.enums import HelperOrigin, ProofOutcome

__all__ = ["ProofAttempt", "RetrievedDeclaration", "LeanDiagnostic", "ProposedHelper"]


class RetrievedDeclaration(Artifact):
    """Something the context builder supplied, and whether the worker used it.

    ``used`` is how the value of retrieval becomes measurable: the summer's one cached
    Mathlib survey cost 86,999 tokens and nothing recorded which entries earned it.
    """

    name: str
    source: str = Field(description="project | mathlib")
    used: bool = False


class LeanDiagnostic(Artifact):
    severity: str = Field(description="error | warning | information")
    message: str
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=0)
    failure_class: str | None = Field(
        default=None,
        description=(
            "surface:name | surface:coercion-form | surface:namespace | surface:arg-order | "
            "surface:motive | surface:instance-mismatch | math:strategy | other. Seeded from "
            "the seven classes measured in log/connectivity-PIPELINE_REPORT.md, where 9 of "
            "~15 build cycles were surface friction and 0 were mathematical."
        ),
    )


class ProposedHelper(Artifact):
    """A helper lemma the worker invented. It becomes a graph node or it is lost.

    Report 04 §B6: two helpers invented mid-proof in July had no identity and were erased
    by the August regeneration.
    """

    lean_name: str
    statement: str
    origin: HelperOrigin
    rationale: str


class ProofAttempt(Artifact):
    id: str
    declaration_id: str
    attempt: int = Field(ge=1)
    role: str = Field(default="proof_worker", description="proof_worker | repair_worker")

    approved_statement_fingerprint: str = Field(
        description="Pins the statement the worker was given; makes rule 7 checkable."
    )
    context_package_id: str
    context_chars: int = Field(
        ge=0, description="Must not grow with attempt number; the repair budget is fixed."
    )

    strategy: str | None = None
    retrieved_declarations: list[RetrievedDeclaration] = Field(default_factory=list)
    generated_proof: str | None = None
    proposed_helpers: list[ProposedHelper] = Field(default_factory=list)

    lean_status: str = Field(default="not_run", description="ok | error | not_run")
    diagnostics: list[LeanDiagnostic] = Field(default_factory=list)
    resulting_goals: list[str] = Field(default_factory=list)

    outcome: ProofOutcome
    failure_class: str | None = None
    review_reason: str | None = Field(
        default=None, description="Required when outcome is STATEMENT_REVIEW_REQUIRED."
    )

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    usd: float | None = Field(default=None, ge=0)
    wall_ms: int | None = Field(default=None, ge=0)
    provenance: Provenance

    @model_validator(mode="after")
    def _outcome_consistency(self) -> ProofAttempt:
        if self.outcome is ProofOutcome.STATEMENT_REVIEW_REQUIRED and not self.review_reason:
            raise ValueError("STATEMENT_REVIEW_REQUIRED requires review_reason")
        if self.outcome is ProofOutcome.SUCCESS:
            if not self.generated_proof:
                raise ValueError("a successful attempt must carry the proof it generated")
            if self.lean_status != "ok":
                raise ValueError("a successful attempt must have lean_status 'ok'")
        return self
