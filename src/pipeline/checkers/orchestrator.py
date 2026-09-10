"""The checker orchestrator.

Runs the four logical checkers over a set of declarations and collects their findings into
one schema. Checker 1 is deterministic and runs over a whole Lean module at once; checkers
2-4 are per declaration and hybrid.

The orchestrator's own job is small and deliberately so: fan out, collect, record the run.
It makes no judgements. Everything it does with a finding -- prioritisation, gating -- is
:mod:`pipeline.review`'s, so that the ranking logic has one home and can be read.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.models import CheckerFinding, CheckerName, Severity, Stage, StageRun
from pipeline.providers import LLMProvider
from pipeline.checkers.lean_integrity import LeanIntegrityResult, check_lean_integrity
from pipeline.checkers.hybrid import (
    CheckerOutcome,
    check_library_context,
    check_semantic_sanity,
    check_source_fidelity,
)

__all__ = ["run_checkers", "CheckReport", "ORCHESTRATOR_VERSION"]

ORCHESTRATOR_VERSION = "checker_orchestrator/v1"


@dataclass
class CheckReport:
    declarations: list[str]
    integrity: LeanIntegrityResult | None = None
    outcomes: list[CheckerOutcome] = field(default_factory=list)
    findings: list[CheckerFinding] = field(default_factory=list)
    runs: list[StageRun] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, object]:
        by_checker: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for f in self.findings:
            by_checker[f.checker.value] = by_checker.get(f.checker.value, 0) + 1
            by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1
            by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
        return {
            "declarations": len(self.declarations),
            "findings": len(self.findings),
            "by_checker": dict(sorted(by_checker.items())),
            "by_severity": dict(sorted(by_severity.items())),
            "by_status": dict(sorted(by_status.items())),
            "blocking": sum(1 for f in self.findings if f.blocks_progression),
            "requires_human": sum(1 for f in self.findings if f.requires_human),
            "usd": round(sum(o.usd or 0 for o in self.outcomes), 4),
        }

    def for_declaration(self, declaration_id: str) -> list[CheckerFinding]:
        return [f for f in self.findings if f.declaration_id == declaration_id]


def run_checkers(
    registry: CorpusRegistry,
    *,
    module: str | None = None,
    declaration_ids: Sequence[str] | None = None,
    lean_root: str | Path | None = None,
    fidelity_provider: LLMProvider | None = None,
    library_provider: LLMProvider | None = None,
    semantic_provider: LLMProvider | None = None,
    verify_mathlib_names: bool = False,
    persist: bool = True,
) -> CheckReport:
    """Run every applicable checker.

    ``module`` runs checker 1 over a whole Lean module -- the natural unit, since a build
    is per module. ``declaration_ids`` selects the targets for checkers 2-4; when omitted
    it defaults to whatever the module produced.

    Providers are per checker and optional. Omitting one runs only that checker's
    deterministic half, which is exactly what a fast local pass should do.
    """
    started = time.monotonic()
    report = CheckReport(declarations=list(declaration_ids or ()))

    if module:
        report.integrity = check_lean_integrity(
            registry, module, cwd=lean_root, persist=persist
        )
        report.findings.extend(report.integrity.findings)
        if report.integrity.run:
            report.runs.append(report.integrity.run)
        registry.reload()
        if not report.declarations:
            report.declarations = [
                d for d in report.integrity.trust if not d.startswith(("module:", "lean:"))
            ]

    for declaration_id in report.declarations:
        record = registry.get(declaration_id)
        if record is None or not record.lean.statement:
            continue

        resolutions = None
        if verify_mathlib_names and record.annotation:
            from pipeline.lean.names import resolve_names  # noqa: PLC0415

            candidates = [c.name for c in record.annotation.mathlib_candidates]
            if candidates:
                resolutions = resolve_names(
                    candidates,
                    imports=tuple(
                        next(
                            (p.imports for p in registry.store.read("proposals")  # type: ignore[attr-defined]
                             if p.declaration_id == declaration_id and p.imports),
                            ("Mathlib",),
                        )
                    ),
                    cwd=lean_root,
                )

        for outcome in (
            check_source_fidelity(registry, declaration_id, provider=fidelity_provider),
            check_library_context(
                registry, declaration_id, provider=library_provider, name_resolutions=resolutions
            ),
            check_semantic_sanity(registry, declaration_id, provider=semantic_provider),
        ):
            report.outcomes.append(outcome)
            report.findings.extend(outcome.findings)
            report.warnings.extend(outcome.warnings)

    run = StageRun(
        id=f"run-check-all-{int(time.time() * 1000) % 10**9}",
        stage=Stage.CHECK,
        target_id=module or ",".join(report.declarations[:3]),
        status="ok",
        output_artifact_ids=[f.id for f in report.findings],
        usd=sum(o.usd or 0 for o in report.outcomes) or None,
        input_tokens=sum(o.input_tokens or 0 for o in report.outcomes) or None,
        output_tokens=sum(o.output_tokens or 0 for o in report.outcomes) or None,
        wall_ms=int((time.monotonic() - started) * 1000),
    )
    report.runs.append(run)

    if persist:
        non_integrity = [
            f for f in report.findings if f.checker is not CheckerName.LEAN_INTEGRITY
        ]
        if non_integrity:
            registry.store.upsert("findings", non_integrity)
        registry.store.append("runs", run)
        all_findings = registry.store.read("findings")
        for record in registry:
            record.finding_ids = sorted(
                {f.id for f in all_findings if f.declaration_id == record.id}  # type: ignore[attr-defined]
            )
        registry.upsert_records(list(registry))
        registry.save()

    return report
