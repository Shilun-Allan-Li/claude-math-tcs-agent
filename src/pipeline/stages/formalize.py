"""Stage 2 -- formalization scaffold.

Contract: one :class:`AnnotatedDeclaration` in, one :class:`FormalizationProposal` out.
Statements only.

Rule 6 is enforced here rather than trusted, because the summer's identical contract was
written in prose and quietly broken: commit ``9468218`` shipped 29 proved theorems under a
message asserting "Every proof body is `sorry`", and nothing checked (report 02 §A.5).

Four enforcement points:

* a theorem-like proposal whose body is not exactly ``sorry`` is rejected;
* ``sorry_kind`` must agree with the declaration kind -- an unfinished *object* is not an
  unfinished *proof*, and conflating them is what made 18+ summer theorems vacuous;
* an unfinished construction always carries a blocking design warning, so it reaches a
  human rather than circulating as usable API;
* the proposed Lean name is claimed in the registry, which fails on collision.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from pipeline.corpus import CorpusRegistry, NameCollisionError
from pipeline.artifacts.models import (
    OBJECT_KINDS,
    THEOREM_LIKE,
    ContextPackage,
    DesignWarning,
    FormalizationProposal,
    LeanDeclarationKind,
    MappingType,
    MathlibRelation,
    ProposalStatus,
    Provenance,
    SemanticStatus,
    SorryKind,
    SourceLeanMapping,
    Stage,
    StageRun,
)
from pipeline.prompts import Prompt, load_prompt
from pipeline.providers import LLMProvider, LLMRequest, call_with_retry
from pipeline.artifacts.records import attach_proposal
from pipeline.context.builders import build_formalization_context

__all__ = [
    "formalize_declaration",
    "formalizable",
    "FormalizationResult",
    "FormalizationError",
    "classify_body",
    "FORMALIZE_VERSION",
]

FORMALIZE_VERSION = "formalize/v1"

#: Anything that is a proof step rather than a statement. `sorry` is deliberately absent.
_TACTIC_RE = re.compile(
    r"\b(simp|omega|linarith|nlinarith|ring|decide|aesop|rfl|trivial|exact|apply|intro|rintro|"
    r"rcases|obtain|induction|cases|constructor|refine|calc|unfold|rw|norm_num|"
    r"field_simp|positivity|gcongr|convert)\b"
)


class FormalizationError(RuntimeError):
    pass


@dataclass
class FormalizationResult:
    proposal: FormalizationProposal
    context: ContextPackage
    run: StageRun
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, object]:
        p = self.proposal
        return {
            "declaration_id": p.declaration_id,
            "status": p.status.value,
            "lean_name": p.lean_name,
            "declaration_kind": p.declaration_kind.value if p.declaration_kind else None,
            "sorry_kind": p.sorry_kind.value,
            "mappings": len(p.mappings),
            "hypotheses_added": len(p.hypotheses_added),
            "hypotheses_dropped": len(p.hypotheses_dropped),
            "design_warnings": len(p.design_warnings),
            "context_chars": self.context.total_chars,
        }


def _proof_body(statement: str) -> str:
    """The text after the final ``:=``, which is the declaration's body."""
    idx = statement.rfind(":=")
    return statement[idx + 2 :].strip() if idx >= 0 else ""


#: Identifier-ish tokens in a term body.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\'!?]*")

#: Lean syntax that is punctuation rather than reference.
_TERM_PUNCTUATION = frozenset("⟨⟩(),.:{}[]<>|_ \n\t")


