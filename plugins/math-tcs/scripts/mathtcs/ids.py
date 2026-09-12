"""Deterministic, source-derived declaration identifiers.

An item keeps one identity from source text to verified Lean. Identity depends only on
things the source fixes: the slug (chosen once per source, then persisted in the target's
config), the chapter, the item kind, and the printed label -- or, for unlabelled items,
the section plus the item's ordinal in that section. Never on model wording, Lean names,
timestamps or hashes.

Content fingerprints (:func:`content_fingerprint`) are a separate concept: they detect
that the text behind an id changed. Identity answers "which theorem"; the fingerprint
answers "is my copy stale".

Ported from ``b753236:src/pipeline/corpus/ids.py`` with the pydantic enums replaced by
plain strings.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

__all__ = [
    "IdentityError",
    "KIND_CODE",
    "KIND_FROM_CODE",
    "KINDS",
    "normalize_label",
    "normalize_slug",
    "abbreviate_slug",
    "declaration_id",
    "helper_name",
    "parse_declaration_id",
    "content_fingerprint",
    "sha256_text",
    "derive_chapter",
    "derive_slug",
]


class IdentityError(ValueError):
    """Raised when an identifier cannot be derived deterministically."""


#: Fixed forever: changing a code changes every id.
KIND_CODE: dict[str, str] = {
    "definition": "def",
    "theorem": "thm",
    "lemma": "lem",
    "corollary": "cor",
    "proposition": "prop",
    "exercise": "ex",
    "example": "exm",
    "construction": "con",
    "notation": "not",
    "remark": "rem",
}
KIND_FROM_CODE: dict[str, str] = {v: k for k, v in KIND_CODE.items()}
KINDS: tuple[str, ...] = tuple(KIND_CODE)

#: Kinds whose Lean form is an object (a definition), not a proposition.
OBJECT_KINDS: frozenset[str] = frozenset({"definition", "construction", "notation"})

_LABEL_ALLOWED = re.compile(r"[^a-z0-9.]+")
_SLUG_ALLOWED = re.compile(r"[^a-z0-9]+")
_ID_RE = re.compile(
    r"^(?P<slug>[a-z0-9]+)-ch(?P<chapter>[a-z0-9]+)-(?P<kind>[a-z]+)-(?P<local>[a-z0-9.\-]+)$"
)
_KIND_WORD_RE = re.compile(
    r"^\s*(theorem|thm|lemma|lem|corollary|cor|proposition|prop|definition|def|"
    r"exercise|ex|example|remark|construction|notation)\.?\s+"
)


def normalize_label(label: str | None) -> str:
    """Normalise a printed label into an id-safe token.

    ``Theorem 3.2`` -> ``3.2``; ``1.2.8(b)`` -> ``1.2.8b``; ``Ex 4.2.11 (a)`` -> ``4.2.11a``;
    ``8.5.2(a)*`` -> ``8.5.2a`` (a starred exercise is the same exercise).
    """
    if label is None:
        raise IdentityError("label is required")
    text = unicodedata.normalize("NFKD", str(label)).lower()
    text = _KIND_WORD_RE.sub("", text)
    text = text.replace("*", "")
    text = _LABEL_ALLOWED.sub("", text)
    text = text.strip(".-")
    if not text:
        raise IdentityError(f"label {label!r} normalises to empty")
    return text


def normalize_slug(text: str, *, max_words: int = 6) -> str:
    """Free text -> readable slug (display and filenames; never identity on its own)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = [w for w in _SLUG_ALLOWED.sub(" ", ascii_text.lower()).split() if w]
    return "-".join(words[:max_words])


def abbreviate_slug(text: str, *, max_len: int = 4) -> str:
    """A multi-word name abbreviates to initials (``demo-naturals`` -> ``dn``); a single
    word is kept (truncated to ``max_len``). Digits are dropped from the front."""
    slug = normalize_slug(text, max_words=4)
    parts = [p for p in slug.split("-") if p and not p.isdigit()] or [p for p in slug.split("-") if p]
    if not parts:
        raise IdentityError(f"slug {text!r} normalises to empty")
    if len(parts) > 1:
        token = "".join(p[0] for p in parts)
    else:
        token = parts[0][:max_len]
    token = token.lstrip("0123456789") or token
    return token


