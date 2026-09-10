"""Deterministic extraction of labelled source items from chapter Markdown.

Rule 5's spirit applied one stage earlier than Lean: **do not ask a model what a program
can decide exactly.** A printed label, the section it sits under, and the page marker
above it are all mechanically recoverable from the extraction output, and report 01 §B1
measured what happens when they are left to an agent instead -- the raw chapters carry
9-24 ``<!-- p.NNN -->`` markers each and the annotated chapters carry zero.

What this module does NOT do is judgement. Unlabelled definitions stated inline in
running prose ("A natural number is *even* if ..."), concept tags, dependencies and proof
strategy are the annotator's job; this pass only finds what the book explicitly numbers.

Item shapes observed in real corpora. All of these occur in a single chapter of one of
them, which is why the matcher is as forgiving as it is:

    **Theorem 3.1** $\\kappa \\leq \\kappa' \\leq \\delta$.
    *Theorem 3.2* A graph $G$ with ... is 2-connected if and only if ...
    *Theorem 3.3* (Harary, 1962)   The graph $H_{m,n}$ is $m$-connected.
    *Corollary 3.2.1*  If $G$ is 2-connected, then ...
    **Corollary 3.2.2**  If $G$ is a block with ...
    3.1.2 Show that if $G$ is $k$-edge-connected, then ...
    **3.2.1** Show that a graph is 2-edge-connected if and only if ...
    3.2.6* Let $G$ be a 2-connected graph and ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.corpus.ids import declaration_id
from pipeline.artifacts.models import Provenance, SourceItem, SourceItemKind, SourceSpan

__all__ = ["extract_source_items", "ExtractionConfig", "PAGE_MARKER_RE"]

EXTRACTOR_VERSION = "source_items/v1"

PAGE_MARKER_RE = re.compile(r"^<!--\s*p\.(\d+)\s*-->\s*$")
# Section headings appear at several depths: chapter 3 puts its applications section
# under an "## APPLICATIONS" banner with the real section as "### 3.3 ...".
SECTION_RE = re.compile(r"^#{2,4}\s+(?P<num>\d+(?:\.\d+)*)\s+(?P<title>.+?)\s*$")
# Two conventions in the same corpus: chapter 3 uses "*Exercises*", chapter 1 uses
# "## Exercises". Both open an exercise block in which bare "N.M.K" labels are items.
EXERCISES_RE = re.compile(r"^(?:\*Exercises\*|#{2,4}\s+Exercises)\s*$", re.I)
# Proof openers vary by typography between corpora: "*Proof*", "*Proof.*", "**Proof.**",
# "_Proof._", "*Proof:*" and named forms like "*Proof of Theorem 1.1.*". What is constant is
# emphasis around the word "Proof", with an optional qualifier and optional punctuation.
#
# Matching a single spelling is not a cosmetic limitation: an unmatched opener drops the
# whole proof, and with it every cross-reference stated inside it, so the informal
# dependency graph comes out incomplete with nothing anywhere saying so.
PROOF_RE = re.compile(
    r"^\s*(?P<open>\*{1,2}|_{1,2})\s*Proof\b(?P<qual>[^*_]*?)\s*(?P=open)\s*[.:]?\s*(?P<rest>.*)$",
    re.I,
)

_KIND_WORDS = {
    "theorem": SourceItemKind.THEOREM,
    "lemma": SourceItemKind.LEMMA,
    "corollary": SourceItemKind.COROLLARY,
    "proposition": SourceItemKind.PROPOSITION,
    "definition": SourceItemKind.DEFINITION,
}

#: A named, numbered result: optional bold/italic markers around "Kind N.M".
NAMED_RE = re.compile(
    r"^(?P<open>\*{1,2})?"
    r"(?P<kind>Theorem|Lemma|Corollary|Proposition|Definition)\s+"
    r"(?P<label>\d+(?:\.\d+)+)"
    r"(?P<close>\*{1,2})?"
    r"(?P<rest>.*)$",
    re.I,
)

#: A bare exercise label: "3.1.2 ...", "**3.2.1** ...", "3.2.6* ...".
EXERCISE_RE = re.compile(
    r"^(?P<open>\*{1,2})?"
    r"(?P<label>\d+\.\d+\.\d+)"
    r"(?P<star>\*)?"
    r"(?P<close>\*{1,2})?"
    r"(?P<rest>\s+.*)$"
)

#: Lines that are structural noise rather than mathematics: a dropped figure, a page
#: marker, or a short italic line alone on its own — which is what extraction leaves
#: behind for a running head (the division's title repeated at the top of each page).
#:
#: The running-head alternative is deliberately a *shape* rather than a list of titles.
#: An earlier version named one corpus's chapter title here, which meant every new
#: source silently re-acquired the bug that pattern was added to fix.
_NOISE_RE = re.compile(
    r"^\s*(\[figure omitted\]|Figure\s|<!--|\*[^*\n]{1,40}\*\s*$)", re.I
)

#: A running head left by extraction: an italic book/chapter title, optionally with a
#: page number, alone on its line.
RUNNING_HEAD_RE = re.compile(r"^\s*\d*\s*\*[^*]+\*\s*$")

#: End-of-proof tombstones. Which glyph a source uses is a typographic choice, so all the
#: common ones close a proof -- including the LaTeX spellings, which survive extraction from
#: a PDF that rendered them as macros rather than characters.
_END_OF_PROOF = ("\u25a1", "\u220e", "\u25a0", "\u25fb", r"\square", r"\blacksquare", r"\qed")


def _is_tombstone(line: str) -> bool:
    return any(mark in line for mark in _END_OF_PROOF)


@dataclass(frozen=True)
class ExtractionConfig:
    """Per-chapter configuration.

    ``printed_page_offset`` converts the ``<!-- p.NNN -->`` markers, which carry **PDF**
    page numbers, into the printed page numbers the book itself prints and that every
    human citation uses. The summer never recorded this mapping (report 00 §A.4), which is
    why chapter 3's Lean docstrings cite "p. 50" for what the book prints as page 42.
    """

    corpus: str
    document_id: str
    chapter_id: str
    chapter: str
    printed_page_offset: int | None = None


def _clean_statement(text: str) -> str:
    text = text.strip()
    # Strip a trailing italic/bold marker left over from the label match.
    text = re.sub(r"^\*{1,2}\s*", "", text)
    return text.strip()


def _flush_paragraph(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def extract_source_items(
    markdown: str,
    config: ExtractionConfig,
    *,
    provenance: Provenance | None = None,
) -> list[SourceItem]:
    """Extract every explicitly labelled item from one chapter of Markdown.

    Items are returned in source order. Each carries a :class:`SourceSpan` with character
    offsets and the PDF page it appeared on, and a ``fingerprint`` over its statement and
    proof so that a later re-extraction can tell "same theorem, changed text" from
    "different theorem".
    """
    prov = provenance or Provenance(producer=EXTRACTOR_VERSION)
    lines = markdown.splitlines(keepends=True)

    # Character offset of the start of each line, for spans.
    offsets: list[int] = []
    running = 0
    for line in lines:
        offsets.append(running)
        running += len(line)

    items: list[SourceItem] = []
    section: str | None = None
    pdf_page: int | None = None
    in_exercises = False
    seen_labels: set[str] = set()

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        line = raw.rstrip("\n")

        if m := PAGE_MARKER_RE.match(line):
            pdf_page = int(m.group(1))
            i += 1
            continue
        if m := SECTION_RE.match(line):
            section = m.group("num")
            in_exercises = False
            i += 1
            continue
        if EXERCISES_RE.match(line):
            in_exercises = True
            i += 1
            continue

        kind: SourceItemKind | None = None
        label: str | None = None
        rest = ""

        if m := NAMED_RE.match(line):
            kind = _KIND_WORDS[m.group("kind").lower()]
            label = m.group("label")
            rest = m.group("rest")
        elif in_exercises and (m := EXERCISE_RE.match(line)):
            kind = SourceItemKind.EXERCISE
            label = m.group("label")
            rest = m.group("rest")

        if kind is None or label is None:
            i += 1
            continue
        # Dedup on the *identity*, not on the bare label: a source may number its
        # corollaries and its exercises independently, so "Corollary 3.2.1" and
        # "Exercise 3.2.1" can both exist. They are different items, and get
        # different ids.
        decl_id = declaration_id(config.document_id, config.chapter, kind, label=label)
        if decl_id in seen_labels:
            i += 1
            continue
        seen_labels.add(decl_id)

        start_off = offsets[i]
        body = [_clean_statement(rest)]
        j = i + 1
        # The statement runs to the next blank line; a labelled item never spans one.
        while j < n and lines[j].strip():
            if NAMED_RE.match(lines[j].rstrip("\n")) or PROOF_RE.match(lines[j].rstrip("\n")):
                break
            body.append(lines[j].rstrip("\n"))
            j += 1
        statement = _flush_paragraph([b for b in body if b])
        end_off = offsets[j - 1] + len(lines[j - 1]) if j > i else start_off + len(raw)

        # A following *Proof* block, up to the tombstone. The book routinely interposes
        # a page marker, a running head, a figure and its caption between a theorem and
        # its proof -- chapter 3's theorem 3.2 has all four -- so structural noise is
        # skipped as well as blank lines. A real declaration line stops the search.
        proof: str | None = None
        k = j
        while k < n:
            candidate = lines[k].rstrip("\n")
            if not candidate.strip() or _NOISE_RE.match(candidate) or RUNNING_HEAD_RE.match(candidate):
                k += 1
                continue
            break
        if k < n and (pm := PROOF_RE.match(lines[k].rstrip("\n"))):
            proof_lines = [pm.group("rest").strip()]
            k += 1
            while k < n:
                candidate = lines[k].rstrip("\n")
                if NAMED_RE.match(candidate) or (in_exercises and EXERCISE_RE.match(candidate)):
                    break
                if not _NOISE_RE.match(candidate):
                    proof_lines.append(candidate)
                if _is_tombstone(candidate):
                    k += 1
                    break
                k += 1
            proof = "\n".join(p for p in proof_lines).strip() or None
            end_off = offsets[min(k, n - 1)]

        printed = None
        if pdf_page is not None and config.printed_page_offset is not None:
            printed = pdf_page - config.printed_page_offset

        items.append(
            SourceItem(
                id=decl_id,
                document_id=config.document_id,
                chapter_id=config.chapter_id,
                chapter=config.chapter,
                section=section,
                label=label,
                kind=kind,
                statement=statement,
                proof=proof,
                span=SourceSpan(
                    start=start_off, end=end_off, pdf_page=pdf_page, printed_page=printed
                ),
                provenance=prov,
            )
        )
        i = j
    return items
