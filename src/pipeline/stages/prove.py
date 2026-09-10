"""Stage 4 -- proof orchestration.

The invariant, and the reason this stage is shaped the way it is:

    A proof agent receives an APPROVED Lean statement, and may modify only the proof body.
    If it believes the statement is wrong, it returns ``STATEMENT_REVIEW_REQUIRED``.

Rule 7 is enforced structurally, not asked for politely. The worker is handed a *body*
slot, never the statement; the verifier reassembles the declaration from the approved
statement plus the returned body; and the attempt record pins
``approved_statement_fingerprint``, so a changed statement is detectable after the fact.

Five roles, and only one of them is an agent:

===============  =========================================================
role             implementation
===============  =========================================================
Orchestrator     deterministic scheduler over the corpus graph
Context Builder  deterministic graph query (:mod:`pipeline.context.builders`)
Proof Worker     **agent**
Lean Verifier    deterministic: assemble, ``lake build``, ``#print axioms``
Repair Worker    **agent**, bounded, with a context budget that does not grow
===============  =========================================================

Report 04 §D argues each of those placements from the summer's measurements: the one
instrumented session spent zero build cycles on mathematical error and roughly nine of
fifteen on Lean-surface friction, and its sub-agent hand-offs cost more than they saved.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.corpus import CorpusRegistry
from pipeline.corpus.ids import content_fingerprint
from pipeline.lean import lake_build, print_axioms
from pipeline.artifacts.models import (
    STATEMENT_USABLE_STATES,
    ContextPackage,
    EdgeType,
    DeclarationRecord,
    LeanDiagnostic,
    ProofAttempt,
    ProofOutcome,
    Provenance,
    ReviewStatus,
    RetrievedDeclaration,
    Stage,
    StageRun,
    TrustStatus,
)
from pipeline.prompts import Prompt, load_prompt
from pipeline.providers import LLMProvider, LLMRequest, call_with_retry
from pipeline.context.builders import build_proof_context
from pipeline.stages.scaffold import plan_scaffold, render_scaffold

__all__ = [
    "proof_eligibility",
    "ready_declarations",
    "prove_declaration",
    "ProofResult",
    "Eligibility",
    "PROVE_VERSION",
    "STATEMENT_REVIEW_SENTINEL",
]

PROVE_VERSION = "prove/v1"
STATEMENT_REVIEW_SENTINEL = "STATEMENT_REVIEW_REQUIRED"

#: The failure classes measured in the summer's one instrumented proof session. Nine of
#: roughly fifteen build cycles were surface friction of these kinds; none were maths.
_FAILURE_CLASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("surface:name", re.compile(r"unknown (identifier|constant)|Unknown constant", re.I)),
    ("surface:namespace", re.compile(r"invalid field|ambiguous", re.I)),
    ("surface:instance-mismatch", re.compile(r"failed to synthesize|instance", re.I)),
    ("surface:motive", re.compile(r"motive is not type correct", re.I)),
    ("surface:coercion-form", re.compile(r"type mismatch|coercion", re.I)),
    ("math:strategy", re.compile(r"unsolved goals", re.I)),
)


def classify_failure(diagnostics: Sequence[LeanDiagnostic]) -> str | None:
    for diagnostic in diagnostics:
        if diagnostic.severity != "error":
            continue
        for name, pattern in _FAILURE_CLASSES:
            if pattern.search(diagnostic.message):
                return name
        return "other"
    return None


def _retrieved(
    registry: CorpusRegistry, package: ContextPackage, proof: str | None
) -> list[RetrievedDeclaration]:
    """Which supplied lemmas the proof actually used.

    Measuring this is how the value of retrieval becomes knowable: the summer's one cached
    Mathlib survey cost 86,999 tokens and nothing recorded which of its entries earned it.
    A project dependency is matched on its *Lean* name, not its declaration id -- the id is
    not what appears in a proof.
    """
    out: list[RetrievedDeclaration] = []
    for item in package.items:
        if item.role not in ("approved_dependency", "mathlib_candidate"):
            continue
        if item.role == "mathlib_candidate":
            name, source = item.ref, "mathlib"
        else:
            record = registry.resolve(item.ref)
            name = (record.lean.name if record and record.lean.name else item.ref)
            source = "project"
        short = name.rsplit(".", 1)[-1]
        out.append(RetrievedDeclaration(name=name, source=source,
                                        used=bool(proof and short in proof)))
    return out


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason: str
    blockers: tuple[str, ...] = ()


def proof_eligibility(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    require_approval: bool = True,
) -> Eligibility:
    """May this declaration enter the proof queue?

    Three gates, in order of consequence:

    1. it must have a Lean statement at all;
    2. that statement must be **approved** by a human, and the approval must not be stale
       -- proving an unapproved statement is how the summer produced proofs of theorems
       that were not the book's;
    3. every dependency must be usable: a dependency that is still ``sorry`` is fine (that
       is the sorry-ladder, and it is the point), but one that is an **opaque object** is
       not, because a statement quantifying over it asserts nothing.
    """
    record = registry.get(declaration_id)
    if record is None:
        return Eligibility(False, f"no declaration {declaration_id!r}")
    if not record.lean.statement or not record.lean.name:
        return Eligibility(False, "not formalized")
    if record.trust.status is TrustStatus.FULLY_VERIFIED:
        return Eligibility(False, "already proved")
    if record.trust.status is TrustStatus.UNFINISHED_CONSTRUCTION:
        return Eligibility(False, "this is an unfinished object, not an open proof")
    if record.trust.status is TrustStatus.BLOCKED_BY_UNTRUSTED_DEPENDENCY:
        return Eligibility(
            False, "quantifies over an object with no definition", tuple(record.trust.blocked_by)
        )
    if require_approval and record.review.status is not ReviewStatus.APPROVED:
        return Eligibility(False, f"statement is {record.review.status.value}, not APPROVED")
    if require_approval:
        from pipeline.artifacts.records import record_fingerprint

        if record.review.stale_against(record_fingerprint(record)):
            return Eligibility(False, "the statement changed since it was approved")

    # Only *Lean* dependencies gate a Lean proof. An informal cross-reference to a chapter
    # that has not been formalized yet is a fact about the book, not an obstacle to
    # elaborating this proof -- and gating on it would stall every chapter behind its
    # predecessors, which is the chapter-serialised schedule the graph exists to replace.
    blockers: list[str] = []
    for dependency_id in registry.prerequisites(
        declaration_id, edge_types=[EdgeType.LEAN_LOCAL_DEPENDENCY], include_mathlib=False
    ):
        dependency = registry.resolve(dependency_id)
        if dependency is None:
            blockers.append(f"{dependency_id} (not in corpus)")
        elif dependency.trust.status not in STATEMENT_USABLE_STATES:
            blockers.append(f"{dependency_id} ({dependency.trust.status.value})")
    if blockers:
        return Eligibility(False, "a dependency is not usable", tuple(blockers))
    return Eligibility(True, "ready")


def ready_declarations(
    registry: CorpusRegistry, *, chapter: str | None = None, require_approval: bool = True
) -> list[DeclarationRecord]:
    """Declarations the orchestrator may dispatch, in dependency order.

    The scheduling unit is the **declaration**, not the chapter: independent nodes can run
    in parallel, and the graph -- not the table of contents -- says which are independent.
    """
    pool = registry.declarations_in_chapter(chapter) if chapter else list(registry)
    eligible = [
        r for r in pool
        if proof_eligibility(registry, r.id, require_approval=require_approval).eligible
    ]
    order = registry.graph.topological_order() or []
    rank = {node: i for i, node in enumerate(order)}
    return sorted(eligible, key=lambda r: (rank.get(r.id, len(rank)), r.id))


@dataclass
class ProofResult:
    declaration_id: str
    attempts: list[ProofAttempt] = field(default_factory=list)
    context: ContextPackage | None = None
    runs: list[StageRun] = field(default_factory=list)
    proof: str | None = None
    outcome: ProofOutcome = ProofOutcome.FAIL

    @property
    def succeeded(self) -> bool:
        return self.outcome is ProofOutcome.SUCCESS

    @property
    def summary(self) -> dict[str, object]:
        return {
            "declaration_id": self.declaration_id,
            "outcome": self.outcome.value,
            "attempts": len(self.attempts),
            "context_chars": self.context.total_chars if self.context else 0,
            "context_stable": len({a.context_chars for a in self.attempts}) <= 1,
            "failure_classes": [a.failure_class for a in self.attempts if a.failure_class],
            "usd": round(sum(a.usd or 0 for a in self.attempts), 4),
        }


def _verify(
    registry: CorpusRegistry,
    record: DeclarationRecord,
    proof: str,
    *,
    lean_root: Path,
    chapter: str,
    scratch_module: str = "ProofScratch",
) -> tuple[bool, list[LeanDiagnostic], list[str]]:
    """Assemble the candidate into a scratch module and ask Lean.

    The canonical module is never touched, so a failed attempt cannot leave the corpus in
    a broken state -- which is how the summer lost two completed developments.
    """
    plan = plan_scaffold(registry, chapter, module=scratch_module)
    source = render_scaffold(
        registry, plan, chapter_title="proof attempt",
        module_name=scratch_module, proof_bodies={record.id: proof},
    )
    target = lean_root / "fixtures/lean" / f"{scratch_module}.lean"
    target.write_text(source, encoding="utf-8")
    build = lake_build(scratch_module, cwd=lean_root)
    diagnostics = [
        LeanDiagnostic(
            severity=d.severity, message=d.message, file=d.file, line=d.line, column=d.column,
            failure_class=None,
        )
        for d in build.diagnostics
    ]
    axioms: list[str] = []
    if build.ok and record.lean.name:
        reports, _ = print_axioms(scratch_module, [record.lean.name], cwd=lean_root)
        report = reports.get(record.lean.name)
        axioms = list(report.axioms) if report else []
    return build.ok, diagnostics, axioms


def _extract_proof(text: str) -> str | None:
    """Pull the tactic block out of a worker response."""
    if STATEMENT_REVIEW_SENTINEL in text:
        return None
    if m := re.search(r"```(?:lean)?\s*(.*?)```", text, re.S):
        return m.group(1).strip()
    return text.strip() or None


def prove_declaration(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    provider: LLMProvider,
    lean_root: str | Path,
    chapter: str | None = None,
    prompt: Prompt | None = None,
    repair_prompt: Prompt | None = None,
    model: str | None = None,
    max_attempts: int = 3,
    require_approval: bool = True,
    persist: bool = True,
) -> ProofResult:
    """Run one declaration through worker → verifier → repair, bounded."""
    lean_root = Path(lean_root)
    record = registry.require(declaration_id)
    chapter = chapter or record.source.chapter

    eligibility = proof_eligibility(registry, declaration_id, require_approval=require_approval)
    result = ProofResult(declaration_id=declaration_id)
    if not eligibility.eligible:
        result.outcome = ProofOutcome.ESCALATE
        run = StageRun(
            id=f"run-prove-{declaration_id}-{int(time.time() * 1000) % 10**9}",
            stage=Stage.PROVE, target_id=declaration_id, status="skipped",
            error=eligibility.reason + (f" [{', '.join(eligibility.blockers)}]" if eligibility.blockers else ""),
            error_kind="validation",
        )
        result.runs.append(run)
        if persist:
            registry.store.append("runs", run)
        return result

    prompt = prompt or load_prompt("prove", "declaration")
    repair_prompt = repair_prompt or load_prompt("repair", "declaration")
    model = model or prompt.model or "claude-opus-5"
    approved_fingerprint = content_fingerprint(record.lean.statement)

    diagnostics: list[LeanDiagnostic] = []
    failed_strategies: list[str] = []
    started_all = time.monotonic()

    for attempt_number in range(1, max_attempts + 1):
        is_repair = attempt_number > 1
        package = build_proof_context(
            registry, declaration_id,
            diagnostics=[f"{d.severity}: {d.message}" for d in diagnostics],
            failed_strategies=failed_strategies,
        )
        if result.context is None:
            result.context = package

        active_prompt = repair_prompt if is_repair else prompt
        request = LLMRequest(
            system=active_prompt.system,
            user=active_prompt.render(
                declaration_id=declaration_id,
                statement=record.lean.statement,
                source=record.source.statement,
                sketch="\n".join(
                    i.content for i in package.by_role("annotation")
                ) or "(none)",
                definitions="\n\n".join(i.content for i in package.by_role("approved_dependency"))
                or "(none)",
                lemmas="\n".join(i.content for i in package.by_role("mathlib_candidate")) or "(none)",
                diagnostics="\n".join(i.content for i in package.by_role("diagnostics")) or "(none yet)",
                attempts="\n".join(i.content for i in package.by_role("prior_attempt")) or "(none)",
            ),
            model=model,
            max_tokens=active_prompt.max_tokens,
        )
        started = time.monotonic()
        response, retries = call_with_retry(provider, request)
        proof = _extract_proof(response.text)

        provenance = Provenance(
            producer=PROVE_VERSION, provider=response.provider, model=response.model,
            prompt_version=active_prompt.id, context_package_id=package.id,
            input_fingerprint=approved_fingerprint, corpus_version=registry.version,
        )

        if proof is None:
            reason = response.text.split(STATEMENT_REVIEW_SENTINEL, 1)[-1].strip() or "no reason given"
            attempt = ProofAttempt(
                id=f"pa-{content_fingerprint(declaration_id, str(attempt_number), 'review')[:16]}",
                declaration_id=declaration_id, attempt=attempt_number,
                role="repair_worker" if is_repair else "proof_worker",
                approved_statement_fingerprint=approved_fingerprint,
                context_package_id=package.id, context_chars=package.total_chars,
                lean_status="not_run", outcome=ProofOutcome.STATEMENT_REVIEW_REQUIRED,
                review_reason=reason,
                input_tokens=response.input_tokens, output_tokens=response.output_tokens,
                usd=response.usd, wall_ms=int((time.monotonic() - started) * 1000),
                provenance=provenance,
            )
            result.attempts.append(attempt)
            result.outcome = ProofOutcome.STATEMENT_REVIEW_REQUIRED
            break

        ok, diagnostics, axioms = _verify(
            registry, record, proof, lean_root=lean_root, chapter=chapter
        )
        failure_class = None if ok else classify_failure(diagnostics)
        if failure_class:
            for diagnostic in diagnostics:
                if diagnostic.severity == "error":
                    object.__setattr__(diagnostic, "failure_class", failure_class)
        trusted = ok and "sorryAx" not in axioms

        attempt = ProofAttempt(
            id=f"pa-{content_fingerprint(declaration_id, str(attempt_number), proof)[:16]}",
            declaration_id=declaration_id, attempt=attempt_number,
            role="repair_worker" if is_repair else "proof_worker",
            approved_statement_fingerprint=approved_fingerprint,
            context_package_id=package.id, context_chars=package.total_chars,
            strategy=(proof.splitlines()[0][:120] if proof else None),
            retrieved_declarations=_retrieved(registry, package, proof),
            generated_proof=proof,
            lean_status="ok" if trusted else "error",
            diagnostics=diagnostics,
            outcome=ProofOutcome.SUCCESS if trusted else ProofOutcome.FAIL,
            failure_class=failure_class or (None if trusted else "trust:sorry_remains"),
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            usd=response.usd, wall_ms=int((time.monotonic() - started) * 1000),
            provenance=provenance,
        )
        result.attempts.append(attempt)

        if trusted:
            result.outcome = ProofOutcome.SUCCESS
            result.proof = proof
            record.lean.proof = proof
            break
        failed_strategies.append(
            f"attempt {attempt_number}: {(attempt.strategy or 'unknown')} -> {failure_class or 'failed'}"
        )
    else:
        result.outcome = ProofOutcome.ESCALATE

    run = StageRun(
        id=f"run-prove-{declaration_id}-{int(time.time() * 1000) % 10**9}",
        stage=Stage.PROVE, target_id=declaration_id,
        status="ok" if result.succeeded else "failed",
        output_artifact_ids=[a.id for a in result.attempts],
        context_package_id=result.context.id if result.context else None,
        model=model, prompt_version=prompt.id,
        input_tokens=sum(a.input_tokens or 0 for a in result.attempts) or None,
        output_tokens=sum(a.output_tokens or 0 for a in result.attempts) or None,
        usd=sum(a.usd or 0 for a in result.attempts) or None,
        wall_ms=int((time.monotonic() - started_all) * 1000),
        error=None if result.succeeded else result.outcome.value,
    )
    result.runs.append(run)

    if persist:
        registry.store.upsert("attempts", result.attempts)
        if result.context:
            registry.store.upsert("context", [result.context])
        registry.store.append("runs", run)
        record.proof_attempt_ids = sorted({a.id for a in result.attempts} | set(record.proof_attempt_ids))
        registry.upsert_records([record])
        registry.save()
    return result