def _chapter_token(chapter: str) -> str:
    ch = _LABEL_ALLOWED.sub("", str(chapter).lower())
    ch = _SLUG_ALLOWED.sub("", ch) or ch
    if not ch:
        raise IdentityError(f"chapter {chapter!r} normalises to empty")
    return ch


def declaration_id(
    slug: str,
    chapter: str,
    kind: str,
    *,
    label: str | None = None,
    section: str | None = None,
    ordinal: int | None = None,
) -> str:
    """``dn`` + ``1`` + ``theorem`` + label ``Theorem 1.1`` -> ``dn-ch1-thm-1.1``.

    Unlabelled items use ``section`` and a 1-based ``ordinal`` over items of the same kind
    in that section, in source order: ``dn-ch1-def-1.1-1``. Passing neither is an error,
    never a fallback to hashing the statement.
    """
    if kind not in KIND_CODE:
        raise IdentityError(f"unknown kind {kind!r}; expected one of {sorted(KIND_CODE)}")
    slug_token = _SLUG_ALLOWED.sub("", str(slug).lower())
    if not slug_token:
        raise IdentityError(f"slug {slug!r} normalises to empty")
    ch = _chapter_token(chapter)
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
    return f"{slug_token}-ch{ch}-{code}-{local}"


def helper_name(lean_name: str, n: int) -> str:
    """Name of the ``n``-th supporting lemma the prover may add for ``lean_name``."""
    return f"{lean_name}.aux_{n}"


def parse_declaration_id(decl_id: str) -> dict[str, str]:
    m = _ID_RE.match(decl_id)
    if not m:
        raise IdentityError(f"{decl_id!r} is not a well-formed declaration id")
    d = m.groupdict()
    d["kind_name"] = KIND_FROM_CODE.get(d["kind"], d["kind"])
    return d


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_fingerprint(*parts: str | None) -> str:
    """Hash of the exact content behind a declaration -- staleness, never identity.

    Absent and empty parts hash differently ("no printed proof" and "empty proof" are
    different facts about the source)."""
    h = hashlib.sha256()
    for part in parts:
        if part is None:
            h.update(b"\x00N")
        else:
            h.update(b"\x00S")
            h.update(part.encode("utf-8"))
    return h.hexdigest()


# --------------------------------------------------------------------------- discovery

_FILENAME_CHAPTER_RE = re.compile(r"^(?:(\d+)[_\-.]|.*?\bch(?:apter)?[_\-]?(\d+)\b)", re.I)
_HEADING_CHAPTER_RE = re.compile(
    r"^#\s+(?:Unit|Chapter|Lecture|Part|Section)\s+([0-9]+|[A-Z])\b", re.I | re.M
)
_FIRST_LABEL_RE = re.compile(r"\b(?:Theorem|Lemma|Corollary|Proposition|Definition)\s+(\d+)\.\d+", re.I)
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def derive_chapter(
    *, explicit: str | None, configured: str | None, filename_stem: str, text: str
) -> tuple[str, str]:
    """Fixed precedence, returned with the rule that decided it."""
    if explicit:
        return str(explicit), "explicit"
    if configured:
        return str(configured), "config"
    fm = _FRONT_MATTER_RE.match(text)
    if fm:
        m = re.search(r"^chapter:\s*[\"']?([A-Za-z0-9]+)[\"']?\s*$", fm.group(1), re.M)
        if m:
            return m.group(1), "front_matter"
    m = _FILENAME_CHAPTER_RE.match(filename_stem)
    if m:
        raw = m.group(1) or m.group(2)
        return (raw.lstrip("0") or "0"), "filename"
    m = _HEADING_CHAPTER_RE.search(text)
    if m:
        return m.group(1), "heading"
    m = _FIRST_LABEL_RE.search(text)
    if m:
        return m.group(1), "first_label"
    return "0", "default"


def derive_slug(*, explicit: str | None, configured: str | None, filename_stem: str) -> tuple[str, str]:
    if explicit:
        return _SLUG_ALLOWED.sub("", explicit.lower()), "explicit"
    if configured:
        return _SLUG_ALLOWED.sub("", configured.lower()), "config"
    # Strip a leading numeric prefix like "01_" before abbreviating.
    stem = re.sub(r"^\d+[_\-.]*", "", filename_stem) or filename_stem
    return abbreviate_slug(stem), "filename"
