"""Deterministic extraction of labelled items from a Markdown source.

A printed label, the section it sits under, the page marker above it and the line span are
mechanically recoverable; this pass finds what the source explicitly numbers. Unlabelled
definitions stated inline in prose are the translator's job -- it emits them with id
``TBD`` and the validator assigns ``section+ordinal`` ids from the located verbatim quote.

Ported from ``b753236:src/pipeline/stages/source_items.py`` (pydantic models replaced by
dicts; ids via :mod:`mathtcs.ids`).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import ids as ids_mod
from .util import sha256_text

__all__ = ["extract", "extract_file", "PAGE_MARKER_RE", "SECTION_RE", "NAMED_RE", "EXERCISE_RE", "PROOF_RE"]

EXTRACTOR_VERSION = "source-items/v1"

PAGE_MARKER_RE = re.compile(r"^<!--\s*p\.(\d+)\s*-->\s*$")
SECTION_RE = re.compile(r"^#{2,4}\s+(?P<num>\d+(?:\.\d+)*)\s+(?P<title>.+?)\s*$")
TITLE_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.M)
EXERCISES_RE = re.compile(r"^(?:\*Exercises\*|#{2,4}\s+Exercises)\s*$", re.I)
PROOF_RE = re.compile(
    r"^\s*(?P<open>\*{1,2}|_{1,2})\s*Proof\b(?P<qual>[^*_]*?)\s*(?P=open)\s*[.:]?\s*(?P<rest>.*)$",
    re.I,
)
_KIND_WORDS = {
    "theorem": "theorem",
    "lemma": "lemma",
    "corollary": "corollary",
    "proposition": "proposition",
    "definition": "definition",
}
NAMED_RE = re.compile(
    r"^(?P<open>\*{1,2})?"
    r"(?P<kind>Theorem|Lemma|Corollary|Proposition|Definition)\s+"
    r"(?P<label>\d+(?:\.\d+)+)"
    r"(?P<close>\*{1,2})?"
    r"(?P<rest>.*)$",
    re.I,
)
EXERCISE_RE = re.compile(
    r"^(?P<open>\*{1,2})?"
    r"(?P<label>\d+\.\d+\.\d+)"
    r"(?P<star>\*)?"
    r"(?P<close>\*{1,2})?"
    r"(?P<rest>\s+.*)$"
)
_NOISE_RE = re.compile(r"^\s*(\[figure omitted\]|Figure\s|<!--|\*[^*\n]{1,40}\*\s*$)", re.I)
RUNNING_HEAD_RE = re.compile(r"^\s*\d*\s*\*[^*]+\*\s*$")
_END_OF_PROOF = ("□", "∎", "■", "◻", r"\square", r"\blacksquare", r"\qed")


def _is_tombstone(line: str) -> bool:
    return any(mark in line for mark in _END_OF_PROOF)


def _clean_statement(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^\*{1,2}\s*", "", text)
    return text.strip()


def extract(markdown: str, *, slug: str, chapter: str) -> list[dict]:
    """Every explicitly labelled item, in source order, with 1-based line spans."""
    lines = markdown.splitlines()
    items: list[dict] = []
    section: str | None = None
    page: int | None = None
    in_exercises = False
    seen: set[str] = set()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if m := PAGE_MARKER_RE.match(line):
            page = int(m.group(1)); i += 1; continue
        if m := SECTION_RE.match(line):
            section = m.group("num"); in_exercises = False; i += 1; continue
        if EXERCISES_RE.match(line):
            in_exercises = True; i += 1; continue

        kind = label = None
        rest = ""
        if m := NAMED_RE.match(line):
            kind = _KIND_WORDS[m.group("kind").lower()]; label = m.group("label"); rest = m.group("rest")
        elif in_exercises and (m := EXERCISE_RE.match(line)):
            kind = "exercise"; label = m.group("label"); rest = m.group("rest")
        if kind is None or label is None:
            i += 1; continue

        decl_id = ids_mod.declaration_id(slug, chapter, kind, label=label)
        if decl_id in seen:
            i += 1; continue
        seen.add(decl_id)

        start_line = i + 1
        body = [_clean_statement(rest)]
        j = i + 1
        while j < n and lines[j].strip():
            if NAMED_RE.match(lines[j]) or PROOF_RE.match(lines[j]):
                break
            body.append(lines[j])
            j += 1
        statement = "\n".join(b for b in body if b).strip()
        end_line = max(start_line, j)  # last statement line (1-based)

        proof = None
        k = j
        while k < n:
            cand = lines[k]
            if not cand.strip() or _NOISE_RE.match(cand) or RUNNING_HEAD_RE.match(cand):
                k += 1; continue
            break
        if k < n and (pm := PROOF_RE.match(lines[k])):
            proof_lines = [pm.group("rest").strip()]
            last_idx = k
            k += 1
            if not _is_tombstone(pm.group("rest")):
                while k < n:
                    cand = lines[k]
                    if NAMED_RE.match(cand) or (in_exercises and EXERCISE_RE.match(cand)) or SECTION_RE.match(cand):
                        break
                    if not _NOISE_RE.match(cand):
                        proof_lines.append(cand)
                        last_idx = k
                    if _is_tombstone(cand):
                        k += 1; break
                    k += 1
            proof = "\n".join(proof_lines).strip() or None
            end_line = last_idx + 1

        items.append({
            "id": decl_id,
            "kind": kind,
            "label": label,
            "section": section,
            "page": page,
            "lines": [start_line, end_line],
            "statement": statement,
            "proof": proof,
            "excerpt_sha256": ids_mod.content_fingerprint(statement, proof),
        })
        i = j
    return items


def extract_file(path: str, *, slug: str | None, chapter: str | None, configured_slug: str | None,
                 configured_chapter: str | None) -> dict:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    stem = p.stem
    slug_v, slug_rule = ids_mod.derive_slug(explicit=slug, configured=configured_slug, filename_stem=stem)
    ch_v, ch_rule = ids_mod.derive_chapter(explicit=chapter, configured=configured_chapter, filename_stem=stem, text=text)
    title_m = TITLE_RE.search(text)
    items = extract(text, slug=slug_v, chapter=ch_v)
    return {
        "extractor": EXTRACTOR_VERSION,
        "path": str(p.resolve()),
        "sha256": sha256_text(text),
        "slug": slug_v,
        "slug_rule": slug_rule,
        "chapter": ch_v,
        "chapter_rule": ch_rule,
        "title": title_m.group("title") if title_m else stem,
        "items": items,
        "counts": {k: sum(1 for it in items if it["kind"] == k) for k in sorted({it["kind"] for it in items})},
    }