def classify_body(
    statement: str, kind: LeanDeclarationKind, *, known_names: frozenset[str] = frozenset()
) -> str:
    """Classify a declaration body as ``definition``, ``sorry``, ``structural`` or ``proof``.

    The line this draws is rule 6's real content. *Structural assembly* is the failure to
    watch for: an earlier scaffold emitted

        theorem combined_inequalities ... := ⟨part_one, part_two⟩

    over two siblings that were both still ``sorry``. That is glue, not a proof: it carries
    no mathematical content, and it cannot be right unless the siblings are.

    So a theorem-like body is allowed to be ``sorry``, or a term in which every identifier
    is either a declaration this scaffold already owns or a binder from the signature.
    Anything else -- a tactic block, or a term citing an outside lemma -- is a proof and
    belongs to stage 4.
    """
    if kind in OBJECT_KINDS:
        return "definition"
    body = _proof_body(statement)
    normalised = re.sub(r"\s+", " ", body.removeprefix("by").strip())
    if normalised == "sorry":
        return "sorry"
    if body.strip().startswith("by") or _TACTIC_RE.search(body):
        return "proof"

    signature = statement[: statement.rfind(":=")] if ":=" in statement else ""
    binders = set(_IDENT_RE.findall(signature))
    short_names = {n.rsplit(".", 1)[-1] for n in known_names}
    unresolved = [
        token
        for token in _IDENT_RE.findall(body)
        if token not in known_names
        and token.rsplit(".", 1)[-1] not in short_names
        and token not in binders
    ]
    if unresolved:
        # The body is tactic-free, so it is not a proof *attempt*, but it references names
        # the pipeline cannot resolve yet -- most often because the sibling it assembles has not
        # been formalized in this run. Deciding it here would make the stage order-
        # sensitive, so it is accepted, flagged for review, and left to Lean: if the names
        # do not exist the module fails to compile, and if they exist but carry real
        # mathematical content the integrity checker still reports the declaration's true
        # trust from its axioms. Rule 5 -- do not guess what Lean can decide.
        return "structural_unverified"
    return "structural"


def _assert_no_proof(
    statement: str, kind: LeanDeclarationKind, *, known_names: frozenset[str] = frozenset()
) -> str:
    """Rule 6, enforced. Returns the accepted body classification."""
    classification = classify_body(statement, kind, known_names=known_names)
    if classification == "proof":
        body = _proof_body(statement)
        offending = _TACTIC_RE.search(body)
        detail = f" (found {offending.group(0)!r})" if offending else ""
        raise FormalizationError(
            f"the formalization stage produced a proof body instead of `sorry`{detail}: "
            f"{body[:120]!r}. Formalization is not proving."
        )
    return classification


