"""Checker 1 -- Lean integrity.

Deterministic. No model is consulted, and every finding reports confidence 1.0, because a
program that read the kernel's answer is not ninety percent sure (rule 5).

The verdict this produces is :class:`TrustStatus`, and the rule that matters is:

    Do not label a theorem verified merely because its own body has no ``sorry``.

``whitney_inequalities`` in the chapter-3 fixture is the case in point. It is a term-level
assembly of two lemmas, contains no ``sorry``, elaborates cleanly -- and is unproved. Only
``#print axioms`` sees that, which is why it, and not a text scan, decides trust here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.corpus import CorpusRegistry
from pipeline.corpus.ids import content_fingerprint
from pipeline.lean import AxiomReport, BuildResult, lake_build, print_axioms, read_ilean
from pipeline.lean.ilean import IleanIndex
from pipeline.artifacts.models import (
    OBJECT_KINDS,
    CheckerFinding,
    CheckerName,
    CompileStatus,
    DependencyEdge,
    EdgeProvenance,
    EdgeProvenanceKind,
    EdgeType,
    Evidence,
    FindingCategory,
    FindingStatus,
    Provenance,
    Severity,
    Stage,
    StageRun,
    TrustStatus,
)

__all__ = ["check_lean_integrity", "LeanIntegrityResult", "CHECKER_VERSION"]

CHECKER_VERSION = "lean_integrity/v1"
MATHLIB_PREFIX = "mathlib:"


@dataclass
class LeanIntegrityResult:
    module: str
    build: BuildResult
    findings: list[CheckerFinding] = field(default_factory=list)
    trust: dict[str, TrustStatus] = field(default_factory=dict)
    edges: list[DependencyEdge] = field(default_factory=list)
    axioms: dict[str, AxiomReport] = field(default_factory=dict)
    run: StageRun | None = None

    @property
    def summary(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for status in self.trust.values():
            counts[status.value] = counts.get(status.value, 0) + 1
        return {
            "module": self.module,
            "build_ok": self.build.ok,
            "build_ms": self.build.wall_ms,
            "declarations": len(self.trust),
            "findings": len(self.findings),
            "edges": len(self.edges),
            "trust": dict(sorted(counts.items())),
        }


def _finding_id(declaration_id: str, category: FindingCategory, detail: str = "") -> str:
    return "f-" + content_fingerprint(CHECKER_VERSION, declaration_id, category.value, detail)[:16]


def _compute_trust(
    *,
    lean_name: str,
    is_object: bool,
    axiom_report: AxiomReport | None,
    direct_sorry: bool,
    compiled: bool,
    blocked_by: list[str],
) -> TrustStatus:
    """The trust verdict for one declaration.

    Order matters. A compile failure dominates everything; an unfinished *object* is
    distinguished from an unfinished *proof*; a declaration resting on an opaque object is
    called out separately from one resting on an unproved theorem, because the first makes
    its own statement vacuous while the second merely leaves it open.
    """
    if not compiled:
        return TrustStatus.COMPILE_FAILURE
    if axiom_report is None:
        return TrustStatus.UNKNOWN
    if not axiom_report.uses_sorry:
        return TrustStatus.FULLY_VERIFIED
    if is_object and direct_sorry:
        return TrustStatus.UNFINISHED_CONSTRUCTION
    if blocked_by:
        # Checked before `direct_sorry`, deliberately. A theorem that quantifies over an
        # object with no definition is typically *also* unproved, but "unproved" is the
        # lesser fact: this statement cannot be proved, and would assert nothing if it
        # were. Reporting it as merely DIRECT_SORRY would put it in the proof queue, which
        # is exactly the trap `Deferred/` was invented to contain in the summer corpus.
        return TrustStatus.BLOCKED_BY_UNTRUSTED_DEPENDENCY
    if direct_sorry:
        return TrustStatus.DIRECT_SORRY
    return TrustStatus.TRANSITIVE_SORRY


def check_lean_integrity(
    registry: CorpusRegistry,
    module: str,
    *,
    cwd: str | Path | None = None,
    ilean_path: str | Path | None = None,
    persist: bool = True,
) -> LeanIntegrityResult:
    """Build a module and derive every Lean fact the pipeline records about it."""
    started = time.monotonic()
    root = Path(cwd) if cwd else Path.cwd()
    build = lake_build(module, cwd=root)

    ilean = (
        Path(ilean_path)
        if ilean_path
        else root / ".lake/build/lib/lean" / f"{module.replace('.', '/')}.ilean"
    )
    index: IleanIndex | None = read_ilean(ilean) if ilean.exists() else None

    by_lean_name = {r.lean.name: r for r in registry if r.lean.name}
    names = sorted(index.declarations) if index else sorted(by_lean_name)
    reports, _raw = print_axioms(module, names, cwd=root) if build.ok and names else ({}, "")

    provenance = Provenance(producer=CHECKER_VERSION, corpus_version=registry.version)
    findings: list[CheckerFinding] = []
    trust: dict[str, TrustStatus] = {}
    edges: list[DependencyEdge] = []

    # Pass 1: which objects are opaque? Needed before any dependent can be judged.
    opaque_objects: set[str] = set()
    for name in names:
        record = by_lean_name.get(name)
        is_object = bool(record and record.lean.declaration_kind in OBJECT_KINDS)
        report = reports.get(name)
        decl = index.declarations.get(name) if index else None
        direct = bool(decl and build.sorry_lines & set(range(decl.line, decl.end_line + 1)))
        if is_object and report and report.uses_sorry and direct:
            opaque_objects.add(name)

    for name in names:
        record = by_lean_name.get(name)
        declaration_id = record.id if record else f"lean:{name}"
        decl = index.declarations.get(name) if index else None
        report = reports.get(name)
        is_object = bool(record and record.lean.declaration_kind in OBJECT_KINDS)
        direct_sorry = bool(decl and build.sorry_lines & set(range(decl.line, decl.end_line + 1)))

        local_deps = index.local_dependencies(name) if index else []
        external_deps = index.external_dependencies(name) if index else []
        blocked_by = sorted(
            (by_lean_name[d].id if d in by_lean_name else d)
            for d in local_deps
            if d in opaque_objects
        )

        status = _compute_trust(
            lean_name=name,
            is_object=is_object,
            axiom_report=report,
            direct_sorry=direct_sorry,
            compiled=build.ok,
            blocked_by=blocked_by,
        )
        trust[declaration_id] = status

        evidence_axioms = (
            [Evidence(kind="axioms", value=", ".join(report.axioms))] if report else []
        )
        position = (
            [Evidence(kind="file_line", value=f"{module}:{decl.line}",
                      file=str(ilean.name), line=decl.line)]
            if decl
            else []
        )

        if status is TrustStatus.UNFINISHED_CONSTRUCTION:
            findings.append(CheckerFinding(
                id=_finding_id(declaration_id, FindingCategory.UNFINISHED_CONSTRUCTION),
                declaration_id=declaration_id, checker=CheckerName.LEAN_INTEGRITY,
                checker_version=CHECKER_VERSION, status=FindingStatus.FAIL,
                category=FindingCategory.UNFINISHED_CONSTRUCTION, severity=Severity.CRITICAL,
                confidence=1.0,
                message=(
                    f"`{name}` is an object with no definition, so every statement about it "
                    f"is vacuous rather than merely unproved."
                ),
                evidence=evidence_axioms + position,
                suggested_repair="Define the object, or return the declaration to design review.",
                requires_human=True, blocks_progression=True, provenance=provenance,
            ))
        elif status is TrustStatus.BLOCKED_BY_UNTRUSTED_DEPENDENCY:
            findings.append(CheckerFinding(
                id=_finding_id(declaration_id, FindingCategory.VACUOUS_DEPENDENCY, ",".join(blocked_by)),
                declaration_id=declaration_id, checker=CheckerName.LEAN_INTEGRITY,
                checker_version=CHECKER_VERSION, status=FindingStatus.FAIL,
                category=FindingCategory.VACUOUS_DEPENDENCY, severity=Severity.CRITICAL,
                confidence=1.0,
                message=(
                    f"`{name}` quantifies over an object with no definition "
                    f"({', '.join(blocked_by)}), so it cannot be proved and would assert "
                    f"nothing if it were."
                ),
                evidence=evidence_axioms + position,
                suggested_repair="Define the blocking object before proving anything about it.",
                requires_human=True, blocks_progression=True, provenance=provenance,
            ))
        elif status is TrustStatus.TRANSITIVE_SORRY:
            unproved = sorted(
                (by_lean_name[d].id if d in by_lean_name else d)
                for d in local_deps
                if reports.get(d) and reports[d].uses_sorry
            )
            findings.append(CheckerFinding(
                id=_finding_id(declaration_id, FindingCategory.TRANSITIVE_SORRY),
                declaration_id=declaration_id, checker=CheckerName.LEAN_INTEGRITY,
                checker_version=CHECKER_VERSION, status=FindingStatus.WARNING,
                category=FindingCategory.TRANSITIVE_SORRY, severity=Severity.HIGH,
                confidence=1.0,
                message=(
                    f"`{name}` has no `sorry` of its own and elaborates cleanly, but depends "
                    f"on `sorryAx` through {', '.join(unproved) or 'its dependencies'}. It is "
                    f"not proved."
                ),
                evidence=evidence_axioms + position + [
                    Evidence(
                        kind="lean_dependency_path",
                        value=" -> ".join([declaration_id, *unproved]),
                    ),
                    Evidence(
                        kind="lean_dependency_path",
                        value=" -> ".join([name, *(by_lean_name[d].lean.name or d if d in by_lean_name else d for d in local_deps if reports.get(d) and reports[d].uses_sorry)]),
                    )
                ],
                requires_human=False, blocks_progression=True, provenance=provenance,
            ))
        elif status is TrustStatus.DIRECT_SORRY:
            findings.append(CheckerFinding(
                id=_finding_id(declaration_id, FindingCategory.DIRECT_SORRY),
                declaration_id=declaration_id, checker=CheckerName.LEAN_INTEGRITY,
                checker_version=CHECKER_VERSION, status=FindingStatus.WARNING,
                category=FindingCategory.DIRECT_SORRY, severity=Severity.MEDIUM,
                confidence=1.0,
                message=f"`{name}` is stated but not proved.",
                evidence=evidence_axioms + position,
                requires_human=False, blocks_progression=False, provenance=provenance,
            ))
        elif status is TrustStatus.FULLY_VERIFIED:
            findings.append(CheckerFinding(
                id=_finding_id(declaration_id, FindingCategory.AXIOM_TRUST),
                declaration_id=declaration_id, checker=CheckerName.LEAN_INTEGRITY,
                checker_version=CHECKER_VERSION, status=FindingStatus.PASS,
                category=FindingCategory.AXIOM_TRUST, severity=Severity.LOW, confidence=1.0,
                message=f"`{name}` compiles and depends on no `sorryAx`.",
                evidence=evidence_axioms, provenance=provenance,
            ))

        # Dependency edges, extracted from the compiler and therefore able to gate.
        for dep in local_deps:
            target = by_lean_name[dep].id if dep in by_lean_name else f"lean:{dep}"
            edges.append(DependencyEdge(
                source_id=declaration_id, target_id=target,
                edge_type=EdgeType.LEAN_LOCAL_DEPENDENCY,
                provenance=EdgeProvenance(
                    kind=EdgeProvenanceKind.LEAN_EXTRACTED,
                    producer=CHECKER_VERSION,
                    artifact_id=f"{ilean.name}#{name}",
                    evidence=f"{ilean.name}: {name} references {dep}",
                ),
                confidence=1.0,
            ))
        for dep in external_deps:
            edges.append(DependencyEdge(
                source_id=declaration_id, target_id=f"{MATHLIB_PREFIX}{dep}",
                edge_type=EdgeType.MATHLIB_DEPENDENCY,
                provenance=EdgeProvenance(
                    kind=EdgeProvenanceKind.LEAN_EXTRACTED,
                    producer=CHECKER_VERSION,
                    artifact_id=f"{ilean.name}#{name}",
                    evidence=f"{ilean.name}: {name} references {dep}",
                ),
                confidence=1.0,
            ))

        if record is not None:
            record.trust.compile_status = CompileStatus.OK if build.ok else CompileStatus.ERROR
            record.trust.direct_sorry = direct_sorry
            record.trust.transitive_sorry = bool(report and report.uses_sorry)
            record.trust.unfinished_construction = status is TrustStatus.UNFINISHED_CONSTRUCTION
            record.trust.axioms = list(report.axioms) if report else []
            record.trust.status = status
            record.trust.blocked_by = blocked_by
            record.trust.checked_at_fingerprint = content_fingerprint(record.lean.statement)
            if decl:
                record.lean.file = str(ilean.with_suffix(".lean").name)
                record.lean.line = decl.name_line or decl.line
                record.lean.end_line = decl.end_line
                record.lean.module = module

    # Compile errors that could not be attributed to a declaration.
    for diagnostic in build.errors:
        findings.append(CheckerFinding(
            id=_finding_id(module, FindingCategory.COMPILE_FAILURE, diagnostic.message[:60]),
            declaration_id=f"module:{module}", checker=CheckerName.LEAN_INTEGRITY,
            checker_version=CHECKER_VERSION, status=FindingStatus.FAIL,
            category=FindingCategory.COMPILE_FAILURE, severity=Severity.CRITICAL, confidence=1.0,
            message=diagnostic.message,
            evidence=[Evidence(kind="file_line",
                               value=f"{diagnostic.file}:{diagnostic.line}",
                               file=diagnostic.file, line=diagnostic.line)],
            requires_human=True, blocks_progression=True, provenance=provenance,
        ))

    run = StageRun(
        id=f"run-check-{module}-{int(time.time() * 1000) % 10**9}",
        stage=Stage.CHECK, target_id=module,
        status="ok" if build.ok else "failed",
        output_artifact_ids=[f.id for f in findings],
        wall_ms=int((time.monotonic() - started) * 1000),
        error=None if build.ok else f"{len(build.errors)} compile errors",
        error_kind=None if build.ok else "fatal",
    )

    if persist:
        registry.store.upsert("findings", findings)
        # Lean-extracted edges are re-derived from the module on every check, so they
        # replace the previous projection instead of merging with it. Only declarations
        # this run actually inspected are touched.
        registry.replace_edges(
            edges,
            source_ids={e.source_id for e in edges} | set(trust),
            edge_types=[EdgeType.LEAN_LOCAL_DEPENDENCY, EdgeType.MATHLIB_DEPENDENCY],
        )
        registry.upsert_records([r for r in registry if r.lean.name in set(names)])
        for record in registry:
            record.finding_ids = sorted(
                {f.id for f in registry.store.read("findings") if f.declaration_id == record.id}  # type: ignore[attr-defined]
            )
        registry.upsert_records(list(registry))
        registry.refresh_dependency_facets()
        registry.store.append("runs", run)
        registry.save()

    return LeanIntegrityResult(
        module=module, build=build, findings=findings, trust=trust, edges=edges,
        axioms=reports, run=run,
    )
