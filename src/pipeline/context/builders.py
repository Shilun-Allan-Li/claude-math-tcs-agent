"""Context builders.

Rule 4, made concrete. A context package is assembled by **querying the corpus graph**,
never by replaying conversation or concatenating prior chapters.

Report 06 §F measured the gap this closes: the summer's scaffold stage read whole chapters
(up to 3,356 lines) and its proof loop read a whole 1,573-line Lean file to emit at most
30 tactic lines, while the information actually needed across a chapter boundary was four
import edges, about thirty reusable declarations, and a notation table.

Every builder here is deterministic and records exactly what it supplied, so a client can
answer "what did the agent actually see?" after the fact -- which a conversation cannot.
"""

from __future__ import annotations

import hashlib
import json

from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.models import (
    ChapterDigest,
    ContextItem,
    ContextPackage,
    Provenance,
    SourceItem,
    Stage,
)

__all__ = [
    "build_annotation_context",
    "build_formalization_context",
    "build_proof_context",
    "package_id",
    "DEFAULT_ANNOTATION_BUDGET_CHARS",
    "DEFAULT_FORMALIZATION_BUDGET_CHARS",
    "DEFAULT_PROOF_BUDGET_CHARS",
]

#: Ceiling for an annotation package. Not a hard limit on the source text itself -- the
#: chapter under annotation is the work -- but on everything *retrieved around* it.
DEFAULT_ANNOTATION_BUDGET_CHARS = 24_000

#: Ceiling for a formalization package. Report 02 §E sizes this at roughly 150 lines:
#: the declaration, its resolved dependencies as *statements only*, the notation
#: registry, conventions, and pre-filtered Mathlib candidates. The summer sent a
#: 600-3,356 line chapter for the same job.
DEFAULT_FORMALIZATION_BUDGET_CHARS = 12_000

#: Ceiling for a proof package. Report 04 §E sizes this at roughly 210 lines and makes
#: one point non-negotiable: it must **not grow with attempt number**. The summer's
#: proof loop read a whole 1,573-line Lean file to emit at most thirty tactic lines, and
#: its repair path appended to that.
DEFAULT_PROOF_BUDGET_CHARS = 14_000

#: Failed strategies are carried as labels, never as transcripts, and capped.
MAX_FAILED_STRATEGIES = 5


def package_id(stage: Stage, target_id: str, items: list[ContextItem]) -> str:
    """Deterministic id over what the package contains.

    Two runs that retrieve the same context get the same id, so a cached stage result is
    addressable and an agent run can be tied to the exact bytes it was given.
    """
    blob = json.dumps(
        [[i.role, i.ref, hashlib.sha256(i.content.encode()).hexdigest()[:16]] for i in items],
        sort_keys=True,
    )
    digest = hashlib.sha256(f"{stage.value}|{target_id}|{blob}".encode()).hexdigest()[:24]
    return f"cp-{digest}"


def _digest_items(digests: list[ChapterDigest]) -> list[ContextItem]:
    """Render prior-chapter digests as context items.

    Only definitions, named results, notation and a one-paragraph summary cross a chapter
    boundary. Prose, proof sketches and difficulty grades do not: report 01 §E.5 found no
    consumer for them.
    """
    items: list[ContextItem] = []
    for digest in digests:
        items.append(
            ContextItem(
                role="digest",
                ref=digest.chapter_id,
                content=f"Chapter {digest.chapter} ({digest.title}): {digest.summary}",
                reason="prior chapter summary",
            )
        )
        for d in digest.definitions:
            items.append(
                ContextItem(
                    role="approved_dependency",
                    ref=d.declaration_id,
                    content=f"[{d.kind}] {d.name or d.label or d.declaration_id}: {d.statement}",
                    reason=f"definition exported by chapter {digest.chapter}",
                )
            )
        for r in digest.results:
            items.append(
                ContextItem(
                    role="approved_dependency",
                    ref=r.declaration_id,
                    content=f"[{r.kind} {r.label or ''}] {r.statement}",
                    reason=f"named result exported by chapter {digest.chapter}",
                )
            )
        for n in digest.notation:
            items.append(
                ContextItem(
                    role="notation",
                    ref=f"{digest.chapter_id}/{n.symbol}",
                    content=f"{n.symbol} = {n.meaning}" + (f"  [Lean: {n.lean}]" if n.lean else ""),
                    reason=f"notation established in chapter {digest.chapter}",
                )
            )
    return items


