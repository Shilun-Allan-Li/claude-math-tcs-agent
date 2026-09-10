"""Controlled vocabularies for pipeline artifacts.

Every member of every enum here corresponds to something actually observed in the
summer corpus (see `files/reports/`). Values are lowercase snake_case for machine use;
`TrustStatus`, `ReviewStatus` and `ProposalStatus` are uppercase because they are
status words a human reads directly in the CLI and in any UI client.
"""

from __future__ import annotations

from enum import StrEnum


class SourceItemKind(StrEnum):
    """What the textbook calls this item.

    Kept separate from :class:`LeanDeclarationKind`: the book's `definition` may become a
    Lean `def`, `abbrev`, `structure` or `Prop`, and an `exercise` may become a `theorem`.
    Conflating them is how source identity gets lost (report 01 §B2).
    """

    DEFINITION = "definition"
    THEOREM = "theorem"
    LEMMA = "lemma"
    COROLLARY = "corollary"
    PROPOSITION = "proposition"
    EXERCISE = "exercise"
    EXAMPLE = "example"
    CONSTRUCTION = "construction"
    NOTATION = "notation"
    REMARK = "remark"


#: Short codes used in stable identifiers. Fixed forever: changing one changes every ID.
KIND_CODE: dict[SourceItemKind, str] = {
    SourceItemKind.DEFINITION: "def",
    SourceItemKind.THEOREM: "thm",
    SourceItemKind.LEMMA: "lem",
    SourceItemKind.COROLLARY: "cor",
    SourceItemKind.PROPOSITION: "prop",
    SourceItemKind.EXERCISE: "ex",
    SourceItemKind.EXAMPLE: "exm",
    SourceItemKind.CONSTRUCTION: "con",
    SourceItemKind.NOTATION: "not",
    SourceItemKind.REMARK: "rem",
}

#: Kinds whose Lean realisation is a proof obligation rather than a construction.
THEOREM_LIKE: frozenset[SourceItemKind] = frozenset(
    {
        SourceItemKind.THEOREM,
        SourceItemKind.LEMMA,
        SourceItemKind.COROLLARY,
        SourceItemKind.PROPOSITION,
        SourceItemKind.EXERCISE,
    }
)


class LeanDeclarationKind(StrEnum):
    THEOREM = "theorem"
    LEMMA = "lemma"
    DEF = "def"
    ABBREV = "abbrev"
    STRUCTURE = "structure"
    INDUCTIVE = "inductive"
    INSTANCE = "instance"
    CLASS = "class"


#: Lean kinds that introduce an object rather than discharge a proof obligation.
OBJECT_KINDS: frozenset[LeanDeclarationKind] = frozenset(
    {
        LeanDeclarationKind.DEF,
        LeanDeclarationKind.ABBREV,
        LeanDeclarationKind.STRUCTURE,
        LeanDeclarationKind.INDUCTIVE,
        LeanDeclarationKind.INSTANCE,
        LeanDeclarationKind.CLASS,
    }
)


class SorryKind(StrEnum):
    """What an occurrence of ``sorry`` means.

    Report 02 §B4: the summer treated ``def f := sorry`` as interchangeable with
    ``theorem t := by sorry``. They are not. An unfinished *proof* leaves downstream
    results unproved; an unfinished *object* leaves them **vacuous** -- 13 opaque
    constants made 18+ theorems meaningless in one module.
    """

    NONE = "none"
    PROOF_PENDING = "proof_pending"
    OBJECT_PENDING = "object_pending"
    FIELD_PENDING = "field_pending"


class CompileStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    NOT_BUILT = "not_built"
    UNKNOWN = "unknown"


