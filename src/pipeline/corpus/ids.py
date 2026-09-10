"""Deterministic, source-derived identifiers.

Architectural rule 2: a mathematical item keeps ONE identity from textbook source
through annotation, formalization, checking, review, proof and integration.

Report 01 §B2 and issue ``i-004`` record what happens without this: every join in the
summer pipeline was string-matching on a human-written Markdown heading, and the terminal
350-record dataset carried no chapter, section, label, page or source-document field at
all -- the chain back to the book was severed.

Identity is derived only from things the *source* fixes:

* the corpus slug (a property of the document, chosen once),
* the chapter,
* the item kind,
* the printed label (``3.2``, ``1.2.8(b)``) when the book gives one,
* otherwise the section plus the item's ordinal position within it.

It never depends on LLM wording, generated Lean names, timestamps, or randomness.

Content hashes are a *separate* concept: :func:`content_fingerprint` detects that the
source text behind an ID changed. Identity answers "which theorem is this"; the
fingerprint answers "is my copy stale". Conflating them would make every re-extraction
look like a new declaration.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from pipeline.artifacts.models.enums import KIND_CODE, SourceItemKind

__all__ = [
    "IdentityError",
    "normalize_label",
    "normalize_slug",
    "declaration_id",
    "chapter_id",
    "document_id",
    "content_fingerprint",
    "parse_declaration_id",
]


class IdentityError(ValueError):
    """Raised when an identifier cannot be derived deterministically."""


_LABEL_ALLOWED = re.compile(r"[^a-z0-9.]+")
_SLUG_ALLOWED = re.compile(r"[^a-z0-9]+")
_ID_RE = re.compile(
    r"^(?P<corpus>[a-z0-9]+)-ch(?P<chapter>[a-z0-9]+)-(?P<kind>[a-z]+)-(?P<local>[a-z0-9.\-]+)$"
)


def normalize_label(label: str) -> str:
    """Normalise a printed source label into an ID-safe token.

    Sources print labels in several shapes, and one real corpus contains all of these:
    ``Theorem 3.2``, ``3.1.2``, ``1.2.8(b)``, ``4.2.11(a)``, ``8.5.2 (a)*``. They must all
    normalise stably, because the label is the join key a human uses.

        >>> normalize_label("Theorem 3.2")
        '3.2'
        >>> normalize_label("1.2.8(b)")
        '1.2.8b'
        >>> normalize_label("Ex 4.2.11 (a)")
        '4.2.11a'
        >>> normalize_label("8.5.2(a)*")
        '8.5.2a'
    """
    if label is None:
        raise IdentityError("label is required")
    text = unicodedata.normalize("NFKD", label).lower()
    # Drop the kind word if the label carries one ("theorem 3.2" -> "3.2").
    text = re.sub(
        r"^\s*(theorem|thm|lemma|lem|corollary|cor|proposition|prop|definition|def|"
        r"exercise|ex|example|remark|construction|notation)\.?\s+",
        "",
        text,
    )
    text = text.replace("*", "")  # starred exercises are the same exercise
    text = _LABEL_ALLOWED.sub("", text)  # "(b)" -> "b", spaces removed
    text = text.strip(".-")
    if not text:
        raise IdentityError(f"label {label!r} normalises to empty")
    return text


def normalize_slug(text: str, *, max_words: int = 6) -> str:
    """Normalise free text into a readable slug.

    Used for display and for filenames -- never inside a declaration ID, because free
    text is exactly the LLM-dependent input that rule 2 forbids as identity.
    """
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = [w for w in _SLUG_ALLOWED.sub(" ", ascii_text.lower()).split() if w]
    return "-".join(words[:max_words])


def document_id(corpus: str) -> str:
    slug = normalize_slug(corpus, max_words=4)
    if not slug:
        raise IdentityError(f"corpus {corpus!r} normalises to empty")
    return slug


def chapter_id(corpus: str, chapter: str) -> str:
    """``bm`` + ``3`` -> ``bm-ch3``. Appendices keep their letter: ``bm-cha1``."""
    ch = _LABEL_ALLOWED.sub("", str(chapter).lower())
    ch = _SLUG_ALLOWED.sub("", ch) or _LABEL_ALLOWED.sub("", str(chapter).lower())
    if not ch:
        raise IdentityError(f"chapter {chapter!r} normalises to empty")
    return f"{document_id(corpus)}-ch{ch}"


def declaration_id(
    corpus: str,
    chapter: str,
    kind: SourceItemKind,
    *,
    label: str | None = None,
    section: str | None = None,
    ordinal: int | None = None,
) -> str:
    """Build the stable declaration identity.

    Two shapes, in priority order:

    1. **Labelled** -- the book prints a number. This is the common case and the one a
       human cites::

           >>> declaration_id("demo-naturals", "1", SourceItemKind.THEOREM, label="Theorem 1.1")
           'dn-ch1-thm-1.1'

    2. **Unlabelled** -- definitions stated inline in running prose, which textbooks do
       constantly and which carry no printed number at all. Identity is then the section
       plus a 1-based ordinal over items of the same kind in that section, ordered by
       position in the source::

           >>> declaration_id("dn", "1", SourceItemKind.DEFINITION, section="1.1", ordinal=1)
           'dn-ch1-def-1.1-1'

       The ordinal must come from the source text order, never from the order an agent
       happened to emit items in.

    Passing neither ``label`` nor (``section``, ``ordinal``) is an error rather than a
    fallback: a silent fallback to hashing the statement would make identity depend on
    extraction wording, which is the failure this module exists to prevent.
    """
    corpus_slug = document_id(corpus)
    if len(corpus_slug) > 4 and "-" in corpus_slug:
        # A multi-word corpus *name* abbreviates to initials: "demo-naturals" -> "dn".
        # Callers that hold a configured slug pass it instead, and a slug is a single
        # token: abbreviating "parity" to "p" would silently discard a deliberate choice.
        initials = "".join(part[0] for part in corpus_slug.split("-") if part)
        corpus_slug = initials or corpus_slug
    ch = chapter_id(corpus_slug, chapter).split("-ch", 1)[1]
    code = KIND_CODE[kind]

    if label is not None and str(label).strip():
        local = normalize_label(str(label))
    elif section is not None and ordinal is not None:
        if ordinal < 1:
            raise IdentityError("ordinal is 1-based")
        local = f"{normalize_label(str(section))}-{ordinal}"
    else:
        raise IdentityError(
            "declaration_id needs either a source label, or a section plus a 1-based "
            "ordinal; identity must not be derived from statement text"
        )
    return f"{corpus_slug}-ch{ch}-{code}-{local}"


def parse_declaration_id(decl_id: str) -> dict[str, str]:
    """Inverse of :func:`declaration_id`, for routing and for client-side filters."""
    m = _ID_RE.match(decl_id)
    if not m:
        raise IdentityError(f"{decl_id!r} is not a well-formed declaration id")
    return m.groupdict()


def content_fingerprint(*parts: str | None) -> str:
    """Hash of the exact source content behind a declaration.

    Detects staleness, never identity. In the earlier effort an annotation kept instructing
    downstream stages to reuse a Lean file long after that file had ceased to exist, because
    nothing recorded which revision of the source the annotation had been written against.
    A fingerprint mismatch turns that silent lie into a refusal.
    """
    h = hashlib.sha256()
    for part in parts:
        # Distinct markers for absent and empty: "this theorem has no printed proof" and
        # "this theorem has an empty proof" are different facts about the source, and a
        # staleness check that conflates them would miss a real content change.
        if part is None:
            h.update(b"\x00N")
        else:
            h.update(b"\x00S")
            h.update(part.encode("utf-8"))
    return h.hexdigest()