def build_annotation_context(
    registry: CorpusRegistry,
    chapter: str,
    *,
    chapter_markdown: str,
    chapter_title: str,
    source_items: list[SourceItem],
    prior_digests: list[ChapterDigest] | None = None,
    referenced_ids: list[str] | None = None,
    budget_chars: int = DEFAULT_ANNOTATION_BUDGET_CHARS,
) -> ContextPackage:
    """Assemble the context for annotating one chapter.

    Retrieved, in order of specificity:

    1. the chapter's own Markdown (the work itself),
    2. the deterministically extracted items, so the agent annotates rather than re-finds,
    3. **only the prior-chapter declarations this chapter actually cites**, resolved from
       the source cross-reference edges already in the graph,
    4. digests of chapters this one references -- never all prior chapters,
    5. the project notation registry and conventions.

    Step 3 is the point. Chapter 3 cites exactly two chapter-2 results; it does not need
    chapter 2, let alone chapters 1 and 2 in full.
    """
    prior_digests = prior_digests or []
    items: list[ContextItem] = [
        ContextItem(
            role="source_passage",
            ref=f"chapter-{chapter}",
            content=chapter_markdown,
            reason="the chapter being annotated",
        )
    ]

    for item in source_items:
        items.append(
            ContextItem(
                role="target",
                ref=item.id,
                content=json.dumps(
                    {
                        "declaration_id": item.id,
                        "kind": item.kind.value,
                        "label": item.label,
                        "section": item.section,
                        "printed_page": item.span.printed_page if item.span else None,
                        "statement": item.statement,
                        "has_printed_proof": bool(item.proof),
                    },
                    ensure_ascii=False,
                ),
                reason="deterministically extracted item to annotate",
            )
        )

    # Only the specific prior declarations this chapter cites.
    cited = set(referenced_ids or [])
    if not cited:
        for item in source_items:
            for target in registry.prerequisites(item.id):
                if not target.startswith(f"bm-ch{chapter}-"):
                    cited.add(target)
    for ref in sorted(cited):
        record = registry.resolve(ref)
        if record is None:
            items.append(
                ContextItem(
                    role="approved_dependency",
                    ref=ref,
                    content=f"[not in corpus] {ref}",
                    reason="cited by this chapter but not yet ingested",
                )
            )
            continue
        items.append(
            ContextItem(
                role="approved_dependency",
                ref=ref,
                content=f"[{record.kind.value} {record.source.label or ''}] {record.source.statement}",
                reason="cited by a declaration in this chapter",
            )
        )

    # Digests only for chapters this one references.
    cited_chapters = {r.split("-")[1] for r in cited if "-" in r}
    relevant = [d for d in prior_digests if f"ch{d.chapter}" in cited_chapters]
    items.extend(_digest_items(relevant))

    for symbol, entry in sorted(registry.notation().items()):
        items.append(
            ContextItem(
                role="notation",
                ref=symbol,
                content=f"{symbol} = {entry.meaning}" + (f"  [Lean: {entry.lean}]" if entry.lean else ""),
                reason="project notation registry",
            )
        )
    for key, value in sorted(registry.conventions().items()):
        items.append(
            ContextItem(role="convention", ref=key, content=f"{key}: {value}",
                        reason="project convention")
        )

    return ContextPackage(
        id=package_id(Stage.ANNOTATE, f"chapter-{chapter}", items),
        stage=Stage.ANNOTATE,
        target_id=f"chapter-{chapter}",
        items=items,
        corpus_version=registry.version,
        budget_chars=budget_chars,
        provenance=Provenance(producer="context_builder/v1", corpus_version=registry.version),
    )


