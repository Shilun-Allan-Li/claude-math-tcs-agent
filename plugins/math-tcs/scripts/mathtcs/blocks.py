"""Marker-delimited declaration blocks inside a generated Lean module.

A module owns one ``namespace`` and a sequence of blocks::

    -- math-tcs:begin id=dn-ch1-thm-1.1 rev=1
    /-- generated doc comment -/
    theorem divides_trans (hab : Divides a b) (hbc : Divides b c) : Divides a c := by
      sorry
    -- math-tcs:end id=dn-ch1-thm-1.1

Markers are line comments (whitespace to Lean's parser); the doc comment still attaches
to the next declaration. Modifier lines (``open … in``, ``@[…]``, ``set_option``) are
hoisted above the doc comment (ported ``split_modifiers``); a model-written doc comment
is stripped in favour of the generated one (ported ``strip_doc_comment``). A block may
contain helper lemmas *before* its main declaration (the prover adds them); the main
declaration is the last declaration in the block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .util import sha256_text

__all__ = [
    "Block", "parse_blocks", "block_by_id", "split_statement", "replace_proof",
    "split_modifiers", "strip_doc_comment", "declarations_in", "render_block",
    "render_module", "upsert_block", "remove_block", "merge_imports", "module_imports",
    "namespace_of", "statement_sha", "block_sha", "BEGIN_RE", "END_RE",
]

BEGIN_RE = re.compile(r"^--\s*math-tcs:begin\s+id=(?P<id>[A-Za-z0-9.\-]+)\s+rev=(?P<rev>\d+)\s*$")
END_RE = re.compile(r"^--\s*math-tcs:end\s+id=(?P<id>[A-Za-z0-9.\-]+)\s*$")
_MODIFIER_PREFIXES = ("open ", "@[", "set_option ", "attribute ", "local ", "scoped ")
_DECL_RE = re.compile(
    r"^(?P<mods>(?:(?:private|protected|noncomputable|nonrec|unsafe|partial)\s+)*)"
    r"(?P<kw>theorem|lemma|def|abbrev|instance|structure|inductive|class|opaque|axiom|example)\b"
    r"\s*(?P<name>[A-Za-z_][A-Za-z0-9_.'!?]*)?"
)
_NAMESPACE_RE = re.compile(r"^namespace\s+([A-Za-z_][A-Za-z0-9_.]*)\s*$", re.M)
_END_NS_RE = re.compile(r"^end\s+([A-Za-z_][A-Za-z0-9_.]*)\s*$", re.M)
_IMPORT_RE = re.compile(r"^import\s+(\S+)\s*$", re.M)
_TACTIC_RE = re.compile(
    r"\b(by|exact|apply|intro|intros|rcases|obtain|refine|simp|omega|decide|linarith|nlinarith|"
    r"norm_num|aesop|rw|rewrite|induction|cases|constructor|use|calc|unfold|ring|field_simp|"
    r"positivity|tauto|trivial|contradiction|exfalso|have|show|specialize|subst|ext|funext)\b"
)


@dataclass
class Block:
    id: str
    rev: int
    start: int      # index of the begin-marker line
    end: int        # index of the end-marker line
    inner: str      # text strictly between the markers (no trailing newline)

    @property
    def sha(self) -> str:
        return block_sha(self.inner)


def block_sha(inner: str) -> str:
    return sha256_text(inner.strip() + "\n")


def parse_blocks(text: str) -> list[Block]:
    lines = text.splitlines()
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        m = BEGIN_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        bid, rev = m.group("id"), int(m.group("rev"))
        j = i + 1
        while j < len(lines):
            e = END_RE.match(lines[j].strip())
            if e and e.group("id") == bid:
                break
            if BEGIN_RE.match(lines[j].strip()):
                raise ValueError(f"block {bid} has no end marker before the next begin marker (line {j + 1})")
            j += 1
        if j >= len(lines):
            raise ValueError(f"block {bid} has no end marker")
        blocks.append(Block(id=bid, rev=rev, start=i, end=j, inner="\n".join(lines[i + 1:j])))
        i = j + 1
    return blocks


def block_by_id(text: str, decl_id: str) -> Block | None:
    for b in parse_blocks(text):
        if b.id == decl_id:
            return b
    return None


def namespace_of(text: str) -> str | None:
    m = _NAMESPACE_RE.search(text)
    return m.group(1) if m else None


def module_imports(text: str) -> list[str]:
    return _IMPORT_RE.findall(text)


# ------------------------------------------------------------------ declaration surgery

def strip_doc_comment(statement: str) -> str:
    text = statement.lstrip()
    if not text.startswith("/--"):
        return statement
    depth, i = 0, 0
    while i < len(text):
        if text.startswith("/-", i):
            depth += 1; i += 2
        elif text.startswith("-/", i):
            depth -= 1; i += 2
            if depth == 0:
                return text[i:].lstrip("\n")
        else:
            i += 1
    return statement


def split_modifiers(statement: str) -> tuple[list[str], str]:
    lines = statement.splitlines()
    modifiers: list[str] = []
    while lines and lines[0].strip().startswith(_MODIFIER_PREFIXES):
        modifiers.append(lines.pop(0))
    return modifiers, "\n".join(lines)


def _skip_comment_or_string(text: str, i: int) -> int | None:
    """If a comment or string starts at ``i``, return the index just past it."""
    if text.startswith("--", i):
        j = text.find("\n", i)
        return len(text) if j < 0 else j
    if text.startswith("/-", i):
        depth, j = 0, i
        while j < len(text):
            if text.startswith("/-", j):
                depth += 1; j += 2
            elif text.startswith("-/", j):
                depth -= 1; j += 2
                if depth == 0:
                    return j
            else:
                j += 1
        return len(text)
    if text[i] == '"':
        j = i + 1
        while j < len(text):
            if text[j] == "\\":
                j += 2; continue
            if text[j] == '"':
                return j + 1
            j += 1
        return len(text)
    return None


_OPEN = {"(": ")", "[": "]", "{": "}", "⟨": "⟩", "⦃": "⦄"}
_CLOSE = set(_OPEN.values())


def body_separator(decl: str) -> tuple[int, str] | None:
    """Index and token of the top-level body separator (``:=`` or ``where``) of a
    declaration, ignoring separators inside binders, strings and comments."""
    depth = 0
    i = 0
    n = len(decl)
    while i < n:
        skip = _skip_comment_or_string(decl, i)
        if skip is not None:
            i = skip; continue
        c = decl[i]
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth = max(0, depth - 1)
        elif depth == 0:
            if decl.startswith(":=", i):
                return i, ":="
            if decl.startswith("where", i) and (i == 0 or not decl[i - 1].isalnum()) and (i + 5 >= n or not decl[i + 5].isalnum()):
                return i, "where"
        i += 1
    return None


def split_statement(decl: str) -> tuple[str, str]:
    """``(signature, body)`` of one declaration (no doc comment). ``body`` includes the
    separator. Raises ``ValueError`` when there is no body separator."""
    sep = body_separator(decl)
    if sep is None:
        raise ValueError(f"declaration has no `:=`/`where` body separator: {decl[:80]!r}")
    i, _tok = sep
    return decl[:i].rstrip(), decl[i:]


def statement_sha(decl: str) -> str:
    sig, _ = split_statement(decl)
    return sha256_text(re.sub(r"\s+", " ", sig).strip())


def replace_proof(decl: str, proof: str) -> str:
    sig, _ = split_statement(decl)
    text = proof.strip()
    if text.startswith("by"):
        text = text[2:].strip()
    indented = "\n".join(("  " + line if line.strip() else line) for line in text.splitlines())
    return f"{sig} := by\n{indented}"


def declarations_in(inner: str) -> list[dict]:
    """Top-level declarations inside a block, in order: ``{kw, name, start, end, text}`` where
    ``start``/``end`` are 0-based line indexes into ``inner`` and ``text`` excludes the doc
    comment and modifiers. The last one is the block's main declaration."""
    lines = inner.splitlines()
    starts: list[tuple[int, str, str | None]] = []
    in_doc = False
    for idx, line in enumerate(lines):
        s = line.strip()
        if in_doc:
            if "-/" in s:
                in_doc = False
            continue
        if s.startswith("/-"):
            if "-/" not in s:
                in_doc = True
            continue
        m = _DECL_RE.match(s)
        if m:
            starts.append((idx, m.group("kw"), m.group("name")))
    decls: list[dict] = []
    for k, (idx, kw, name) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        # trim trailing blank / comment-only lines that belong to the next decl's doc
        body_lines = lines[idx:end]
        while body_lines and (not body_lines[-1].strip() or body_lines[-1].strip().startswith("--") or body_lines[-1].strip().startswith("/-") or body_lines[-1].strip().startswith("@[")):
            if body_lines[-1].strip().startswith("--") and not body_lines[-1].strip().startswith("--"):
                break
            body_lines.pop()
        decls.append({"kw": kw, "name": name, "start": idx, "end": idx + len(body_lines), "text": "\n".join(body_lines)})
    return decls


