"""CheckerFinding: the one representation every checker uses.

Milestone 7 requires a single finding format across all four logical checkers. Report 03
§3 designs it; the vocabulary is seeded from the 37 categorised issues in
``files/evidence/issues.jsonl`` so historical findings replay without translation.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from pipeline.artifacts.models.base import Confidence, Artifact, Provenance
from pipeline.artifacts.models.enums import CheckerName, FindingCategory, FindingStatus, Severity

__all__ = ["CheckerFinding", "Evidence"]


class Evidence(Artifact):
    """A pointer a reader can chase. Findings without evidence are not actionable."""

    kind: str = Field(description="file_line | lean_dependency_path | axioms | source_quote | lean_quote")
    value: str
    file: str | None = None
    line: int | None = Field(default=None, ge=1)


class CheckerFinding(Artifact):
    id: str = Field(description="'f-' plus a deterministic digest of the finding's identity.")
    declaration_id: str
    checker: CheckerName
    checker_version: str
    status: FindingStatus
    category: FindingCategory
    severity: Severity
    confidence: Confidence = Field(
        description="Deterministic checkers must report 1.0; see the validator below."
    )
    message: str
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_repair: str | None = None
    producer_declared: bool = Field(
        default=False,
        description=(
            "True when the producing stage already flagged this itself. Report 03 §0.3: "
            "the summer's Lean carries 508 self-reported hazard markers, several with the "
            "repair written out. Such findings are cheaper to confirm and should be "
            "visibly distinguished from ones a checker inferred."
        ),
    )
    requires_human: bool = False
    blocks_progression: bool = False
    provenance: Provenance

    @model_validator(mode="after")
    def _deterministic_confidence(self) -> CheckerFinding:
        if self.provenance.is_deterministic and self.confidence != 1.0:
            raise ValueError(
                "a deterministic checker must report confidence 1.0; "
                f"{self.checker.value} reported {self.confidence}"
            )
        return self

    @model_validator(mode="after")
    def _actionable(self) -> CheckerFinding:
        if self.status in (FindingStatus.FAIL, FindingStatus.WARNING) and not self.evidence:
            raise ValueError(
                f"{self.status.value} finding {self.id} carries no evidence; "
                "no checker may produce an isolated prose claim"
            )
        return self