def build_formalization_context(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    budget_chars: int = DEFAULT_FORMALIZATION_BUDGET_CHARS,
    max_dependencies: int = 8,
) -> ContextPackage:
    """Assemble the context for formalizing one declaration.

    Contains only what report 02 §E found this stage actually needs:

    1. the target declaration -- source statement, label, page,
    2. its annotation IR, including the stated hypotheses,
    3. the approved prior declarations it depends on, **as statements only**, never as
       proofs, and never more than ``max_dependencies`` of them,
    4. the project notation registry and conventions,
    5. the Mathlib candidates the annotator already resolved,
    6. the Lean names already claimed, so the formalizer cannot propose a colliding one.

    Item 6 is what makes the registry's write barrier cooperative rather than merely
    punitive: the formalizer is told what is taken before it chooses.
    """
    record = registry.require(declaration_id)
    items: list[ContextItem] = [
        ContextItem(
            role="target",
            ref=record.id,
            content=json.dumps(
                {
                    "declaration_id": record.id,
                    "kind": record.kind.value,
                    "label": record.source.label,
                    "name": record.source.name,
                    "section": record.source.section,
                    "printed_page": record.source.span.printed_page if record.source.span else None,
                },
                ensure_ascii=False,
            ),
            reason="the declaration being formalized",
        ),
        ContextItem(
            role="source_passage",
            ref=f"{record.id}/statement",
            content=record.source.statement,
            reason="verbatim source statement",
        ),
    ]
    if record.source.proof:
        items.append(
            ContextItem(
                role="source_passage",
                ref=f"{record.id}/proof",
                content=record.source.proof,
                reason="the book's printed proof, for hypothesis discovery only",
            )
        )

    annotation = record.annotation
    if annotation is not None:
        items.append(
            ContextItem(
                role="annotation",
                ref=f"{record.id}/annotation",
                content=json.dumps(
                    {
                        "stated_hypotheses": annotation.stated_hypotheses,
                        "conclusion": annotation.conclusion,
                        "terminology": annotation.terminology,
                        "formalization_hints": annotation.formalization_hints,
                        "local_definition_hints": annotation.local_definition_hints,
                        "questions": [q.question for q in annotation.questions],
                    },
                    ensure_ascii=False,
                ),
                reason="annotation IR for this declaration",
            )
        )
        for candidate in annotation.mathlib_candidates:
            items.append(
                ContextItem(
                    role="mathlib_candidate",
                    ref=candidate.name,
                    content=f"{candidate.name} [{candidate.status}]"
                    + (f" — {candidate.note}" if candidate.note else ""),
                    reason="Mathlib candidate resolved during annotation",
                )
            )

    # Dependencies, statements only. Ordered so the ones the annotation named come first.
    named = list(annotation.local_definition_hints) if annotation else []
    dependency_ids: list[str] = []
    for dep in registry.prerequisites(declaration_id, include_mathlib=False):
        dependency_ids.append(dep)
    for hint in named:
        for candidate in registry:
            if candidate.source.name and candidate.source.name.lower() == hint.lower():
                if candidate.id not in dependency_ids:
                    dependency_ids.append(candidate.id)
    for dep_id in dependency_ids[:max_dependencies]:
        dep = registry.resolve(dep_id)
        if dep is None:
            continue
        lean = f"  Lean: `{dep.lean.name}`" if dep.lean.name else "  Lean: (not yet formalized)"
        items.append(
            ContextItem(
                role="approved_dependency",
                ref=dep.id,
                content=(
                    f"[{dep.kind.value} {dep.source.label or dep.source.name or ''}] "
                    f"{dep.source.statement}\n{lean}  trust: {dep.trust.status.value}"
                ),
                reason="dependency of the target",
            )
        )

    for symbol, entry in sorted(registry.notation().items()):
        items.append(
            ContextItem(
                role="notation",
                ref=symbol,
                content=f"{symbol} = {entry.meaning}" + (f"  [Lean: {entry.lean}]" if entry.lean else ""),
                reason="project notation registry",
            )
        )
    for key, value in sorted(registry.conventions().items()):
        items.append(
            ContextItem(role="convention", ref=key, content=f"{key}: {value}", reason="project convention")
        )

    claimed = sorted(registry.claimed_names())
    if claimed:
        items.append(
            ContextItem(
                role="convention",
                ref="claimed_lean_names",
                content="Already claimed, do not reuse: " + ", ".join(claimed),
                reason="registry name barrier",
            )
        )

    return ContextPackage(
        id=package_id(Stage.FORMALIZE, declaration_id, items),
        stage=Stage.FORMALIZE,
        target_id=declaration_id,
        items=items,
        corpus_version=registry.version,
        budget_chars=budget_chars,
        provenance=Provenance(producer="context_builder/v1", corpus_version=registry.version),
    )