class TrustStatus(StrEnum):
    """Whether a declaration may be relied upon. Decided by Lean, never by an LLM."""

    FULLY_VERIFIED = "FULLY_VERIFIED"
    DIRECT_SORRY = "DIRECT_SORRY"
    TRANSITIVE_SORRY = "TRANSITIVE_SORRY"
    UNFINISHED_CONSTRUCTION = "UNFINISHED_CONSTRUCTION"
    BLOCKED_BY_UNTRUSTED_DEPENDENCY = "BLOCKED_BY_UNTRUSTED_DEPENDENCY"
    COMPILE_FAILURE = "COMPILE_FAILURE"
    UNKNOWN = "UNKNOWN"


#: Trust states a downstream declaration may safely build on.
TRUSTED_STATES: frozenset[TrustStatus] = frozenset({TrustStatus.FULLY_VERIFIED})

#: Trust states meaning "the statement is fine, the proof is not" -- safe to cite as a
#: black box in a sorry-ladder (report 04 §C1), unsafe to call verified.
STATEMENT_USABLE_STATES: frozenset[TrustStatus] = frozenset(
    {
        TrustStatus.FULLY_VERIFIED,
        TrustStatus.DIRECT_SORRY,
        TrustStatus.TRANSITIVE_SORRY,
    }
)


class MappingType(StrEnum):
    """How a Lean expression differs in form from its source expression."""

    NOTATION = "notation"
    RENAMING = "renaming"
    REPRESENTATION = "representation"
    SPECIALIZATION = "specialization"
    GENERALIZATION = "generalization"
    SEMANTIC_DEVIATION = "semantic_deviation"
    UNCERTAIN = "uncertain"


class SemanticStatus(StrEnum):
    """Whether the Lean form means the same thing as the source form."""

    EQUIVALENT = "equivalent"
    LIKELY_EQUIVALENT = "likely_equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    UNCERTAIN = "uncertain"


class ProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    NEEDS_DESIGN = "NEEDS_DESIGN"
    FAILED = "FAILED"


class CheckerName(StrEnum):
    LEAN_INTEGRITY = "lean_integrity"
    SOURCE_FIDELITY = "source_fidelity"
    LIBRARY_CONTEXT = "library_context"
    SEMANTIC_SANITY = "semantic_sanity"


class FindingStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


class FindingCategory(StrEnum):
    """Finding vocabulary, grouped by the checker that emits it.

    Seeded from the 37 categorised issues in `files/evidence/issues.jsonl` so that the
    historical findings can be replayed against the new schema without translation.
    """

    # -- lean_integrity (deterministic) --
    COMPILE_FAILURE = "COMPILE_FAILURE"
    PARSE_ERROR = "PARSE_ERROR"
    UNKNOWN_IDENTIFIER = "UNKNOWN_IDENTIFIER"
    IMPORT_FAILURE = "IMPORT_FAILURE"
    TYPECLASS_FAILURE = "TYPECLASS_FAILURE"
    DIRECT_SORRY = "DIRECT_SORRY"
    TRANSITIVE_SORRY = "TRANSITIVE_SORRY"
    UNFINISHED_CONSTRUCTION = "UNFINISHED_CONSTRUCTION"
    VACUOUS_DEPENDENCY = "VACUOUS_DEPENDENCY"
    AXIOM_TRUST = "AXIOM_TRUST"
    LINT = "LINT"

    # -- source_fidelity --
    RENAMING = "RENAMING"
    NOTATION_MAPPING = "NOTATION_MAPPING"
    REPRESENTATION_CHANGE = "REPRESENTATION_CHANGE"
    SPECIALIZATION = "SPECIALIZATION"
    GENERALIZATION = "GENERALIZATION"
    SEMANTIC_DEVIATION = "SEMANTIC_DEVIATION"
    MISSING_ASSUMPTION = "MISSING_ASSUMPTION"
    OVERSTRONG_ASSUMPTION = "OVERSTRONG_ASSUMPTION"
    OVERWEAK_CONCLUSION = "OVERWEAK_CONCLUSION"

    # -- library_context --
    DUPLICATE_DECLARATION = "DUPLICATE_DECLARATION"
    MATHLIB_DUPLICATION = "MATHLIB_DUPLICATION"
    STRONGER_RESULT_EXISTS = "STRONGER_RESULT_EXISTS"
    NAMING_CONFLICT = "NAMING_CONFLICT"
    ABSTRACTION_LEVEL = "ABSTRACTION_LEVEL"
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    UNNECESSARY_REINVENTION = "UNNECESSARY_REINVENTION"

    # -- semantic_sanity --
    EMPTY_TYPE = "EMPTY_TYPE"
    SINGLETON_CASE = "SINGLETON_CASE"
    TRIVIAL_CASE = "TRIVIAL_CASE"
    ZERO_PARAMETER = "ZERO_PARAMETER"
    VACUOUS_QUANTIFICATION = "VACUOUS_QUANTIFICATION"
    MISSING_NONEMPTY = "MISSING_NONEMPTY"
    MISSING_CARDINALITY = "MISSING_CARDINALITY"
    BOUNDARY_CONDITION = "BOUNDARY_CONDITION"
    SUSPICIOUS_ASSUMPTION = "SUSPICIOUS_ASSUMPTION"
    SUSPICIOUS_CONCLUSION = "SUSPICIOUS_CONCLUSION"

    # -- cross-cutting --
    SOURCE_PROVENANCE = "SOURCE_PROVENANCE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNCERTAIN = "UNCERTAIN"


class ReviewStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    AGENT_PASS = "AGENT_PASS"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVISION = "NEEDS_REVISION"


#: Decisions a human made. Rule 8: an agent may add findings but must never overwrite one.
HUMAN_DECISIONS: frozenset[ReviewStatus] = frozenset(
    {ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.NEEDS_REVISION}
)


class EdgeType(StrEnum):
    """Corpus-graph edge types.

    ``provenance`` on each edge (see :class:`pipeline.artifacts.models.graph.DependencyEdge`) decides
    whether it may gate progression: report 06 §E.2 -- only source-extracted and
    Lean-extracted edges are exact enough to block automatically.
    """

    INFORMAL_DEPENDENCY = "informal_dependency"
    SOURCE_CROSS_REFERENCE = "source_cross_reference"
    LEAN_LOCAL_DEPENDENCY = "lean_local_dependency"
    MATHLIB_DEPENDENCY = "mathlib_dependency"
    HELPER_DEPENDENCY = "helper_dependency"
    FORMALIZES = "formalizes"
    EXAMPLE_OF = "example_of"
    SUPERSEDES = "supersedes"


class EdgeProvenanceKind(StrEnum):
    SOURCE_EXTRACTED = "source_extracted"
    LEAN_EXTRACTED = "lean_extracted"
    AGENT_INFERRED = "agent_inferred"
    HUMAN_CONFIRMED = "human_confirmed"


#: Edge provenances trustworthy enough to gate progression without review.
GATING_PROVENANCE: frozenset[EdgeProvenanceKind] = frozenset(
    {
        EdgeProvenanceKind.SOURCE_EXTRACTED,
        EdgeProvenanceKind.LEAN_EXTRACTED,
        EdgeProvenanceKind.HUMAN_CONFIRMED,
    }
)


class HelperOrigin(StrEnum):
    """Why a helper lemma exists (report 04 §F). Determines where it should live."""

    BOOK_IMPLICIT = "book_implicit"
    LEAN_INFRASTRUCTURE = "lean_infrastructure"
    MATHLIB_GAP = "mathlib_gap"
    DECOMPOSITION = "decomposition"


class ProofOutcome(StrEnum):
    SUCCESS = "success"
    FAIL = "fail"
    ESCALATE = "escalate"
    STATEMENT_REVIEW_REQUIRED = "STATEMENT_REVIEW_REQUIRED"
    BUDGET_EXCEEDED = "budget_exceeded"


class Stage(StrEnum):
    INGEST = "ingest"
    ANNOTATE = "annotate"
    FORMALIZE = "formalize"
    CHECK = "check"
    REVIEW = "review"
    PROVE = "prove"
    INTEGRATE = "integrate"
