"""SourceLeanMapping: one recorded difference between source form and Lean form.

Rule 3 in artifact form. The schema is the one already populated by hand over chapters
1-3 in ``files/evidence/source-lean-mappings.jsonl`` (44 rows), so the historical
mappings replay against this model without translation. That corpus is also why the
model exists: 14 of those 44 mappings are ``not_equivalent``.
"""

from __future__ import annotations

from pydantic import Field

from pipeline.artifacts.models.base import Confidence, Artifact
from pipeline.artifacts.models.enums import MappingType, SemanticStatus

__all__ = ["SourceLeanMapping"]


class SourceLeanMapping(Artifact):
    id: str = Field(description="Stable within a declaration: '<declaration_id>/m<N>'.")
    declaration_id: str
    aspect: str = Field(
        description="What is being mapped, e.g. 'edge cut' or 'the carrier type'."
    )
    source_form: str = Field(description="The book's form, verbatim where possible.")
    lean_form: str = Field(description="The Lean form.")
    mapping_type: MappingType
    semantic_status: SemanticStatus
    justification: str = Field(
        description=(
            "Why the change is sound, in the producer's own words. Report 02 §C1: the "
            "summer wrote these as '## In Lean notation' docstring sections and they are "
            "the single most valuable artifact in the corpus -- the container was the "
            "problem, not the practice."
        )
    )
    confidence: Confidence = 1.0
    declared_by_producer: bool = Field(
        default=True,
        description=(
            "True when the formalizer itself declared the divergence. A checker finding "
            "that merely confirms a declared mapping is an audit trail entry, not a defect "
            "-- this is what keeps the fidelity checker's false-positive rate usable."
        ),
    )
