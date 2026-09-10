"""Human review state.

Rule 8: a human decision is persistent. Agents may raise new findings afterwards, but
must never silently overwrite APPROVED / REJECTED / NEEDS_REVISION.

``ReviewState`` therefore stores the human decision and the agent's assessment in
*separate* fields, and exposes the effective status as a computed property. There is no
way for an agent-side write to reach the human decision.
"""

from __future__ import annotations

import datetime as _dt

from pydantic import Field

from pipeline.artifacts.models.base import Artifact, utc_now
from pipeline.artifacts.models.enums import HUMAN_DECISIONS, ReviewStatus

__all__ = ["ReviewDecision", "ReviewNote", "ReviewState"]


class ReviewNote(Artifact):
    author: str
    text: str
    created_at: _dt.datetime = Field(default_factory=utc_now)


class ReviewDecision(Artifact):
    """One human decision, recorded immutably.

    ``superseded_by`` exists because of issue ``i-033``: exercise 1.5.2 was judged
    GENERALIZE and later reversed to DROP when the Mathlib lemma was found. Without
    versioned decisions a reversal is indistinguishable from a contradiction.
    """

    id: str
    declaration_id: str
    status: ReviewStatus
    reviewer: str
    rationale: str
    findings_reviewed: list[str] = Field(
        default_factory=list, description="CheckerFinding ids this decision was made against."
    )
    artifact_fingerprint: str | None = Field(
        default=None,
        description="Fingerprint of what was reviewed; a later change makes the decision stale.",
    )
    superseded_by: str | None = None
    created_at: _dt.datetime = Field(default_factory=utc_now)


class ReviewState(Artifact):
    """Current review state of one declaration."""

    declaration_id: str
    agent_status: ReviewStatus = Field(
        default=ReviewStatus.UNREVIEWED,
        description="What the checkers concluded. Agents may write this freely.",
    )
    human_decision: ReviewDecision | None = Field(
        default=None, description="The standing human decision. Never written by an agent."
    )
    notes: list[ReviewNote] = Field(default_factory=list)
    risk_score: float | None = Field(
        default=None, description="Interpretable priority score; see pipeline.review.risk."
    )
    risk_factors: dict[str, float] = Field(
        default_factory=dict, description="Per-factor contributions, so the score stays readable."
    )

    @property
    def status(self) -> ReviewStatus:
        """A standing human decision always wins."""
        if self.human_decision is not None:
            return self.human_decision.status
        return self.agent_status

    @property
    def is_human_decided(self) -> bool:
        return self.human_decision is not None and self.human_decision.status in HUMAN_DECISIONS

    @property
    def is_approved(self) -> bool:
        return self.status is ReviewStatus.APPROVED

    def stale_against(self, fingerprint: str) -> bool:
        """True when the artifact changed since the human looked at it."""
        if self.human_decision is None or self.human_decision.artifact_fingerprint is None:
            return False
        return self.human_decision.artifact_fingerprint != fingerprint