def build_proof_context(
    registry: CorpusRegistry,
    declaration_id: str,
    *,
    diagnostics: list[str] | None = None,
    failed_strategies: list[str] | None = None,
    budget_chars: int = DEFAULT_PROOF_BUDGET_CHARS,
    max_dependencies: int = 8,
    max_candidates: int = 8,
) -> ContextPackage:
    """Assemble the context for proving one declaration.

    Contents, and why each is here (report 04 §E):

    1. the **approved** Lean statement, plus an explicit instruction not to change it;
    2. the book's proof sketch and steps -- the summer's one instrumented session found
       the informal strategy correct on the first attempt for all three lemmas it closed;
    3. approved local definitions, verbatim, because a proof needs to unfold them;
    4. sibling lemmas as **signatures only**: citing a still-``sorry`` sibling as a black
       box is the sorry ladder working as intended, and its proof is not needed to do so;
    5. the cached Mathlib candidates, *including* the ones marked missing -- knowing a
       lemma does not exist prevents a doomed search;
    6. the current Lean diagnostics;
    7. previously failed strategies as **labels**, capped, never as transcripts.

    Item 7 is what keeps the package flat across attempts. A repair worker that receives
    the whole history of its own failures is the growth mode report 06 §C measured.
    """
    record = registry.require(declaration_id)
    if not record.lean.statement:
        raise ValueError(f"{declaration_id} has no Lean statement to prove")

    items: list[ContextItem] = [
        ContextItem(
            role="target", ref=record.id,
            content=record.lean.statement,
            reason="the approved statement; the proof body is the only thing that may change",
        ),
        ContextItem(
            role="convention", ref="immutability",
            content=(
                "DO NOT CHANGE THE STATEMENT. If it appears wrong, return "
                "STATEMENT_REVIEW_REQUIRED with the reason instead of altering it."
            ),
            reason="rule 7",
        ),
        ContextItem(
            role="source_passage", ref=f"{record.id}/statement",
            content=record.source.statement,
            reason="what the book states",
        ),
    ]
    if record.source.proof:
        items.append(ContextItem(
            role="source_passage", ref=f"{record.id}/proof",
            content=record.source.proof, reason="the book's printed proof",
        ))

    annotation = record.annotation
    if annotation is not None:
        sketch = {
            "proof_strategy": annotation.proof_strategy,
            "proof_steps": [f"{s.index}. {s.text}" for s in annotation.proof_steps],
            "formalization_hints": annotation.formalization_hints,
        }
        items.append(ContextItem(
            role="annotation", ref=f"{record.id}/sketch",
            content=json.dumps(sketch, ensure_ascii=False),
            reason="informal proof sketch",
        ))
        for candidate in annotation.mathlib_candidates[:max_candidates]:
            items.append(ContextItem(
                role="mathlib_candidate", ref=candidate.name,
                content=f"{candidate.name} [{candidate.status}]"
                + (f" — {candidate.note}" if candidate.note else ""),
                reason="cached Mathlib candidate"
                + (" (recorded as MISSING: do not search for it)"
                   if candidate.status == "missing" else ""),
            ))

    for dependency_id in registry.prerequisites(declaration_id, include_mathlib=False)[:max_dependencies]:
        dependency = registry.resolve(dependency_id)
        if dependency is None or not dependency.lean.statement:
            continue
        # Definitions go in verbatim -- a proof must be able to unfold them. Theorems go in
        # as signatures only: their proofs are not needed to cite them.
        if dependency.is_foundational:
            content = dependency.lean.statement
            reason = "approved definition, verbatim (needed to unfold)"
        else:
            content = dependency.lean.statement.split(":=", 1)[0].rstrip()
            reason = f"approved lemma, signature only [{dependency.trust.status.value}]"
        items.append(ContextItem(role="approved_dependency", ref=dependency.id,
                                 content=content, reason=reason))

    for line in diagnostics or []:
        items.append(ContextItem(role="diagnostics", ref=f"{record.id}/lean",
                                 content=line, reason="current Lean diagnostic"))
    for label in (failed_strategies or [])[-MAX_FAILED_STRATEGIES:]:
        items.append(ContextItem(role="prior_attempt", ref=f"{record.id}/failed",
                                 content=label,
                                 reason="failed strategy, as a label (never a transcript)"))

    return ContextPackage(
        id=package_id(Stage.PROVE, declaration_id, items),
        stage=Stage.PROVE,
        target_id=declaration_id,
        items=items,
        corpus_version=registry.version,
        budget_chars=budget_chars,
        provenance=Provenance(producer="context_builder/v1", corpus_version=registry.version),
    )
