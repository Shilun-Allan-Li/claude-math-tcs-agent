"""ChapterDigest: the compact export that replaces "feed the previous chapters forward".

Report 01 §G.1 specifies it and §E.5 measures why it is small. Across 17,650 lines of the
summer's annotation there were **28** cross-chapter references, and only four genuine
cross-chapter import edges in the resulting Lean. What a later chapter actually needs from
an earlier one is: the definitions it may reuse, the named results it may cite as black
boxes, the notation, and a one-paragraph summary.

Everything else -- prose, proof sketches, difficulty rubrics, exercise triage -- was never
consumed by another chapter, and carrying it is the context waste report 06 §C measured.
"""

from __future__ import annotations

from pydantic import Field

from pipeline.artifacts.models.base import Artifact, Provenance
from pipeline.artifacts.models.source import NotationEntry

__all__ = ["ChapterDigest", "ExportedDeclaration"]


class ExportedDeclaration(Artifact):
    """One item a later chapter may build on. Statement only -- never a proof."""

    declaration_id: str
    kind: str
    label: str | None = None
    name: str | None = Field(default=None, description="The term, for definitions.")
    statement: str
    lean_name: str | None = None
    trust: str = Field(default="UNKNOWN", description="TrustStatus at digest time.")
    review: str = Field(default="UNREVIEWED", description="ReviewStatus at digest time.")


class ChapterDigest(Artifact):
    chapter_id: str
    chapter: str
    title: str
    summary: str = Field(description="One paragraph: what this chapter establishes.")
    definitions: list[ExportedDeclaration] = Field(
        default_factory=list, description="Foundational items later chapters may reuse."
    )
    results: list[ExportedDeclaration] = Field(
        default_factory=list, description="Named theorems citable as black boxes."
    )
    notation: list[NotationEntry] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    exports_to: list[str] = Field(
        default_factory=list,
        description="Declaration ids in *other* chapters that cite this one.",
    )
    depends_on_chapters: list[str] = Field(default_factory=list)
    provenance: Provenance

    @property
    def size_estimate_chars(self) -> int:
        return (
            len(self.summary)
            + sum(len(d.statement) for d in self.definitions)
            + sum(len(r.statement) for r in self.results)
            + sum(len(n.symbol) + len(n.meaning) + len(n.lean or "") for n in self.notation)
        )
