"""Human review: persistence, and risk-based prioritisation.

Two rules govern this module.

**Rule 8 -- human decisions persist.** :class:`~pipeline.artifacts.models.review.ReviewState` keeps the
human decision in a field no agent path writes; an agent may only set ``agent_status`` and
add findings. Both are visible; the human decision wins. Nothing here can overwrite one.

**Risk is interpretable, not learned.** Report 03 §4 designs the score and the brief asks
for it explicitly: no opaque model. Every contribution is a named factor with a weight you
can read, and :meth:`ReviewState.risk_factors` records the breakdown, so a reviewer can see
*why* something is near the top of the queue rather than being told that it is.

The weights come from where the summer's cost actually was. Of 37 categorised issues in
chapters 1-3, six were critical -- and four of those six were **definitions**. That is why
``foundational`` is the largest single term.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pipeline.corpus import CorpusRegistry
from pipeline.corpus.ids import content_fingerprint
from pipeline.artifacts.models import (
    HUMAN_DECISIONS,
    SEVERITY_RANK,
    CheckerFinding,
    CheckerName,
    DeclarationRecord,
    FindingStatus,
    ReviewDecision,
    ReviewStatus,
    Severity,
    SorryKind,
    TrustStatus,
)
from pipeline.artifacts.records import record_fingerprint

__all__ = [
    "RISK_WEIGHTS",
    "score_declaration",
    "recompute_review_states",
    "review_queue",
    "record_decision",
    "add_note",
    "ReviewError",
    "QueueEntry",
]


class ReviewError(RuntimeError):
    pass


#: Interpretable risk weights. Each key is a factor a reviewer can check by hand.
RISK_WEIGHTS: dict[str, float] = {
    # A wrong definition is wrong everywhere downstream, and four of the six critical
    # issues found in the summer's chapters 1-3 were definitions.
    "foundational": 6.0,
    # An object with no body makes every statement about it vacuous rather than unproved.
    "unfinished_construction": 5.0,
    # A recorded not-equivalent mapping is a divergence someone already believed real.
    "semantic_deviation": 5.0,
    # The generator of false-but-compiling theorems.
    "missing_assumption": 4.0,
    # Two independent checkers reaching different conclusions about the same declaration.
    "checker_disagreement": 3.0,
    # Blast radius. Capped, because beyond a handful the marginal signal flattens.
    "reverse_dependencies": 3.0,
    # Proved-looking but not proved: no `sorry`, yet `sorryAx` in the axioms.
    "hidden_transitive_sorry": 2.0,
    "name_collision": 2.0,
    "compile_failure": 4.0,
    "blocked_dependency": 3.0,
    # Early chapters are cited by everything after them.
    "foundational_chapter": 1.0,
    # A finding the producer raised itself, with a repair written out, is cheap to confirm.
    "producer_declared": -2.0,
}

#: Chapters whose declarations everything later builds on.
FOUNDATIONAL_CHAPTERS = frozenset({"1", "2", "3"})


@dataclass
class QueueEntry:
    record: DeclarationRecord
    score: float
    factors: dict[str, float]
    findings: list[CheckerFinding]
    queue: str

    @property
    def top_severity(self) -> Severity:
        if not self.findings:
            return Severity.LOW
        return max((f.severity for f in self.findings), key=lambda s: SEVERITY_RANK[s])

    def as_dict(self) -> dict[str, object]:
        return {
            "declaration_id": self.record.id,
            "queue": self.queue,
            "score": round(self.score, 2),
            "factors": {k: round(v, 2) for k, v in sorted(self.factors.items())},
            "kind": self.record.kind.value,
            "lean_name": self.record.lean.name,
            "trust": self.record.trust.status.value,
            "review": self.record.review.status.value,
            "reverse_dependencies": self.record.reverse_dependency_count,
            "top_severity": self.top_severity.value,
            "findings": [
                {"id": f.id, "checker": f.checker.value, "category": f.category.value,
                 "severity": f.severity.value, "status": f.status.value, "message": f.message}
                for f in sorted(self.findings, key=lambda f: -SEVERITY_RANK[f.severity])
            ],
        }


def score_declaration(
    record: DeclarationRecord, findings: Sequence[CheckerFinding]
) -> tuple[float, dict[str, float]]:
    """Compute the risk score and its breakdown. Pure, and readable by hand."""
    factors: dict[str, float] = {}

    def add(name: str, multiplier: float = 1.0) -> None:
        if multiplier:
            factors[name] = RISK_WEIGHTS[name] * multiplier

    if record.is_foundational:
        add("foundational")
    if record.trust.status is TrustStatus.UNFINISHED_CONSTRUCTION:
        add("unfinished_construction")
    if record.trust.status is TrustStatus.COMPILE_FAILURE:
        add("compile_failure")
    if record.trust.status is TrustStatus.BLOCKED_BY_UNTRUSTED_DEPENDENCY:
        add("blocked_dependency")
    if record.trust.status is TrustStatus.TRANSITIVE_SORRY and record.trust.direct_sorry is False:
        add("hidden_transitive_sorry")
    if any(m.semantic_status.value == "not_equivalent" for m in record.mappings):
        add("semantic_deviation")
    if any(f.category.value == "MISSING_ASSUMPTION" for f in findings):
        add("missing_assumption")
    if any(f.category.value == "NAMING_CONFLICT" for f in findings):
        add("name_collision")
    if record.source.chapter in FOUNDATIONAL_CHAPTERS:
        add("foundational_chapter")
    if record.reverse_dependency_count:
        add("reverse_dependencies", min(record.reverse_dependency_count, 5) / 5)

    # Checker disagreement: two checkers, one passing and one failing on the same item.
    verdicts: dict[CheckerName, set[FindingStatus]] = {}
    for f in findings:
        verdicts.setdefault(f.checker, set()).add(f.status)
    passing = {c for c, s in verdicts.items() if s == {FindingStatus.PASS}}
    failing = {c for c, s in verdicts.items() if FindingStatus.FAIL in s}
    if passing and failing:
        add("checker_disagreement")

    # A finding the producer raised itself, with a repair, is cheaper to confirm.
    actionable = [f for f in findings if f.status is not FindingStatus.PASS]
    if actionable and all(f.producer_declared for f in actionable):
        add("producer_declared")

    return sum(factors.values()), factors


def _queue_for(
    record: DeclarationRecord, findings: Sequence[CheckerFinding], score: float
) -> str:
    """Which queue this declaration belongs in.

    Four queues, per report 03 §4.4. The ordering is by consequence, not by score: a
    blocking finding outranks a high score, because a blocked declaration cannot be worked
    on at all.
    """
    if record.review.is_human_decided and not record.review.stale_against(record_fingerprint(record)):
        return "DONE"
    if any(f.blocks_progression for f in findings):
        return "BLOCKED"
    if record.is_foundational and any(f.status is not FindingStatus.PASS for f in findings):
        return "REVIEW-NOW"
    if any(f.requires_human for f in findings) or score >= 8.0:
        return "REVIEW-NOW"
    if any(f.status is not FindingStatus.PASS for f in findings):
        return "REVIEW-BATCH"
    return "FYI"


def recompute_review_states(
    registry: CorpusRegistry, *, persist: bool = True
) -> list[QueueEntry]:
    """Recompute agent status, risk score and queue for every declaration.

    Never touches :attr:`ReviewState.human_decision`. An agent's later finding can move a
    declaration back into the queue -- which it should -- but the standing decision remains
    on the record and remains what :attr:`ReviewState.status` reports.
    """
    findings_by_declaration: dict[str, list[CheckerFinding]] = {}
    for finding in registry.store.read("findings"):
        findings_by_declaration.setdefault(finding.declaration_id, []).append(finding)  # type: ignore[attr-defined]

    entries: list[QueueEntry] = []
    for record in registry:
        findings = findings_by_declaration.get(record.id, [])
        score, factors = score_declaration(record, findings)
        queue = _queue_for(record, findings, score)

        record.review.risk_score = round(score, 2)
        record.review.risk_factors = {k: round(v, 2) for k, v in factors.items()}
        # Agent-side status only. The human decision is untouched.
        if not findings:
            record.review.agent_status = ReviewStatus.UNREVIEWED
        elif queue in ("BLOCKED", "REVIEW-NOW"):
            record.review.agent_status = ReviewStatus.NEEDS_HUMAN
        elif all(f.status is FindingStatus.PASS for f in findings):
            record.review.agent_status = ReviewStatus.AGENT_PASS
        else:
            record.review.agent_status = ReviewStatus.NEEDS_HUMAN

        entries.append(QueueEntry(record=record, score=score, factors=factors,
                                  findings=findings, queue=queue))

    if persist:
        registry.upsert_records([e.record for e in entries])
        registry.save()
    return entries


_QUEUE_ORDER = {"BLOCKED": 0, "REVIEW-NOW": 1, "REVIEW-BATCH": 2, "FYI": 3, "DONE": 4}


def review_queue(
    entries: Iterable[QueueEntry],
    *,
    queues: Sequence[str] | None = None,
    chapter: str | None = None,
    checker: str | None = None,
    min_severity: Severity | None = None,
    limit: int | None = None,
) -> list[QueueEntry]:
    """Filter and order the queue. Highest consequence first, then highest risk."""
    out = list(entries)
    if queues:
        out = [e for e in out if e.queue in set(queues)]
    if chapter:
        out = [e for e in out if e.record.source.chapter == str(chapter)]
    if checker:
        out = [e for e in out if any(f.checker.value == checker for f in e.findings)]
    if min_severity is not None:
        floor = SEVERITY_RANK[min_severity]
        out = [e for e in out if any(SEVERITY_RANK[f.severity] >= floor for f in e.findings)]
    out.sort(key=lambda e: (_QUEUE_ORDER.get(e.queue, 9), -e.score, e.record.id))
    return out[:limit] if limit else out


def record_decision(
    registry: CorpusRegistry,
    declaration_id: str,
    status: ReviewStatus,
    *,
    reviewer: str,
    rationale: str,
    persist: bool = True,
) -> ReviewDecision:
    """Record a human decision, superseding any previous one.

    Supersession rather than overwrite: issue ``i-033`` in the forensic corpus is a verdict
    that was reversed months later when new evidence appeared, and without a chain of
    decisions a reversal is indistinguishable from a contradiction.
    """
    if status not in HUMAN_DECISIONS:
        raise ReviewError(
            f"{status.value} is not a human decision; expected one of "
            f"{', '.join(sorted(s.value for s in HUMAN_DECISIONS))}"
        )
    record = registry.require(declaration_id)
    previous = record.review.human_decision
    fingerprint = record_fingerprint(record)
    decision = ReviewDecision(
        id="rv-" + content_fingerprint(declaration_id, status.value, reviewer, rationale, fingerprint)[:16],
        declaration_id=declaration_id,
        status=status,
        reviewer=reviewer,
        rationale=rationale,
        findings_reviewed=list(record.finding_ids),
        artifact_fingerprint=fingerprint,
    )
    if previous is not None:
        superseded = previous.model_copy(update={"superseded_by": decision.id})
        if persist:
            registry.store.upsert("reviews", [superseded])
    record.review.human_decision = decision
    if persist:
        registry.store.append("reviews", decision)
        registry.upsert_records([record])
        registry.save()
    return decision


def add_note(
    registry: CorpusRegistry, declaration_id: str, *, author: str, text: str, persist: bool = True
) -> None:
    from pipeline.artifacts.models import ReviewNote

    record = registry.require(declaration_id)
    record.review.notes.append(ReviewNote(author=author, text=text))
    if persist:
        registry.upsert_records([record])
        registry.save()