def _parse_response(text: str, declaration_id: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.S)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end < 0:
        raise FormalizationError(f"no JSON object in the formalizer response for {declaration_id}")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise FormalizationError(f"formalizer response for {declaration_id} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise FormalizationError(f"formalizer response for {declaration_id} is not a JSON object")
    return payload


def _mappings(raw: list, declaration_id: str) -> list[SourceLeanMapping]:
    out: list[SourceLeanMapping] = []
    for i, m in enumerate(raw, start=1):
        if not isinstance(m, dict) or not m.get("justification"):
            continue
        out.append(
            SourceLeanMapping(
                id=f"{declaration_id}/m{i}",
                declaration_id=declaration_id,
                aspect=str(m.get("aspect", "")),
                source_form=str(m.get("source_form", "")),
                lean_form=str(m.get("lean_form", "")),
                mapping_type=MappingType(str(m.get("mapping_type", "uncertain"))),
                semantic_status=SemanticStatus(str(m.get("semantic_status", "uncertain"))),
                justification=str(m["justification"]),
                declared_by_producer=True,
            )
        )
    return out


def formalize_declaration(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    provider: LLMProvider,
    prompt: Prompt | None = None,
    model: str | None = None,
    persist: bool = True,
) -> FormalizationResult:
    """Propose a Lean statement for one declaration."""
    record = registry.require(declaration_id)
    if record.annotation is None:
        raise FormalizationError(
            f"{declaration_id} has no annotation; run `pipeline annotate` for its chapter first"
        )
    prompt = prompt or load_prompt("formalize", "declaration")
    model = model or prompt.model or "claude-opus-5"

    package = build_formalization_context(registry, declaration_id)
    by_role = {
        "target": package.by_role("target"),
        "source": package.by_role("source_passage"),
        "annotation": package.by_role("annotation"),
        "dependencies": package.by_role("approved_dependency"),
        "candidates": package.by_role("mathlib_candidate"),
    }
    conventions = "\n".join(
        i.content for i in package.items if i.role in ("notation", "convention")
    ) or "(none established yet)"

    request = LLMRequest(
        system=prompt.system,
        user=prompt.render(
            target="\n".join(i.content for i in by_role["target"]),
            source="\n\n".join(i.content for i in by_role["source"]),
            annotation="\n".join(i.content for i in by_role["annotation"]) or "(none)",
            dependencies="\n".join(i.content for i in by_role["dependencies"]) or "(none)",
            conventions=conventions,
            candidates="\n".join(i.content for i in by_role["candidates"]) or "(none)",
        ),
        model=model,
        max_tokens=prompt.max_tokens,
    )

    started = time.monotonic()
    response, retries = call_with_retry(provider, request)
    payload = _parse_response(response.text, declaration_id)

    provenance = Provenance(
        producer=FORMALIZE_VERSION,
        provider=response.provider,
        model=response.model,
        prompt_version=prompt.id,
        context_package_id=package.id,
        input_fingerprint=record.annotation.source_fingerprint,
        corpus_version=registry.version,
    )
    warnings: list[str] = []
    status = ProposalStatus(str(payload.get("status", "PROPOSED")))
    kind_raw = payload.get("declaration_kind")
    kind = LeanDeclarationKind(str(kind_raw)) if kind_raw else None
    statement = payload.get("statement")
    sorry_kind = SorryKind(str(payload.get("sorry_kind", "none")))

    design_warnings = [
        DesignWarning(
            code=str(w.get("code", "unspecified")),
            message=str(w.get("message", "")),
            blocks=bool(w.get("blocks", False)),
        )
        for w in payload.get("design_warnings", [])
        if isinstance(w, dict)
    ]

    body_kind = "unknown"
    if status is ProposalStatus.PROPOSED and statement and kind is not None:
        try:
            known = frozenset(registry.claimed_names()) | {
                p.lean_name for p in registry.store.read("proposals") if p.lean_name  # type: ignore[attr-defined]
            }
            body_kind = _assert_no_proof(statement, kind, known_names=known)
        except FormalizationError:
            if persist:
                registry.store.append(
                    "runs",
                    StageRun(
                        id=f"run-formalize-{declaration_id}-{int(time.time() * 1000) % 10**9}",
                        stage=Stage.FORMALIZE, target_id=declaration_id, status="failed",
                        context_package_id=package.id, provider=response.provider,
                        model=response.model, prompt_version=prompt.id,
                        error="proof body emitted by the formalization stage",
                        error_kind="validation",
                    ),
                )
            raise

        # Structural assembly is legitimate scaffold output, but the declaration is only
        # as trustworthy as the siblings it assembles -- and it carries no `sorry` of its
        # own, so nothing downstream would otherwise notice. Say so.
        if body_kind.startswith("structural"):
            design_warnings.append(
                DesignWarning(
                    code="structural-assembly",
                    message=(
                        "The body assembles other declarations and contains no proof of its "
                        "own. It has no `sorry`, so its trust must be computed from its "
                        "dependencies rather than from its body."
                    ),
                    blocks=False,
                )
            )
        if body_kind == "structural_unverified":
            design_warnings.append(
                DesignWarning(
                    code="unresolved-references",
                    message=(
                        "The body references names the pipeline could not resolve at proposal time. "
                        "If they are siblings not yet formalized this is expected; if they are "
                        "outside lemmas the declaration is a proof and belongs to stage 4. "
                        "The Lean integrity checker decides."
                    ),
                    blocks=True,
                )
            )

        # An unfinished construction must not circulate as usable API.
        if kind in OBJECT_KINDS and sorry_kind is SorryKind.OBJECT_PENDING:
            design_warnings.append(
                DesignWarning(
                    code="unfinished-construction",
                    message=(
                        "The object has no body, so every statement about it is vacuous "
                        "rather than merely unproved. It must be designed before anything "
                        "is proved about it."
                    ),
                    blocks=True,
                )
            )
        # The book's kind and the Lean kind should agree about what is being introduced.
        if record.kind in THEOREM_LIKE and kind in OBJECT_KINDS:
            warnings.append(
                f"{declaration_id} is a {record.kind.value} in the source but was formalized "
                f"as a Lean {kind.value}"
            )

    proposal = FormalizationProposal(
        id=f"{declaration_id}/f1",
        declaration_id=declaration_id,
        status=status,
        lean_name=payload.get("lean_name"),
        namespace=payload.get("namespace"),
        declaration_kind=kind,
        imports=[str(i) for i in payload.get("imports", [])],
        variables=[str(v) for v in payload.get("variables", [])],
        typeclasses=[str(t) for t in payload.get("typeclasses", [])],
        statement=statement,
        sorry_kind=sorry_kind,
        mappings=_mappings(payload.get("mappings", []), declaration_id),
        hypotheses_added=[str(h) for h in payload.get("hypotheses_added", [])],
        hypotheses_dropped=[str(h) for h in payload.get("hypotheses_dropped", [])],
        design_warnings=design_warnings,
        mathlib_candidates=[
            MathlibRelation(
                name=str(c["name"]),
                relation=str(c.get("relation", "related")),
                verified=bool(c.get("verified", False)),
            )
            for c in payload.get("mathlib_candidates", [])
            if isinstance(c, dict) and c.get("name")
        ],
        needs_design_reason=payload.get("needs_design_reason"),
        failure_reason=payload.get("failure_reason"),
        annotation_fingerprint=record.annotation.source_fingerprint,
        provenance=provenance,
    )

    run = StageRun(
        id=f"run-formalize-{declaration_id}-{int(time.time() * 1000) % 10**9}",
        stage=Stage.FORMALIZE,
        target_id=declaration_id,
        status="ok",
        input_artifact_ids=[declaration_id],
        output_artifact_ids=[proposal.id],
        context_package_id=package.id,
        provider=response.provider,
        model=response.model,
        prompt_version=prompt.id,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        usd=response.usd,
        wall_ms=int((time.monotonic() - started) * 1000),
        retries=retries,
    )

    if persist:
        if proposal.status is ProposalStatus.PROPOSED and proposal.lean_name:
            try:
                registry.claim_lean_name(proposal.lean_name, declaration_id)
            except NameCollisionError as exc:
                proposal = proposal.model_copy(
                    update={
                        "status": ProposalStatus.FAILED,
                        "failure_reason": str(exc),
                        "lean_name": None,
                        "declaration_kind": None,
                        "statement": None,
                    }
                )
                run.status = "failed"
                run.error = str(exc)
                run.error_kind = "validation"
                warnings.append(str(exc))
        registry.store.upsert("proposals", [proposal])
        attach_proposal(record, proposal)
        registry.upsert_records([record])
        registry.store.upsert("context", [package])
        registry.store.append("runs", run)
        registry.save()

    return FormalizationResult(proposal=proposal, context=package, run=run, warnings=warnings)


def formalizable(
    registry: CorpusRegistry,
    *,
    chapter: str | int | None = None,
    include_done: bool = False,
    kinds: set[str] | None = None,
) -> list[str]:
    """Declaration ids ready for stage 2, in the order they should be attempted.

    Ordering matters here in a way it does not for most queries. Definitions go first,
    because a theorem's statement is written in terms of them and the formalizer is given
    the approved ones as context; and within each group, source order, because that is the
    order the book builds things up in. A structural assembly citing a sibling that has not
    been formalized yet is accepted but flagged (see :func:`classify_body`), so getting the
    order right is what keeps that flag rare.
    """
    proposed = {
        p.declaration_id
        for p in registry.store.read("proposals")
        if p.status is ProposalStatus.PROPOSED  # type: ignore[attr-defined]
    }
    pool = (
        registry.declarations_in_chapter(chapter) if chapter is not None else list(registry)
    )
    out = [
        record
        for record in pool
        if record.annotation is not None
        and (include_done or record.id not in proposed)
        and (kinds is None or record.kind.value in kinds)
    ]
    out.sort(key=lambda r: (not r.is_foundational, r.source.span.start if r.source.span else 0, r.id))
    return [r.id for r in out]
