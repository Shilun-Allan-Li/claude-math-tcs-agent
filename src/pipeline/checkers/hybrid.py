"""Checkers 2-4: source fidelity, library context, semantic sanity.

Each is a **hybrid**: a deterministic pre-pass that decides what a program can decide
exactly, then a model for the judgement that remains. Report 03 argues this shape for all
three, and the split is not cosmetic -- the deterministic halves catch the failures that
cost the most in the summer corpus:

* **fidelity**: comparing the annotation's ``stated_hypotheses`` against the Lean binders
  catches missing assumptions, which produced five theorems that compile, elaborate, and
  are false;
* **library**: registry collisions and ``#check``-verified Mathlib names catch the twelve
  declarations that were written, proved, and later archived as duplicates;
* **sanity**: a statement whose signature has no nonemptiness or cardinality binder while
  its source says ``ν ≥ 3`` is flagged without asking anyone.

The model handles what genuinely needs reading: is this rendering faithful, is that
existing lemma really stronger, is this degenerate case really a counterexample.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from pipeline.corpus import CorpusRegistry
from pipeline.corpus.ids import content_fingerprint
from pipeline.artifacts.models import (
    CheckerFinding,
    CheckerName,
    DeclarationRecord,
    Evidence,
    FindingCategory,
    FindingStatus,
    Provenance,
    Severity,
)
from pipeline.prompts import Prompt, load_prompt
from pipeline.providers import LLMProvider, LLMRequest, call_with_retry

__all__ = [
    "check_source_fidelity",
    "check_library_context",
    "check_semantic_sanity",
    "CheckerOutcome",
    "SOURCE_FIDELITY_VERSION",
    "LIBRARY_CONTEXT_VERSION",
    "SEMANTIC_SANITY_VERSION",
]

SOURCE_FIDELITY_VERSION = "source_fidelity/v1"
LIBRARY_CONTEXT_VERSION = "library_context/v1"
SEMANTIC_SANITY_VERSION = "semantic_sanity/v1"

_SEVERITY = {s.value: s for s in Severity}
_STATUS = {s.value: s for s in FindingStatus}
_CATEGORY = {c.value: c for c in FindingCategory}


@dataclass
class CheckerOutcome:
    checker: CheckerName
    findings: list[CheckerFinding] = field(default_factory=list)
    deterministic_findings: int = 0
    model_findings: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    usd: float | None = None
    wall_ms: int = 0
    warnings: list[str] = field(default_factory=list)


def _finding_id(version: str, declaration_id: str, category: str, detail: str = "") -> str:
    return "f-" + content_fingerprint(version, declaration_id, category, detail)[:16]


def _parse_findings(text: str, checker: CheckerName) -> list[dict]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.S)
    start, end = stripped.find("["), stripped.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"{checker.value} returned no JSON array")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, list):
        raise ValueError(f"{checker.value} returned a {type(payload).__name__}, not an array")
    return [f for f in payload if isinstance(f, dict)]


def _build_finding(
    raw: dict,
    *,
    declaration_id: str,
    checker: CheckerName,
    version: str,
    provenance: Provenance,
    evidence: list[Evidence],
    default_category: FindingCategory,
) -> CheckerFinding | None:
    category = _CATEGORY.get(str(raw.get("category", "")), default_category)
    status = _STATUS.get(str(raw.get("status", "warning")), FindingStatus.WARNING)
    severity = _SEVERITY.get(str(raw.get("severity", "medium")), Severity.MEDIUM)
    message = str(raw.get("message", "")).strip()
    if not message:
        return None
    return CheckerFinding(
        id=_finding_id(version, declaration_id, category.value, message[:64]),
        declaration_id=declaration_id,
        checker=checker,
        checker_version=version,
        status=status,
        category=category,
        severity=severity,
        confidence=float(raw.get("confidence", 0.6)),
        message=message,
        evidence=evidence,
        suggested_repair=raw.get("suggested_repair"),
        requires_human=status is not FindingStatus.PASS and severity in (Severity.HIGH, Severity.CRITICAL),
        blocks_progression=status is FindingStatus.FAIL and severity is Severity.CRITICAL,
        provenance=provenance,
    )


# --------------------------------------------------------------- source fidelity


#: Lean binder shapes that carry a mathematical hypothesis rather than plumbing.
_BINDER_RE = re.compile(r"[(\[{]\s*(?P<body>[^)\]}]*)[)\]}]")
#: Typeclass binders Lean needs to elaborate at all; not mathematical content.
_PLUMBING_RE = re.compile(
    r"\b(Fintype|DecidableEq|DecidableRel|Inhabited|Nonempty|NeZero|Classical)\b"
)


def _lean_binders(statement: str) -> list[str]:
    head = statement.split(":=", 1)[0]
    return [m.group("body").strip() for m in _BINDER_RE.finditer(head) if m.group("body").strip()]


def _deterministic_fidelity(
    record: DeclarationRecord, provenance: Provenance
) -> list[CheckerFinding]:
    """The pre-pass a program can decide: what the formalizer itself declared it changed.

    This is deliberately not an attempt to *understand* the statement. It reports the
    formalizer's own declared divergences, which are facts, and leaves interpretation to
    the model half.
    """
    findings: list[CheckerFinding] = []
    for mapping in record.mappings:
        if mapping.semantic_status.value == "not_equivalent":
            findings.append(CheckerFinding(
                id=_finding_id(SOURCE_FIDELITY_VERSION, record.id, "declared_not_equivalent", mapping.id),
                declaration_id=record.id, checker=CheckerName.SOURCE_FIDELITY,
                checker_version=SOURCE_FIDELITY_VERSION, status=FindingStatus.FAIL,
                category=_CATEGORY.get(mapping.mapping_type.value.upper(), FindingCategory.SEMANTIC_DEVIATION),
                severity=Severity.HIGH, confidence=1.0,
                message=(
                    f"The formalizer recorded this mapping as NOT equivalent to the source: "
                    f"{mapping.aspect}. {mapping.justification}"
                ),
                evidence=[
                    Evidence(kind="source_quote", value=mapping.source_form),
                    Evidence(kind="lean_quote", value=mapping.lean_form),
                ],
                producer_declared=True, requires_human=True, blocks_progression=False,
                provenance=provenance,
            ))
    return findings


def check_source_fidelity(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    provider: LLMProvider | None = None,
    prompt: Prompt | None = None,
    model: str | None = None,
) -> CheckerOutcome:
    """Did the Lean statement preserve the source mathematics?"""
    started = time.monotonic()
    record = registry.require(declaration_id)
    provenance_det = Provenance(producer=SOURCE_FIDELITY_VERSION, corpus_version=registry.version)
    outcome = CheckerOutcome(checker=CheckerName.SOURCE_FIDELITY)

    proposal = next(
        (p for p in registry.store.read("proposals") if p.declaration_id == declaration_id), None  # type: ignore[attr-defined]
    )
    findings = _deterministic_fidelity(record, provenance_det)

    # Dropped hypotheses are the highest-value deterministic signal there is.
    if proposal is not None:
        for hypothesis in proposal.hypotheses_dropped:
            findings.append(CheckerFinding(
                id=_finding_id(SOURCE_FIDELITY_VERSION, record.id, "MISSING_ASSUMPTION", hypothesis[:64]),
                declaration_id=record.id, checker=CheckerName.SOURCE_FIDELITY,
                checker_version=SOURCE_FIDELITY_VERSION, status=FindingStatus.FAIL,
                category=FindingCategory.MISSING_ASSUMPTION, severity=Severity.HIGH, confidence=1.0,
                message=f"The formalizer recorded a dropped source hypothesis: {hypothesis}",
                evidence=[Evidence(kind="source_quote", value=record.source.statement[:400])],
                producer_declared=True, requires_human=True, blocks_progression=False,
                provenance=provenance_det,
            ))
        for hypothesis in proposal.hypotheses_added:
            findings.append(CheckerFinding(
                id=_finding_id(SOURCE_FIDELITY_VERSION, record.id, "OVERSTRONG_ASSUMPTION", hypothesis[:64]),
                declaration_id=record.id, checker=CheckerName.SOURCE_FIDELITY,
                checker_version=SOURCE_FIDELITY_VERSION, status=FindingStatus.WARNING,
                category=FindingCategory.OVERSTRONG_ASSUMPTION, severity=Severity.LOW, confidence=1.0,
                message=f"Hypothesis added with a stated reason: {hypothesis}",
                evidence=[Evidence(kind="lean_quote", value=(record.lean.statement or "")[:400])],
                producer_declared=True, requires_human=False, blocks_progression=False,
                provenance=provenance_det,
            ))
    outcome.deterministic_findings = len(findings)

    if provider is not None and record.lean.statement:
        prompt = prompt or load_prompt("check-source", "declaration")
        annotation = record.annotation
        request = LLMRequest(
            system=prompt.system,
            user=prompt.render(
                declaration_id=declaration_id,
                source=record.source.statement,
                hypotheses="\n".join(f"- {h}" for h in (annotation.stated_hypotheses if annotation else []))
                or "(none recorded)",
                lean=record.lean.statement,
                declared="\n".join(
                    f"- {m.aspect}: {m.source_form} -> {m.lean_form} "
                    f"({m.mapping_type.value}, {m.semantic_status.value}) — {m.justification}"
                    for m in record.mappings
                ) or "(none declared)",
                notation="\n".join(
                    f"{s} = {e.meaning}" + (f" [Lean: {e.lean}]" if e.lean else "")
                    for s, e in sorted(registry.notation().items())
                ) or "(none)",
            ),
            model=model or prompt.model or "claude-opus-5",
            max_tokens=prompt.max_tokens,
        )
        response, _retries = call_with_retry(provider, request)
        provenance_llm = Provenance(
            producer=SOURCE_FIDELITY_VERSION, provider=response.provider, model=response.model,
            prompt_version=prompt.id, corpus_version=registry.version,
        )
        try:
            for raw in _parse_findings(response.text, CheckerName.SOURCE_FIDELITY):
                evidence = [
                    Evidence(kind="source_quote", value=str(raw[k]))
                    for k in ("source_quote",) if raw.get(k)
                ] + [
                    Evidence(kind="lean_quote", value=str(raw[k]))
                    for k in ("lean_quote",) if raw.get(k)
                ]
                finding = _build_finding(
                    raw, declaration_id=declaration_id, checker=CheckerName.SOURCE_FIDELITY,
                    version=SOURCE_FIDELITY_VERSION, provenance=provenance_llm,
                    evidence=evidence, default_category=FindingCategory.UNCERTAIN,
                )
                if finding is not None:
                    findings.append(finding)
                    outcome.model_findings += 1
        except ValueError as exc:
            outcome.warnings.append(str(exc))
        outcome.input_tokens = response.input_tokens
        outcome.output_tokens = response.output_tokens
        outcome.usd = response.usd

    outcome.findings = findings
    outcome.wall_ms = int((time.monotonic() - started) * 1000)
    return outcome


# --------------------------------------------------------------- library context


def check_library_context(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    provider: LLMProvider | None = None,
    prompt: Prompt | None = None,
    model: str | None = None,
    name_resolutions: dict | None = None,
) -> CheckerOutcome:
    """Does this declaration need to exist, in this form?"""
    started = time.monotonic()
    record = registry.require(declaration_id)
    provenance_det = Provenance(producer=LIBRARY_CONTEXT_VERSION, corpus_version=registry.version)
    outcome = CheckerOutcome(checker=CheckerName.LIBRARY_CONTEXT)
    findings: list[CheckerFinding] = []

    # Deterministic: the same statement text under two identities.
    if record.lean.statement:
        normalised = re.sub(r"\s+", " ", record.lean.statement.split(":=", 1)[0]).strip()
        for other in registry:
            if other.id == record.id or not other.lean.statement:
                continue
            other_norm = re.sub(r"\s+", " ", other.lean.statement.split(":=", 1)[0]).strip()
            if normalised and normalised == other_norm:
                findings.append(CheckerFinding(
                    id=_finding_id(LIBRARY_CONTEXT_VERSION, record.id, "DUPLICATE_DECLARATION", other.id),
                    declaration_id=record.id, checker=CheckerName.LIBRARY_CONTEXT,
                    checker_version=LIBRARY_CONTEXT_VERSION, status=FindingStatus.FAIL,
                    category=FindingCategory.DUPLICATE_DECLARATION, severity=Severity.HIGH,
                    confidence=1.0,
                    message=f"Identical Lean signature to `{other.lean.name}` ({other.id}).",
                    evidence=[Evidence(kind="lean_quote", value=normalised)],
                    requires_human=True, blocks_progression=False, provenance=provenance_det,
                ))

    # Deterministic: Mathlib candidate names Lean says do not exist.
    for name, resolution in (name_resolutions or {}).items():
        if not resolution.exists:
            findings.append(CheckerFinding(
                id=_finding_id(LIBRARY_CONTEXT_VERSION, record.id, "UNCERTAIN", name),
                declaration_id=record.id, checker=CheckerName.LIBRARY_CONTEXT,
                checker_version=LIBRARY_CONTEXT_VERSION, status=FindingStatus.WARNING,
                category=FindingCategory.UNCERTAIN, severity=Severity.LOW, confidence=1.0,
                message=(
                    f"The annotation cites `{name}` as a Mathlib candidate, but Lean does not "
                    f"resolve it: {resolution.error}"
                ),
                evidence=[Evidence(kind="lean_quote", value=name)],
                requires_human=False, blocks_progression=False, provenance=provenance_det,
            ))
    outcome.deterministic_findings = len(findings)

    if provider is not None and record.lean.statement:
        prompt = prompt or load_prompt("check-library", "declaration")
        corpus_lines = [
            f"{r.lean.name} ({r.id}, {r.kind.value}): {r.source.statement[:120]}"
            for r in registry
            if r.lean.name and r.id != record.id
        ][:40]
        candidates = "\n".join(
            f"- {name}: {'EXISTS' if res.exists else 'DOES NOT EXIST'}"
            + (f" — {res.type_signature[:120]}" if res.exists and res.type_signature else "")
            for name, res in (name_resolutions or {}).items()
        ) or "(none checked)"
        request = LLMRequest(
            system=prompt.system,
            user=prompt.render(
                declaration_id=declaration_id,
                lean=record.lean.statement,
                lean_name=record.lean.name or "(unnamed)",
                kind=record.lean.declaration_kind.value if record.lean.declaration_kind else "?",
                source=record.source.statement,
                candidates=candidates,
                corpus="\n".join(corpus_lines) or "(empty)",
                conventions="\n".join(f"{k}: {v}" for k, v in sorted(registry.conventions().items()))
                or "(none)",
            ),
            model=model or prompt.model or "claude-opus-5",
            max_tokens=prompt.max_tokens,
        )
        response, _ = call_with_retry(provider, request)
        provenance_llm = Provenance(
            producer=LIBRARY_CONTEXT_VERSION, provider=response.provider, model=response.model,
            prompt_version=prompt.id, corpus_version=registry.version,
        )
        try:
            for raw in _parse_findings(response.text, CheckerName.LIBRARY_CONTEXT):
                evidence = [Evidence(kind="lean_quote", value=str(raw["existing_name"]))] if raw.get("existing_name") else [
                    Evidence(kind="lean_quote", value=record.lean.name or record.id)
                ]
                finding = _build_finding(
                    raw, declaration_id=declaration_id, checker=CheckerName.LIBRARY_CONTEXT,
                    version=LIBRARY_CONTEXT_VERSION, provenance=provenance_llm,
                    evidence=evidence, default_category=FindingCategory.UNNECESSARY_REINVENTION,
                )
                if finding is not None:
                    findings.append(finding)
                    outcome.model_findings += 1
        except ValueError as exc:
            outcome.warnings.append(str(exc))
        outcome.input_tokens = response.input_tokens
        outcome.output_tokens = response.output_tokens
        outcome.usd = response.usd

    outcome.findings = findings
    outcome.wall_ms = int((time.monotonic() - started) * 1000)
    return outcome


# --------------------------------------------------------------- semantic sanity


#: Source phrases that state a size condition the Lean statement ought to carry.
#:
#: Deliberately domain-neutral: "at least three of them", "at least two elements" and
#: "at least two distinct primes" are the same claim about cardinality. A pattern that
#: recognised only one corpus's nouns would pass every other corpus silently, which is
#: the failure mode this checker exists to catch.
_SIZE_CONDITION_RE = re.compile(
    r"\bat (?:least|most) (?P<count>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b"
    r"|\b(?:more|fewer|less) than "
    r"(?P<count2>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b"
    r"|\bnon-?empty\b"
    # A variable bounded by a numeral, in prose or LaTeX: "n >= 2", "n \geq 2", "\nu \ge 3".
    r"|(?:\\)?[A-Za-z]\w*\s*(?:\\(?:geq|ge|leq|le)\b|[\u2265\u2264]|>=|<=)\s*\d+",
    re.I,
)

#: Lean spellings that already carry a size or nonemptiness bound. Checked before warning
#: so a statement that *did* carry the hypothesis is not reported for lacking it.
_SIZE_IN_LEAN_RE = re.compile(
    r"\bcard\b|\bNonempty\b|\bNeZero\b|\bFinite\b|\bFintype\b|\bpos\b"
    r"|[\u2265\u2264]|>=|<=",
    re.I,
)
_NUMERIC_BINDER_RE = re.compile(r"\((?P<names>[a-zA-Z ]+)\s*:\s*(ℕ|Nat)\)")


def _deterministic_sanity(
    record: DeclarationRecord, provenance: Provenance
) -> list[CheckerFinding]:
    """Structural checks a program can make without reading the mathematics."""
    findings: list[CheckerFinding] = []
    statement = record.lean.statement or ""
    signature = statement.split(":=", 1)[0]
    source = record.source.statement

    # A size condition in the source with no corresponding bound in the signature.
    if (m := _SIZE_CONDITION_RE.search(source)) and not _SIZE_IN_LEAN_RE.search(signature):
        findings.append(CheckerFinding(
            id=_finding_id(SEMANTIC_SANITY_VERSION, record.id, "MISSING_CARDINALITY"),
            declaration_id=record.id, checker=CheckerName.SEMANTIC_SANITY,
            checker_version=SEMANTIC_SANITY_VERSION, status=FindingStatus.WARNING,
            category=FindingCategory.MISSING_CARDINALITY, severity=Severity.HIGH, confidence=1.0,
            message=(
                f"The source states a size condition ({m.group(0)!r}) but the Lean signature "
                f"carries no corresponding bound."
            ),
            evidence=[Evidence(kind="source_quote", value=source[:300]),
                      Evidence(kind="lean_quote", value=signature[:300])],
            requires_human=True, blocks_progression=False, provenance=provenance,
        ))

    # Numeric parameters with no lower bound anywhere in the signature.
    for m in _NUMERIC_BINDER_RE.finditer(signature):
        for name in m.group("names").split():
            if not re.search(rf"\b\d+\s*[<≤]\s*{re.escape(name)}\b|\b{re.escape(name)}\s*[<≤]", signature):
                findings.append(CheckerFinding(
                    id=_finding_id(SEMANTIC_SANITY_VERSION, record.id, "ZERO_PARAMETER", name),
                    declaration_id=record.id, checker=CheckerName.SEMANTIC_SANITY,
                    checker_version=SEMANTIC_SANITY_VERSION, status=FindingStatus.WARNING,
                    category=FindingCategory.ZERO_PARAMETER, severity=Severity.MEDIUM, confidence=1.0,
                    message=(
                        f"The natural-number parameter `{name}` has no lower bound, so the "
                        f"statement is asserted at `{name} = 0`. Natural subtraction and "
                        f"`0 ^ 0 = 1` make that case behave unlike the general one."
                    ),
                    evidence=[Evidence(kind="lean_quote", value=signature[:300])],
                    requires_human=False, blocks_progression=False, provenance=provenance,
                ))
    return findings


def check_semantic_sanity(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    provider: LLMProvider | None = None,
    prompt: Prompt | None = None,
    model: str | None = None,
) -> CheckerOutcome:
    """Is the statement vacuous or false in a degenerate case?"""
    started = time.monotonic()
    record = registry.require(declaration_id)
    provenance_det = Provenance(producer=SEMANTIC_SANITY_VERSION, corpus_version=registry.version)
    outcome = CheckerOutcome(checker=CheckerName.SEMANTIC_SANITY)
    findings = _deterministic_sanity(record, provenance_det)
    outcome.deterministic_findings = len(findings)

    if provider is not None and record.lean.statement:
        prompt = prompt or load_prompt("check-semantic", "declaration")
        dependencies = "\n".join(
            f"{dep.lean.name}: {dep.lean.statement}"
            for dep_id in registry.prerequisites(declaration_id, include_mathlib=False)
            if (dep := registry.resolve(dep_id)) and dep.lean.statement
        ) or "(none)"
        annotation = record.annotation
        request = LLMRequest(
            system=prompt.system,
            user=prompt.render(
                declaration_id=declaration_id,
                lean=record.lean.statement,
                source=record.source.statement,
                hypotheses="\n".join(f"- {h}" for h in (annotation.stated_hypotheses if annotation else []))
                or "(none recorded)",
                dependencies=dependencies,
            ),
            model=model or prompt.model or "claude-opus-5",
            max_tokens=prompt.max_tokens,
        )
        response, _ = call_with_retry(provider, request)
        provenance_llm = Provenance(
            producer=SEMANTIC_SANITY_VERSION, provider=response.provider, model=response.model,
            prompt_version=prompt.id, corpus_version=registry.version,
        )
        try:
            for raw in _parse_findings(response.text, CheckerName.SEMANTIC_SANITY):
                evidence = [Evidence(kind="lean_quote", value=str(raw.get("instantiation", "")))] if raw.get("instantiation") else [
                    Evidence(kind="lean_quote", value=(record.lean.statement or "")[:300])
                ]
                finding = _build_finding(
                    raw, declaration_id=declaration_id, checker=CheckerName.SEMANTIC_SANITY,
                    version=SEMANTIC_SANITY_VERSION, provenance=provenance_llm,
                    evidence=evidence, default_category=FindingCategory.BOUNDARY_CONDITION,
                )
                if finding is not None:
                    findings.append(finding)
                    outcome.model_findings += 1
        except ValueError as exc:
            outcome.warnings.append(str(exc))
        outcome.input_tokens = response.input_tokens
        outcome.output_tokens = response.output_tokens
        outcome.usd = response.usd

    outcome.findings = findings
    outcome.wall_ms = int((time.monotonic() - started) * 1000)
    return outcome
