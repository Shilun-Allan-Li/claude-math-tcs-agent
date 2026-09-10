"""Corpus-graph edges.

An edge records not only *that* a dependency exists but **why the pipeline believes it does**.
Report 06 §E.2: an edge's provenance decides whether it may gate progression -- only
source-extracted and Lean-extracted edges are exact; agent-inferred edges enter as
proposals and gate nothing until a human confirms them. Rule 5 applied to the graph.

:class:`EdgeProvenance` carries three things, and each answers a different question a
person actually asks when an edge looks wrong:

* ``kind`` -- what class of evidence this is, and therefore whether it may gate;
* ``producer`` -- which component asserted it (``cross_references/v1``, ``annotator``,
  ``lean_integrity/v1``);
* ``artifact_id`` -- the persisted artifact the assertion came from, so the claim can be
  read back rather than taken on trust.

Without the last two, "why does this edge exist" is answerable only by re-running the
stage that made it.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from pipeline.artifacts.models.base import Confidence, Artifact
from pipeline.artifacts.models.enums import GATING_PROVENANCE, EdgeProvenanceKind, EdgeType

__all__ = ["DependencyEdge", "EdgeProvenance"]


class EdgeProvenance(Artifact):
    """Why the pipeline believes an edge exists."""

    kind: EdgeProvenanceKind
    producer: str | None = Field(
        default=None, description="Component that asserted the edge, e.g. 'annotator'."
    )
    artifact_id: str | None = Field(
        default=None,
        description="Persisted artifact the assertion came from, e.g. an annotation id.",
    )
    evidence: str | None = Field(
        default=None, description="Where it was read from: file:line, or the raw citation."
    )

    @property
    def may_gate(self) -> bool:
        return self.kind in GATING_PROVENANCE

    def __str__(self) -> str:  # pragma: no cover - display only
        bits = [self.kind.value]
        if self.producer:
            bits.append(self.producer)
        if self.artifact_id:
            bits.append(self.artifact_id)
        return " · ".join(bits)


class DependencyEdge(Artifact):
    source_id: str = Field(description="Declaration id, or 'library:<Name>' for library nodes.")
    target_id: str
    edge_type: EdgeType
    provenance: EdgeProvenance
    confidence: Confidence = 1.0
    evidence: str | None = Field(
        default=None, description="Deprecated: prefer provenance.evidence. Kept readable."
    )
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_provenance(cls, data):
        """Upgrade the pre-structured form in place.

        Edge files written before provenance became an object carry a bare string
        (``"source_extracted"``). Rewriting those files would invalidate every historical
        artifact for no gain, so they are read forward instead: the string becomes the
        ``kind`` and the row's ``evidence`` moves inside.
        """
        if not isinstance(data, dict):
            return data
        prov = data.get("provenance")
        if isinstance(prov, str):
            data = dict(data)
            data["provenance"] = {
                "kind": prov,
                "evidence": data.get("evidence"),
            }
        return data

    @model_validator(mode="after")
    def _mirror_evidence(self) -> DependencyEdge:
        """Keep the two evidence fields agreeing, whichever one the producer set."""
        if self.provenance.evidence is None and self.evidence is not None:
            self.provenance.evidence = self.evidence
        elif self.evidence is None and self.provenance.evidence is not None:
            self.evidence = self.provenance.evidence
        return self

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_id, self.target_id, self.edge_type.value)

    @property
    def may_gate(self) -> bool:
        """Whether this edge is exact enough to block progression without human review."""
        return self.provenance.may_gate