def main_declaration(inner: str) -> dict | None:
    decls = declarations_in(inner)
    return decls[-1] if decls else None


def classify_body(decl_text: str, kind: str) -> str:
    """``definition`` (object kinds), ``sorry``, ``structural`` or ``proof``."""
    if kind in {"def", "abbrev", "instance", "structure", "inductive", "class", "opaque"}:
        return "definition"
    try:
        _sig, body = split_statement(decl_text)
    except ValueError:
        return "no_body"
    b = body[2:].strip() if body.startswith(":=") else body
    normalised = re.sub(r"\s+", " ", b.removeprefix("by").strip())
    if normalised == "sorry":
        return "sorry"
    if b.startswith("by") or _TACTIC_RE.search(b):
        return "proof"
    return "structural"


# ------------------------------------------------------------------------- rendering

def render_doc_comment(spec: dict) -> str:
    """Generated doc comment. ``spec`` keys: kind, label, id, source_ref, source_statement,
    source_proof (None for absent), difficulty {estimate, reason}, deviations [str],
    blockers [str], extra (str|None)."""
    kind = (spec.get("kind") or "declaration").capitalize()
    label = spec.get("label") or spec.get("name") or spec["id"]
    lines = ["/--", f"**{kind} {label}** — math-tcs id `{spec['id']}`", ""]
    lines.append(f"Source: {spec.get('source_ref', '?')}, verbatim:")
    lines.append("")
    for para in (spec.get("source_statement") or "").splitlines():
        lines.append(f"> {para}")
    proof = spec.get("source_proof")
    lines.append("")
    if proof:
        lines.append("Proof (source, verbatim):")
        lines.append("")
        for para in proof.splitlines():
            lines.append(f"> {para}")
    else:
        lines.append("_No proof in source._")
    diff = spec.get("difficulty") or {}
    if diff:
        lines += ["", f"Difficulty (estimate): {diff.get('estimate', '?')} — {diff.get('reason', 'no reason given')}"]
    if spec.get("deviations"):
        lines += ["", "Source ↔ Lean (declared deviations):"]
        lines += [f"* {d}" for d in spec["deviations"]]
    if spec.get("blockers"):
        lines += ["", "⚠ Blockers:"]
        lines += [f"* {b}" for b in spec["blockers"]]
    if spec.get("extra"):
        lines += ["", str(spec["extra"]).rstrip()]
    lines.append("-/")
    return "\n".join(lines)


