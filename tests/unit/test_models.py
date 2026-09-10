"""Model invariants. Milestone 1 requires invalid artifacts to fail loudly."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline.artifacts.models import (
    CheckerFinding,
    CheckerName,
    Evidence,
    FindingCategory,
    FindingStatus,
    FormalizationProposal,
    LeanDeclarationKind,
    ProofAttempt,
    ProofOutcome,
    ProposalStatus,
    Provenance,
    ReviewDecision,
    ReviewState,
    ReviewStatus,
    Severity,
    SorryKind,
    SourceSpan,
)

DET = Provenance(producer="test")
LLM = Provenance(producer="test", provider="anthropic", model="claude-opus-5")


class TestValidationIsLoud:
    def test_unknown_fields_are_rejected(self):
        with pytest.raises(ValidationError):
            SourceSpan(start=0, end=1, bogus=True)

    def test_span_must_be_ordered(self):
        with pytest.raises(ValidationError):
            SourceSpan(start=10, end=3)

    def test_assignment_is_revalidated(self):
        span = SourceSpan(start=0, end=10)
        with pytest.raises(ValidationError):
            span.start = -1


class TestSorryKindInvariant:
    """Report 02 §B4: `def := sorry` and `theorem := by sorry` are different failures."""

    def _proposal(self, kind, sorry_kind):
        return FormalizationProposal(
            id="d/f1",
            declaration_id="d",
            status=ProposalStatus.PROPOSED,
            lean_name="Foo",
            declaration_kind=kind,
            statement="...",
            sorry_kind=sorry_kind,
            annotation_fingerprint="f",
            provenance=DET,
        )

    def test_theorem_cannot_be_object_pending(self):
        with pytest.raises(ValidationError, match="object_pending"):
            self._proposal(LeanDeclarationKind.THEOREM, SorryKind.OBJECT_PENDING)

    def test_def_cannot_be_proof_pending(self):
        with pytest.raises(ValidationError, match="proof_pending"):
            self._proposal(LeanDeclarationKind.DEF, SorryKind.PROOF_PENDING)

    def test_the_valid_pairings_are_accepted(self):
        assert self._proposal(LeanDeclarationKind.THEOREM, SorryKind.PROOF_PENDING)
        assert self._proposal(LeanDeclarationKind.DEF, SorryKind.OBJECT_PENDING)
        assert self._proposal(LeanDeclarationKind.DEF, SorryKind.NONE)


class TestProposalStatusConsistency:
    def test_proposed_requires_a_lean_statement(self):
        with pytest.raises(ValidationError, match="missing"):
            FormalizationProposal(
                id="d/f1", declaration_id="d", status=ProposalStatus.PROPOSED,
                annotation_fingerprint="f", provenance=DET,
            )

    def test_needs_design_requires_a_reason(self):
        with pytest.raises(ValidationError, match="needs_design_reason"):
            FormalizationProposal(
                id="d/f1", declaration_id="d", status=ProposalStatus.NEEDS_DESIGN,
                annotation_fingerprint="f", provenance=DET,
            )

    def test_needs_design_with_a_reason_is_a_legitimate_outcome(self):
        p = FormalizationProposal(
            id="d/f1", declaration_id="d", status=ProposalStatus.NEEDS_DESIGN,
            needs_design_reason="Harary graph construction has no faithful Lean form yet",
            annotation_fingerprint="f", provenance=DET,
        )
        assert p.lean_name is None


class TestFindingInvariants:
    def _finding(self, provenance, confidence, status=FindingStatus.FAIL, evidence=None):
        return CheckerFinding(
            id="f-1", declaration_id="d", checker=CheckerName.LEAN_INTEGRITY,
            checker_version="v1", status=status, category=FindingCategory.DIRECT_SORRY,
            severity=Severity.MEDIUM, confidence=confidence, message="m",
            evidence=evidence if evidence is not None else [Evidence(kind="file_line", value="a.lean:1")],
            provenance=provenance,
        )

    def test_deterministic_checkers_must_report_full_confidence(self):
        """Rule 5: a program that inspected Lean is not 90% sure."""
        with pytest.raises(ValidationError, match="confidence 1.0"):
            self._finding(DET, 0.9)
        assert self._finding(DET, 1.0)

    def test_llm_checkers_may_be_uncertain(self):
        assert self._finding(LLM, 0.62)

    def test_a_failing_finding_must_carry_evidence(self):
        with pytest.raises(ValidationError, match="no evidence"):
            self._finding(DET, 1.0, evidence=[])

    def test_a_passing_finding_needs_no_evidence(self):
        assert self._finding(DET, 1.0, status=FindingStatus.PASS, evidence=[])


class TestReviewPersistence:
    """Rule 8: agents may raise findings but never overwrite a human decision."""

    def test_human_decision_survives_agent_writes(self):
        state = ReviewState(declaration_id="d")
        state.human_decision = ReviewDecision(
            id="rv-1", declaration_id="d", status=ReviewStatus.APPROVED,
            reviewer="rxw", rationale="checked by hand", artifact_fingerprint="abc",
        )
        state.agent_status = ReviewStatus.NEEDS_HUMAN
        assert state.status is ReviewStatus.APPROVED
        assert state.is_human_decided

    def test_agent_status_governs_until_a_human_decides(self):
        state = ReviewState(declaration_id="d")
        assert state.status is ReviewStatus.UNREVIEWED
        state.agent_status = ReviewStatus.AGENT_PASS
        assert state.status is ReviewStatus.AGENT_PASS

    def test_a_changed_artifact_makes_a_decision_stale(self):
        state = ReviewState(declaration_id="d")
        state.human_decision = ReviewDecision(
            id="rv-1", declaration_id="d", status=ReviewStatus.APPROVED,
            reviewer="rxw", rationale="ok", artifact_fingerprint="abc",
        )
        assert not state.stale_against("abc")
        assert state.stale_against("def")


class TestProofAttemptInvariants:
    """Rule 7 made checkable."""

    def _attempt(self, **kw):
        base = dict(
            id="pa-1", declaration_id="d", attempt=1,
            approved_statement_fingerprint="abc", context_package_id="cp-1",
            context_chars=100, outcome=ProofOutcome.FAIL, provenance=LLM,
        )
        return ProofAttempt(**(base | kw))

    def test_statement_review_required_must_say_why(self):
        with pytest.raises(ValidationError, match="review_reason"):
            self._attempt(outcome=ProofOutcome.STATEMENT_REVIEW_REQUIRED)
        assert self._attempt(
            outcome=ProofOutcome.STATEMENT_REVIEW_REQUIRED,
            review_reason="hypothesis k >= 1 is missing; false at k = 0",
        )

    def test_success_requires_a_proof_and_a_clean_build(self):
        with pytest.raises(ValidationError, match="must carry the proof"):
            self._attempt(outcome=ProofOutcome.SUCCESS, lean_status="ok")
        with pytest.raises(ValidationError, match="lean_status"):
            self._attempt(outcome=ProofOutcome.SUCCESS, generated_proof="by simp")
        assert self._attempt(
            outcome=ProofOutcome.SUCCESS, generated_proof="by simp", lean_status="ok"
        )
