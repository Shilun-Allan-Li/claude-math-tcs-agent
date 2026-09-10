"""Construction and update of :class:`DeclarationRecord` aggregates.

Kept separate from the models so that the models stay pure data. Every function here is
deterministic and total: given the same inputs it produces the same record, which is what
makes re-running a stage converge instead of drifting.
"""

from __future__ import annotations

from pipeline.corpus.ids import content_fingerprint
from pipeline.artifacts.models import (
    AnnotatedDeclaration,
    DeclarationRecord,
    FormalizationProposal,
    LeanFacet,
    ProposalStatus,
    ReviewState,
    SourceItem,
)

__all__ = ["record_from_source_item", "attach_annotation", "attach_proposal", "record_fingerprint"]


def record_from_source_item(item: SourceItem) -> DeclarationRecord:
    """Seed a record from the source. This is the only place a record is created.

    The record's ``id`` is the source item's ``id`` -- the same stable identity, carried
    rather than re-derived. Nothing downstream may mint a new one.
    """
    return DeclarationRecord(
        id=item.id,
        kind=item.kind,
        source=item,
        review=ReviewState(declaration_id=item.id),
    )


def attach_annotation(record: DeclarationRecord, annotation: AnnotatedDeclaration) -> DeclarationRecord:
    """Attach stage-1 output, refusing a mismatched or stale annotation."""
    if annotation.declaration_id != record.id:
        raise ValueError(
            f"annotation is for {annotation.declaration_id!r}, record is {record.id!r}"
        )
    if annotation.source_fingerprint != record.source.fingerprint:
        raise ValueError(
            f"annotation for {record.id} was written against source fingerprint "
            f"{annotation.source_fingerprint[:12]}..., but the source is now "
            f"{record.source.fingerprint[:12]}...; re-annotate rather than attach"
        )
    record.annotation = annotation
    record.dependencies.informal = [
        d.target_id for d in annotation.informal_dependencies if d.target_id
    ]
    record.dependencies.unresolved = [
        d.raw_reference for d in annotation.informal_dependencies if not d.target_id
    ]
    return record


def attach_proposal(record: DeclarationRecord, proposal: FormalizationProposal) -> DeclarationRecord:
    """Attach stage-2 output.

    Only a ``PROPOSED`` proposal populates the Lean facet: a ``NEEDS_DESIGN`` or
    ``FAILED`` proposal is recorded on the record (so a client can show why the declaration
    is stalled) but must not put a half-formed Lean name into circulation, because the
    registry and every downstream query key off that name.
    """
    if proposal.declaration_id != record.id:
        raise ValueError(f"proposal is for {proposal.declaration_id!r}, record is {record.id!r}")
    record.proposal_id = proposal.id
    record.mappings = list(proposal.mappings)
    if proposal.status is ProposalStatus.PROPOSED:
        record.lean = LeanFacet(
            name=proposal.lean_name,
            declaration_kind=proposal.declaration_kind,
            statement=proposal.statement,
            module=proposal.namespace,
            sorry_kind=proposal.sorry_kind,
        )
    return record


def record_fingerprint(record: DeclarationRecord) -> str:
    """Fingerprint of the content a human reviews.

    A change here makes a standing review decision stale (:meth:`ReviewState.stale_against`),
    which is how rule 8 stays honest: the decision persists, but a client can show that what
    was approved is no longer what is on disk.
    """
    return content_fingerprint(*record.fingerprint_inputs())