def render_block(spec: dict, statement: str, *, rev: int, proof: str | None = None,
                 helpers: list[str] | None = None) -> str:
    """Full block text including markers. ``statement`` is the declaration text (a model
    doc comment is stripped); ``helpers`` are complete helper declarations emitted before
    it; ``proof`` replaces the main declaration's body."""
    modifiers, body = split_modifiers(strip_doc_comment(statement).strip())
    if proof is not None:
        body = replace_proof(body, proof)
    parts = [f"-- math-tcs:begin id={spec['id']} rev={rev}"]
    for h in helpers or []:
        parts.append(h.strip())
        parts.append("")
    parts.extend(modifiers)
    parts.append(render_doc_comment(spec))
    parts.append(body.rstrip())
    parts.append(f"-- math-tcs:end id={spec['id']}")
    return "\n".join(parts)


def render_module(*, module_name: str, namespace: str, title: str, source_ref: str,
                  imports: list[str], blocks: list[str]) -> str:
    lines = [f"import {i}" for i in sorted(set(imports))]
    lines += ["", "/-!", f"# {module_name} — {title}", "",
              f"Generated by math-tcs from `{source_ref}`. Blocks are delimited by",
              "`-- math-tcs:begin/end` markers; theorem bodies are `sorry` until proved and",
              "each declaration carries the identity of the source item it formalizes.", "-/", ""]
    lines += [f"namespace {namespace}", ""]
    for b in blocks:
        lines.append(b.rstrip())
        lines.append("")
    lines.append(f"end {namespace}")
    return "\n".join(lines) + "\n"


