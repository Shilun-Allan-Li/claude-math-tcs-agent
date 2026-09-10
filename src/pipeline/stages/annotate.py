"""Stage 1 -- mathematical annotation.

Contract: **one chapter in, annotated Markdown plus a validated
:class:`AnnotatedDeclaration` IR out**, per section, with a bounded context package.

Three design decisions, each from the forensic study:

* **The agent annotates; the program assigns identity.** Labels, sections, pages and spans
  are computed deterministically (stage 0). For definitions the book does not number, the
  agent must return a *verbatim quote*, which the program locates in the source to derive
  the span, the page and the ordinal. A paraphrase is rejected. Identity therefore never
  depends on model wording, which is rule 2.
* **Section-sized requests.** The unit of work is a section, not a chapter and certainly
  not an accumulated conversation. Report 06 §D: chapter-sized units with no shared
  registry produced twelve colliding declaration names.
* **The annotator may not write Lean proofs.** Enforced by rejecting any response whose
  Lean-shaped fields contain tactic syntax.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from pipeline.corpus.config import ChapterConfig, load_corpus
from pipeline.corpus import CorpusRegistry
from pipeline.corpus.ids import content_fingerprint, declaration_id
from pipeline.artifacts.models import (
    AnnotatedDeclaration,
    ChapterDigest,
    ContextPackage,
    DependencyEdge,
    EdgeProvenance,
    EdgeProvenanceKind,
    EdgeType,
    ExportedDeclaration,
    InformalDependency,
    MathlibCandidate,
    NotationEntry,
    OpenQuestion,
    ProofStep,
    Provenance,
    SourceItem,
    SourceItemKind,
    SourceSpan,
    Stage,
    StageRun,
)
from pipeline.prompts import Prompt, load_prompt
from pipeline.providers import LLMProvider, LLMRequest, call_with_retry
from pipeline.artifacts.records import attach_annotation, record_from_source_item
from pipeline.context.builders import build_annotation_context
from pipeline.stages.cross_references import REFERENCE_RE, parse_reference

__all__ = ["annotate_chapter", "AnnotationResult", "AnnotationError", "split_sections", "ANNOTATE_VERSION"]

ANNOTATE_VERSION = "annotate/v1"

#: Lean tactic syntax. The annotator proposing any of this is a contract violation, not a
#: stylistic quibble: report 02 §A.5 shows what an unenforced "statements only" contract
#: produces.
_TACTIC_RE = re.compile(
    r"\b(by\s+(simp|omega|linarith|ring|decide|aesop|exact|apply|rfl)|"
    r":=\s*by\b|\bsorry\b|\brintro\b|\brcases\b|\bobtain\b)"
)

_SECTION_HEADING_RE = re.compile(r"^#{2,4}\s+(?P<num>\d+(?:\.\d+)*)\s+(?P<title>.+?)\s*$", re.M)


class AnnotationError(RuntimeError):
    pass


@dataclass
class AnnotationResult:
    chapter: str
    annotations: list[AnnotatedDeclaration]
    discovered_definitions: list[SourceItem]
    edges: list[DependencyEdge]
    notation: list[NotationEntry]
    digest: ChapterDigest
    context_packages: list[ContextPackage]
    runs: list[StageRun]
    markdown: str
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, object]:
        return {
            "chapter": self.chapter,
            "annotated": len(self.annotations),
            "definitions_discovered": len(self.discovered_definitions),
            "informal_edges": len(self.edges),
            "notation": len(self.notation),
            "context_packages": len(self.context_packages),
            "context_chars": sum(p.total_chars for p in self.context_packages),
            "usd": round(sum(r.usd or 0 for r in self.runs), 4),
            "warnings": len(self.warnings),
        }


def split_sections(markdown: str) -> list[tuple[str, str, str]]:
    """Split a chapter into ``(section_number, title, text)``.

    Text before the first numbered heading is attached to a synthetic ``"0"`` section so
    that a chapter preamble is never silently dropped.
    """
    matches = list(_SECTION_HEADING_RE.finditer(markdown))
    if not matches:
        return [("0", "", markdown)]
    out: list[tuple[str, str, str]] = []
    if matches[0].start() > 0:
        head = markdown[: matches[0].start()].strip()
        if head:
            out.append(("0", "preamble", head))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        out.append((m.group("num"), m.group("title"), markdown[m.start() : end]))
    return out


def _reject_lean_proofs(payload: dict, section: str) -> None:
    """Rule 6, enforced at the stage boundary rather than trusted."""
    blob = json.dumps(payload, ensure_ascii=False)
    match = _TACTIC_RE.search(blob)
    if match:
        raise AnnotationError(
            f"annotator emitted Lean tactic syntax in section {section}: {match.group(0)!r}. "
            "The annotation stage must not write proofs."
        )


def _parse_response(text: str, section: str) -> dict:
    """Extract the JSON object from a model response, failing loudly."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.S)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end < 0:
        raise AnnotationError(f"no JSON object in the annotator response for section {section}")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AnnotationError(f"annotator response for section {section} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AnnotationError(f"annotator response for section {section} is not a JSON object")
    _reject_lean_proofs(payload, section)
    return payload


def _dependency(raw: dict) -> InformalDependency:
    return InformalDependency(
        raw_reference=str(raw.get("raw_reference", "")).strip(),
        role=str(raw.get("role", "uses")),
        target_id=None,
        resolved=False,
    )


def _resolve_dependency(dep: InformalDependency, corpus: str, registry: CorpusRegistry) -> InformalDependency:
    """Resolve a prose citation to a declaration id, using the same parser stage 0 uses."""
    m = REFERENCE_RE.search(dep.raw_reference)
    if not m:
        return dep
    kind, label = parse_reference(m)
    chapter = label.split(".", 1)[0]
    candidate = declaration_id(corpus, chapter, kind, label=label)
    record = registry.resolve(candidate)
    dep.target_id = candidate
    dep.resolved = record is not None
    return dep


def _annotation_from(
    raw: dict,
    *,
    chapter_id: str,
    kind: SourceItemKind,
    source_fingerprint: str,
    provenance: Provenance,
    corpus: str,
    registry: CorpusRegistry,
) -> AnnotatedDeclaration:
    deps = [
        _resolve_dependency(_dependency(d), corpus, registry)
        for d in raw.get("informal_dependencies", [])
        if isinstance(d, dict)
    ]
    return AnnotatedDeclaration(
        declaration_id=raw["declaration_id"],
        chapter_id=chapter_id,
        kind=kind,
        stated_hypotheses=[str(h) for h in raw.get("stated_hypotheses", [])],
        conclusion=raw.get("conclusion"),
        concepts=[str(c) for c in raw.get("concepts", [])],
        terminology=[str(t) for t in raw.get("terminology", [])],
        informal_dependencies=deps,
        proof_strategy=raw.get("proof_strategy"),
        proof_steps=[
            ProofStep(index=int(s["index"]), text=str(s["text"]), uses=[str(u) for u in s.get("uses", [])])
            for s in raw.get("proof_steps", [])
            if isinstance(s, dict) and "index" in s and "text" in s
        ],
        formalization_hints=[str(h) for h in raw.get("formalization_hints", [])],
        mathlib_candidates=[
            MathlibCandidate(
                name=str(c["name"]),
                status=str(c.get("status", "uncertain")),
                note=c.get("note"),
            )
            for c in raw.get("mathlib_candidates", [])
            if isinstance(c, dict) and c.get("name")
        ],
        local_definition_hints=[str(h) for h in raw.get("local_definition_hints", [])],
        figure_dependencies=[str(f) for f in raw.get("figure_dependencies", [])],
        questions=[
            OpenQuestion(
                question=str(q["question"]),
                blocks_formalization=bool(q.get("blocks_formalization", False)),
            )
            for q in raw.get("questions", [])
            if isinstance(q, dict) and q.get("question")
        ],
        difficulty=raw.get("difficulty"),
        route=raw.get("route"),
        source_fingerprint=source_fingerprint,
        provenance=provenance,
    )


def _locate_quote(markdown: str, quote: str) -> tuple[int, int]:
    """Find a verbatim quote in the source, tolerating whitespace differences only.

    Rejecting a paraphrase here is what keeps identity source-derived: a discovered
    definition's id comes from where it *is* in the book, not from what the model called it.
    """
    idx = markdown.find(quote)
    if idx >= 0:
        return idx, idx + len(quote)
    # Whitespace-insensitive fallback: the model may reflow a quote across lines.
    pattern = re.compile(r"\s+".join(re.escape(w) for w in quote.split()), re.S)
    if m := pattern.search(markdown):
        return m.start(), m.end()
    raise AnnotationError(
        f"definition quote is not present verbatim in the source: {quote[:80]!r}. "
        "The annotator must quote, not paraphrase."
    )


def _page_for_offset(markdown: str, offset: int, printed_page_offset: int | None) -> tuple[int | None, int | None]:
    """The page a character offset falls on, from the nearest preceding page marker."""
    pdf_page = None
    for m in re.finditer(r"<!--\s*p\.(\d+)\s*-->", markdown[:offset]):
        pdf_page = int(m.group(1))
    printed = pdf_page - printed_page_offset if (pdf_page and printed_page_offset is not None) else None
    return pdf_page, printed


def annotate_chapter(
    registry: CorpusRegistry,
    chapter: str | int,
    *,
    provider: LLMProvider,
    corpus_name: str | None = None,
    prompt: Prompt | None = None,
    model: str | None = None,
    persist: bool = True,
    sections: list[str] | None = None,
) -> AnnotationResult:
    """Annotate one chapter, one section per request."""
    config = load_corpus(corpus_name)
    ch: ChapterConfig = config.chapter(chapter)
    chapter_no = ch.number
    chap_id = f"{config.slug}-ch{chapter_no}"
    markdown = ch.markdown.read_text(encoding="utf-8")
    prompt = prompt or load_prompt("annotate", "chapter")
    model = model or prompt.model or "claude-opus-5"

    existing = registry.declarations_in_chapter(chapter_no)
    if not existing:
        raise AnnotationError(
            f"chapter {chapter_no} has not been ingested; run `pipeline ingest {chapter_no}` first"
        )
    items_by_section: dict[str, list[SourceItem]] = {}
    for record in existing:
        items_by_section.setdefault(record.source.section or "0", []).append(record.source)

    annotations: list[AnnotatedDeclaration] = []
    discovered: list[SourceItem] = []
    edges: list[DependencyEdge] = []
    notation: list[NotationEntry] = []
    packages: list[ContextPackage] = []
    runs: list[StageRun] = []
    warnings: list[str] = []
    summaries: list[str] = []

    for section_no, section_title, section_text in split_sections(markdown):
        if sections is not None and section_no not in sections:
            continue
        section_items = items_by_section.get(section_no, [])
        if not section_items and section_no == "0":
            continue

        package = build_annotation_context(
            registry,
            chapter_no,
            chapter_markdown=section_text,
            chapter_title=ch.title,
            source_items=section_items,
        )
        packages.append(package)

        prior = "\n".join(i.content for i in package.by_role("approved_dependency")) or "(none cited)"
        conventions = "\n".join(
            i.content for i in package.items if i.role in ("notation", "convention")
        ) or "(none established yet)"
        items_blob = "\n".join(i.content for i in package.by_role("target")) or "(none)"

        request = LLMRequest(
            system=prompt.system,
            user=prompt.render(
                chapter=chapter_no,
                chapter_title=ch.title,
                section=section_no,
                items=items_blob,
                prior=prior,
                conventions=conventions,
                source=section_text,
            ),
            model=model,
            max_tokens=prompt.max_tokens,
        )
        started = time.monotonic()
        response, retries = call_with_retry(provider, request)
        payload = _parse_response(response.text, section_no)

        provenance = Provenance(
            producer=ANNOTATE_VERSION,
            provider=response.provider,
            model=response.model,
            prompt_version=prompt.id,
            context_package_id=package.id,
            corpus_version=registry.version,
        )

        if summary := payload.get("section_summary"):
            summaries.append(f"§{section_no}: {summary}")

        for raw in payload.get("notation", []):
            if isinstance(raw, dict) and raw.get("symbol"):
                notation.append(
                    NotationEntry(
                        symbol=str(raw["symbol"]),
                        meaning=str(raw.get("meaning", "")),
                        lean=raw.get("lean"),
                        decided_in=chap_id,
                    )
                )

        # --- items the deterministic pass could not find ----------------------
        # The book states plenty of mathematics without numbering it: most definitions,
        # and (as in theorem 3.1) the separate halves of a numbered result that it proves
        # one at a time. Both need identities, and ordinals run per kind within a section.
        section_items_raw = [
            d
            for d in payload.get("discovered_items", payload.get("definitions", []))
            if isinstance(d, dict) and d.get("quote")
        ]
        ordinals: dict[SourceItemKind, int] = {}
        for raw in section_items_raw:
            try:
                item_kind = SourceItemKind(str(raw.get("kind", "definition")))
            except ValueError:
                warnings.append(f"unknown discovered-item kind {raw.get('kind')!r}; ignored")
                continue
            quote = str(raw["quote"]).strip()
            try:
                start, end = _locate_quote(markdown, quote)
            except AnnotationError as exc:
                warnings.append(str(exc))
                continue
            ordinals[item_kind] = ordinals.get(item_kind, 0) + 1
            pdf_page, printed_page = _page_for_offset(markdown, start, ch.printed_page_offset)
            decl_id = declaration_id(
                config.slug, chapter_no, item_kind,
                section=section_no, ordinal=ordinals[item_kind],
            )
            item = SourceItem(
                id=decl_id,
                document_id=config.slug,
                chapter_id=chap_id,
                chapter=chapter_no,
                section=section_no,
                label=None,
                kind=item_kind,
                name=str(raw.get("term") or "").strip() or None,
                statement=quote,
                proof=None,
                span=SourceSpan(start=start, end=end, pdf_page=pdf_page, printed_page=printed_page),
                provenance=provenance,
            )
            discovered.append(item)
            raw_with_id = dict(raw, declaration_id=decl_id)
            annotations.append(
                _annotation_from(
                    raw_with_id,
                    chapter_id=chap_id,
                    kind=item_kind,
                    source_fingerprint=item.fingerprint,
                    provenance=provenance,
                    corpus=config.slug,
                    registry=registry,
                )
            )

        # --- annotations for known items -------------------------------------
        known = {i.id: i for i in section_items}
        for raw in payload.get("annotations", []):
            if not isinstance(raw, dict) or "declaration_id" not in raw:
                continue
            decl_id = str(raw["declaration_id"])
            item = known.get(decl_id)
            if item is None:
                warnings.append(f"annotator returned unknown declaration id {decl_id!r}; ignored")
                continue
            annotations.append(
                _annotation_from(
                    raw,
                    chapter_id=chap_id,
                    kind=item.kind,
                    source_fingerprint=item.fingerprint,
                    provenance=provenance,
                    corpus=config.slug,
                    registry=registry,
                )
            )

        runs.append(
            StageRun(
                id=f"run-annotate-{chap_id}-s{section_no}-{int(time.time() * 1000) % 10**9}",
                stage=Stage.ANNOTATE,
                target_id=f"{chap_id}/§{section_no}",
                status="ok",
                input_artifact_ids=[i.id for i in section_items],
                output_artifact_ids=[a.declaration_id for a in annotations],
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
        )

    # --- informal dependency edges (agent-inferred: proposals, not gates) -----
    for ann in annotations:
        for dep in ann.informal_dependencies:
            if dep.target_id:
                edges.append(
                    DependencyEdge(
                        source_id=ann.declaration_id,
                        target_id=dep.target_id,
                        edge_type=EdgeType.INFORMAL_DEPENDENCY,
                        provenance=EdgeProvenance(
                            kind=EdgeProvenanceKind.AGENT_INFERRED,
                            producer=ANNOTATE_VERSION,
                            artifact_id=ann.declaration_id,
                            evidence=f"annotation for {ann.declaration_id} "
                                     f"references {dep.raw_reference!r}",
                        ),
                        confidence=0.8,
                    )
                )

    digest_provenance = Provenance(producer=ANNOTATE_VERSION, corpus_version=registry.version)
    markdown_out = _render_markdown(chapter_no, ch.title, summaries, annotations, discovered, registry)

    if persist:
        if discovered:
            registry.store.upsert("items", discovered)
            registry.upsert_records(
                [record_from_source_item(i) for i in discovered if registry.get(i.id) is None]
            )
        registry.store.upsert("annotations", annotations)
        registry.store.upsert("context", packages)
        for run in runs:
            registry.store.append("runs", run)
        if notation:
            try:
                registry.register_notation(notation)
            except Exception as exc:  # noqa: BLE001 - a conflict is a warning, not a crash
                warnings.append(f"notation conflict: {exc}")
        registry.add_edges(edges)

        for ann in annotations:
            record = registry.get(ann.declaration_id)
            if record is not None:
                attach_annotation(record, ann)
        registry.upsert_records(
            [registry.require(a.declaration_id) for a in annotations if registry.get(a.declaration_id)]
        )
        registry.refresh_dependency_facets()
        registry.save()

    digest = build_digest(registry, chapter_no, ch.title, summaries, digest_provenance)
    if persist:
        _write_digest(registry, digest)

    return AnnotationResult(
        chapter=chapter_no,
        annotations=annotations,
        discovered_definitions=discovered,
        edges=edges,
        notation=notation,
        digest=digest,
        context_packages=packages,
        runs=runs,
        markdown=markdown_out,
        warnings=warnings,
    )


def build_digest(
    registry: CorpusRegistry,
    chapter: str,
    title: str,
    summaries: list[str],
    provenance: Provenance,
) -> ChapterDigest:
    """Compact export for later chapters. Statements only, never proofs."""
    records = registry.declarations_in_chapter(chapter)
    definitions, results = [], []
    concepts: set[str] = set()
    for r in records:
        export = ExportedDeclaration(
            declaration_id=r.id,
            kind=r.kind.value,
            label=r.source.label,
            name=r.source.name,
            statement=r.source.statement,
            lean_name=r.lean.name,
            trust=r.trust.status.value,
            review=r.review.status.value,
        )
        if r.is_foundational:
            definitions.append(export)
        elif r.kind.value in ("theorem", "lemma", "corollary", "proposition"):
            results.append(export)
        if r.annotation:
            concepts.update(r.annotation.concepts)

    cited_chapters: set[str] = set()
    exports_to: list[str] = []
    for r in records:
        for target in registry.prerequisites(r.id):
            if not target.startswith(f"{registry.store.corpus}-ch{chapter}-"):
                parts = target.split("-")
                if len(parts) > 1 and parts[1].startswith("ch"):
                    cited_chapters.add(parts[1][2:])
        for dependent in registry.reverse_dependencies(r.id):
            if not dependent.startswith(f"{registry.store.corpus}-ch{chapter}-"):
                exports_to.append(dependent)

    return ChapterDigest(
        chapter_id=f"{registry.store.corpus}-ch{chapter}",
        chapter=chapter,
        title=title,
        summary=" ".join(summaries) or f"Chapter {chapter}: {title}.",
        definitions=definitions,
        results=results,
        notation=list(registry.notation().values()),
        concepts=sorted(concepts),
        exports_to=sorted(set(exports_to)),
        depends_on_chapters=sorted(cited_chapters),
        provenance=provenance,
    )


def _write_digest(registry: CorpusRegistry, digest: ChapterDigest) -> None:
    registry.store.ensure()
    path = registry.store.directory / f"digest-{digest.chapter_id}.json"
    path.write_text(
        json.dumps(digest.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _render_markdown(
    chapter: str,
    title: str,
    summaries: list[str],
    annotations: list[AnnotatedDeclaration],
    discovered: list[SourceItem],
    registry: CorpusRegistry,
) -> str:
    """The human-readable annotated chapter. Kept because people read it (report 01 §F)."""
    lines = [f"# Chapter {chapter} — {title}: annotated", ""]
    if summaries:
        lines += ["## Summary", "", *summaries, ""]
    if discovered:
        lines += ["## Definitions found in prose", ""]
        for d in discovered:
            page = f" (p. {d.span.printed_page})" if d.span and d.span.printed_page else ""
            lines.append(f"- **{d.name or d.id}** `{d.id}`{page} — {d.statement}")
        lines.append("")
    lines += ["## Declarations", ""]
    for ann in sorted(annotations, key=lambda a: a.declaration_id):
        record = registry.get(ann.declaration_id)
        src = record.source if record else None
        header = f"### `{ann.declaration_id}`"
        if src and src.label:
            header += f" — {ann.kind.value} {src.label}"
        lines.append(header)
        if src:
            page = f", p. {src.span.printed_page}" if src.span and src.span.printed_page else ""
            lines.append(f"*§{src.section or '?'}{page}*")
            lines += ["", "> " + src.statement.replace("\n", "\n> "), ""]
        if ann.stated_hypotheses:
            lines.append("**Stated hypotheses**")
            lines += [f"- {h}" for h in ann.stated_hypotheses]
            lines.append("")
        if ann.proof_strategy:
            lines += ["**Proof strategy**", "", ann.proof_strategy, ""]
        if ann.proof_steps:
            lines.append("**Proof steps**")
            lines += [f"{s.index}. {s.text}" for s in ann.proof_steps]
            lines.append("")
        if ann.informal_dependencies:
            deps = ", ".join(
                f"`{d.target_id}`" if d.resolved else f"{d.raw_reference} (unresolved)"
                for d in ann.informal_dependencies
            )
            lines += [f"**Depends on** {deps}", ""]
        if ann.formalization_hints:
            lines.append("**Formalization hints**")
            lines += [f"- {h}" for h in ann.formalization_hints]
            lines.append("")
        if ann.mathlib_candidates:
            lines.append("**Mathlib candidates**")
            lines += [f"- `{c.name}` — {c.status}" + (f" ({c.note})" if c.note else "") for c in ann.mathlib_candidates]
            lines.append("")
        if ann.questions:
            lines.append("**Open questions**")
            lines += [f"- {q.question}" + (" **[blocks formalization]**" if q.blocks_formalization else "") for q in ann.questions]
            lines.append("")
        if ann.difficulty is not None:
            lines += [f"**Difficulty** {ann.difficulty}/100 → {ann.route or 'unrouted'}", ""]
    return "\n".join(lines)
