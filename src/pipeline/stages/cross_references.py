"""Deterministic extraction of the book's own cross-references.

Issue ``i-061``: *"The dependency graph exists in prose, not in code."* The summer
recorded 176 of 226 declarations as cited only inside another declaration's docstring,
while 224 of 226 had no Lean-code reference at all -- so the informal graph and the formal
graph never met.

But the book writes its dependencies down explicitly, in a small number of fixed forms,
and a regex reads them exactly. This module turns "by theorem 2.3" into a typed edge with
``SOURCE_EXTRACTED`` provenance, which is exact enough to gate on. No model is asked.

A reference that resolves to a declaration outside the loaded corpus stays *unresolved*
rather than being dropped: chapter 3 depends on theorem 2.3 and exercise 2.3.1(a) from
chapter 2, and a corpus holding only chapter 3 should say so out loud.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from pipeline.corpus.ids import declaration_id
from pipeline.artifacts.models import (
    DependencyEdge,
    EdgeProvenance,
    EdgeProvenanceKind,
    EdgeType,
    SourceItem,
    SourceItemKind,
)

__all__ = ["extract_cross_references", "CrossReference", "REFERENCE_RE", "parse_reference"]

EXTRACTOR_VERSION = "cross_references/v1"

_REF_KINDS = {
    "theorem": SourceItemKind.THEOREM,
    "lemma": SourceItemKind.LEMMA,
    "corollary": SourceItemKind.COROLLARY,
    "proposition": SourceItemKind.PROPOSITION,
    "exercise": SourceItemKind.EXERCISE,
    "definition": SourceItemKind.DEFINITION,
}

#: A citation to a numbered item, optionally to one of its lettered parts.
#: All four part spellings occur in this corpus and in prose written about it:
#:   "exercise 2.3.1$a$"   the book, italicising the letter in maths mode
#:   "exercise 2.3.1(a)"   ordinary prose
#:   "exercise 2.3.1 (a)"  the same, spaced
#:   "exercise 2.3.1a"     compact
#: The bare form requires the letter not to begin a word, so "theorem 3.1 and ..." does
#: not silently acquire a part "a".
REFERENCE_RE = re.compile(
    r"\b(?P<kind>theorem|lemma|corollary|proposition|exercise|definition)s?\s+"
    r"(?P<label>\d+(?:\.\d+)+)"
    r"(?:"
    r"\s*\((?P<part_paren>[a-z])\)"
    r"|\$(?P<part_math>[a-z])\$"
    r"|(?P<part_bare>[a-z])(?![a-z])"
    r")?",
    re.I,
)


def parse_reference(match: re.Match[str]) -> tuple[SourceItemKind, str]:
    """Turn a :data:`REFERENCE_RE` match into (kind, label-with-part).

    Single source of truth for reference parsing, so the deterministic extractor and the
    annotator's dependency resolver cannot drift apart.
    """
    kind = _REF_KINDS[match.group("kind").lower()]
    part = match.group("part_paren") or match.group("part_math") or match.group("part_bare") or ""
    return kind, f"{match.group('label')}{part.lower()}"


class CrossReference:
    """One resolved-or-not citation found in source text."""

    __slots__ = ("raw", "kind", "label", "target_id", "chapter", "where")

    def __init__(
        self, raw: str, kind: SourceItemKind, label: str, target_id: str, chapter: str, where: str
    ) -> None:
        self.raw = raw
        self.kind = kind
        self.label = label
        self.target_id = target_id
        self.chapter = chapter
        self.where = where  # "statement" | "proof"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CrossReference {self.raw!r} -> {self.target_id}>"


def _references_in(text: str, corpus: str, where: str) -> list[CrossReference]:
    found: list[CrossReference] = []
    for m in REFERENCE_RE.finditer(text):
        kind, label = parse_reference(m)
        chapter = label.split(".", 1)[0]
        target = declaration_id(corpus, chapter, kind, label=label)
        found.append(CrossReference(m.group(0), kind, label, target, chapter, where))
    return found


def extract_cross_references(
    items: Iterable[SourceItem], *, corpus: str
) -> tuple[list[DependencyEdge], list[CrossReference]]:
    """Return (edges, references) for a collection of source items.

    Self-references are dropped: a theorem's proof naturally restates its own number.
    """
    edges: list[DependencyEdge] = []
    references: list[CrossReference] = []
    seen: set[tuple[str, str]] = set()

    for item in items:
        for where, text in (("statement", item.statement), ("proof", item.proof)):
            if not text:
                continue
            for ref in _references_in(text, corpus, where):
                if ref.target_id == item.id:
                    continue
                references.append(ref)
                key = (item.id, ref.target_id)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    DependencyEdge(
                        source_id=item.id,
                        target_id=ref.target_id,
                        edge_type=EdgeType.SOURCE_CROSS_REFERENCE,
                        provenance=EdgeProvenance(
                            kind=EdgeProvenanceKind.SOURCE_EXTRACTED,
                            producer=EXTRACTOR_VERSION,
                            artifact_id=item.id,
                            evidence=f"{item.id} {where}: {ref.raw!r}",
                        ),
                        confidence=1.0,
                    )
                )
    return edges, references