def merge_imports(text: str, imports: list[str]) -> str:
    existing = module_imports(text)
    missing = [i for i in imports if i not in existing]
    if not missing:
        return text
    lines = text.splitlines()
    last_import = -1
    for idx, line in enumerate(lines):
        if _IMPORT_RE.match(line):
            last_import = idx
    insert_at = last_import + 1
    new_lines = lines[:insert_at] + [f"import {i}" for i in missing] + lines[insert_at:]
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")


def upsert_block(text: str, block_text: str, *, decl_id: str, expect_sha: str | None = None,
                 force: bool = False, protect: bool = False) -> tuple[str, str]:
    """Insert or replace the block for ``decl_id``. Returns ``(new_text, outcome)`` with
    outcome ∈ ``inserted | replaced | refused_human_edit | refused_protected | unchanged``.

    ``expect_sha`` is the sha the manifest recorded for the current block; a mismatch means
    a human edited it and the block is not touched unless ``force``. ``protect`` refuses
    replacement outright (proved / approved) unless ``force``."""
    existing = block_by_id(text, decl_id)
    lines = text.splitlines()
    new_block_lines = block_text.rstrip("\n").splitlines()
    if existing is None:
        end_idx = None
        for idx in range(len(lines) - 1, -1, -1):
            if _END_NS_RE.match(lines[idx]):
                end_idx = idx
                break
        if end_idx is None:
            merged = lines + [""] + new_block_lines
        else:
            before = lines[:end_idx]
            while before and not before[-1].strip():
                before.pop()
            merged = before + [""] + new_block_lines + [""] + lines[end_idx:]
        return "\n".join(merged) + "\n", "inserted"
    if existing.inner.strip() == "\n".join(new_block_lines[1:-1]).strip():
        return text, "unchanged"
    if protect and not force:
        return text, "refused_protected"
    if expect_sha is not None and existing.sha != expect_sha and not force:
        return text, "refused_human_edit"
    merged = lines[:existing.start] + new_block_lines + lines[existing.end + 1:]
    return "\n".join(merged) + "\n", "replaced"


def remove_block(text: str, decl_id: str) -> tuple[str, bool]:
    existing = block_by_id(text, decl_id)
    if existing is None:
        return text, False
    lines = text.splitlines()
    merged = lines[:existing.start] + lines[existing.end + 1:]
    return "\n".join(merged) + "\n", True
