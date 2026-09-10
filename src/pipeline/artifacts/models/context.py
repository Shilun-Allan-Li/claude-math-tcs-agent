"""ContextPackage: the bounded, reproducible input to an agent stage.

Rule 4. Report 06 §F measured what this replaces: the scaffold stage read whole chapters
(up to 3,356 lines) and the proof loop read a whole 1,573-line Lean file to emit at most
30 tactic lines. A package is built by *query* against the corpus graph, so it is
reproducible, cacheable and auditable -- none of which a conversation is.

The package records what was supplied, not merely how much: ``items`` is the audit trail
that lets a caller answer "what did the agent actually see?" after the fact.
"""

from __future__ import annotations

from pydantic import Field

from pipeline.artifacts.models.base import Artifact, Provenance
from pipeline.artifacts.models.enums import Stage

__all__ = ["ContextPackage", "ContextItem"]


class ContextItem(Artifact):
    """One retrieved element, with the reason it was retrieved."""

    role: str = Field(
        description=(
            "target | source_passage | annotation | approved_dependency | notation | "
            "convention | mathlib_candidate | diagnostics | prior_attempt | digest"
        )
    )
    ref: str = Field(description="Declaration id, Mathlib name, or artifact id.")
    content: str
    reason: str = Field(description="Why the graph returned it, e.g. 'informal_dependency of target'.")

    @property
    def char_count(self) -> int:
        return len(self.content)


class ContextPackage(Artifact):
    id: str = Field(description="'cp-' plus a digest of (stage, target, item refs, content).")
    stage: Stage
    target_id: str = Field(description="Declaration the package was built for.")
    items: list[ContextItem] = Field(default_factory=list)
    corpus_version: int = Field(
        description="Registry version the package was built against; detects staleness."
    )
    budget_chars: int | None = Field(
        default=None, description="Configured ceiling, for the audit trail."
    )
    provenance: Provenance

    @property
    def total_chars(self) -> int:
        return sum(i.char_count for i in self.items)

    @property
    def estimated_tokens(self) -> int:
        """Rough 4-chars-per-token estimate, matching the forensic reports' convention."""
        return self.total_chars // 4

    def refs(self) -> list[str]:
        return [i.ref for i in self.items]

    def by_role(self, role: str) -> list[ContextItem]:
        return [i for i in self.items if i.role == role]

    @property
    def within_budget(self) -> bool:
        return self.budget_chars is None or self.total_chars <= self.budget_chars
