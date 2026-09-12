"""The annotated Markdown IR (``annotated/v1``): parse, validate, assign ids, register.

Layout (stdlib-parseable: a ``key: value`` front matter and one JSON block per item)::

    ---
    math-tcs: annotated/v1
    slug: dn
    chapter: 1
    title: Unit 1 — Divisibility
    source_path: /abs/path/01_unit-1-divisibility.md
    source_sha256: …
    ---
    # Unit 1 — Divisibility

    ## Conventions
    - "Throughout this unit $a$, $b$ and $c$ denote natural numbers." → all variables range over ℕ

    ## Open questions
    - none

    ## dn-ch1-thm-1.1
    ```json math-tcs
    {"id": "dn-ch1-thm-1.1", "kind": "theorem", "label": "1.1", …}
    ```
    ### Source statement (verbatim)
    > If $a \\mid b$ and $b \\mid c$, then $a \\mid c$.
    ### Source proof (verbatim)
    > Write $b = a q$ … □
    ### Interpretation (agent)
    prose …

Source content lives only in the two verbatim blockquotes; everything else is the
agent's interpretation. A missing proof is written as exactly ``_No proof in source._``.
Unlabelled items are emitted with id ``TBD`` and get ``section+ordinal`` ids from the
located verbatim quote (``validate --assign-ids``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import ids as ids_mod
from . import source_items
from .util import MathTcsError, sha256_text, write_text_atomic

__all__ = ["VERSION", "parse", "validate", "assign_ids", "render_skeleton", "section_for", "NO_PROOF"]

VERSION = "annotated/v1"
NO_PROOF = "_No proof in source._"
REQUIRED_FIELDS = ("id", "kind", "statement_nl", "hypotheses", "conclusion", "has_source_proof")
_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.M)
_H3_STATEMENT = "### Source statement (verbatim)"
_H3_PROOF = "### Source proof (verbatim)"
_H3_INTERP = "### Interpretation (agent)"
_JSON_BLOCK_RE = re.compile(r"```json\s+math-tcs\s*\n(?P<body>.*?)\n```", re.S)
_TBD_RE = re.compile(r"^TBD(?:-\d+)?$")
_LEANISH_RE = re.compile(r"(:=\s*by\b|```lean|\btheorem\s+[A-Za-z_]|\blemma\s+[A-Za-z_]|\bsorry\b)")


def _front_matter(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"')
    return fm, text[m.end():]


def _blockquote(section: str, heading: str, next_headings: tuple[str, ...]) -> str | None:
    start = section.find(heading)
    if start < 0:
        return None
    body_start = start + len(heading)
    end = len(section)
    for h in next_headings:
        k = section.find(h, body_start)
        if 0 <= k < end:
            end = k
    body = section[body_start:end]
    if NO_PROOF in body:
        return None
    quote_lines = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith(">"):
            quote_lines.append(s[1:].strip())
        elif s == "" and quote_lines:
            quote_lines.append("")
    joined = "\n".join(quote_lines).strip()
    return joined or None


def parse(text: str) -> dict:
    """Parse without validating. Every item section becomes a declaration dict."""
    fm, body = _front_matter(text)
    heads = list(_H2_RE.finditer(body))
    declarations: list[dict] = []
    conventions: list[str] = []
    open_questions: list[str] = []
    for idx, h in enumerate(heads):
        title = h.group("title").strip()
        sec_start = h.end()
        sec_end = heads[idx + 1].start() if idx + 1 < len(heads) else len(body)
        section = body[sec_start:sec_end]
        low = title.lower()
        if low.startswith("conventions"):
            conventions = [l.strip()[2:].strip() for l in section.splitlines() if l.strip().startswith("- ")]
            continue
        if low.startswith("open questions"):
            open_questions = [l.strip()[2:].strip() for l in section.splitlines() if l.strip().startswith("- ")]
            continue
        jm = _JSON_BLOCK_RE.search(section)
        meta: dict = {}
        json_error = None
        if jm:
            try:
                meta = json.loads(jm.group("body"))
            except json.JSONDecodeError as exc:
                json_error = f"invalid JSON block: {exc}"
        else:
            json_error = "missing ```json math-tcs block"
        statement_q = _blockquote(section, _H3_STATEMENT, (_H3_PROOF, _H3_INTERP))
        proof_present = _H3_PROOF in section
        proof_q = _blockquote(section, _H3_PROOF, (_H3_INTERP,)) if proof_present else None
        interp = section.split(_H3_INTERP, 1)[1].strip() if _H3_INTERP in section else ""
        declarations.append({
            "heading": title,
            "id": (meta.get("id") if isinstance(meta, dict) else None) or title,
            "meta": meta if isinstance(meta, dict) else {},
            "json_error": json_error,
            "source_statement": statement_q,
            "source_proof": proof_q,
            "proof_section_present": proof_present,
            "interpretation": interp,
            "section_text": h.group(0) + section,
            "section_sha256": sha256_text((h.group(0) + section).strip() + "\n"),
            "span": [sec_start, sec_end],
        })
    return {"front_matter": fm, "conventions": conventions, "open_questions": open_questions,
            "declarations": declarations, "_body": body, "_heads": [(h.start(), h.end()) for h in heads]}


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _norm_map(lines: list[str]) -> tuple[str, list[int]]:
    """Whitespace-normalised text of the source plus, per normalised char, its 0-based line."""
    chars: list[str] = []
    line_of: list[int] = []
    prev_space = True
    for li, line in enumerate(lines):
        for ch in line:
            if ch.isspace():
                if not prev_space:
                    chars.append(" "); line_of.append(li); prev_space = True
            else:
                chars.append(ch); line_of.append(li); prev_space = False
        if not prev_space:
            chars.append(" "); line_of.append(li); prev_space = True
    return "".join(chars), line_of


def _locate(source_lines: list[str], quote: str) -> tuple[int, int] | None:
    """1-based inclusive line span of a verbatim quote in the source (whitespace-insensitive)."""
    target = _norm_ws(quote)
    if not target:
        return None
    text, line_of = _norm_map(source_lines)
    idx = text.find(target)
    if idx < 0:
        return None
    end = min(idx + len(target) - 1, len(line_of) - 1)
    return line_of[idx] + 1, line_of[end] + 1


def _section_at(source_lines: list[str], line: int) -> str | None:
    sec = None
    for idx in range(min(line, len(source_lines))):
        m = source_items.SECTION_RE.match(source_lines[idx])
        if m:
            sec = m.group("num")
    return sec


def validate(text: str, *, source_text: str | None, slug: str | None, chapter: str | None) -> dict:
    doc = parse(text)
    errors: list[str] = []
    warnings: list[str] = []
    fm = doc["front_matter"]
    if fm.get("math-tcs") != VERSION:
        errors.append(f"front matter `math-tcs` must be {VERSION}")
    slug = slug or fm.get("slug")
    chapter = chapter or fm.get("chapter")
    if not slug:
        errors.append("front matter needs `slug`")
    if not chapter:
        errors.append("front matter needs `chapter`")
    src_lines = source_text.splitlines() if source_text is not None else None
    seen: set[str] = set()
    for d in doc["declarations"]:
        tag = d["heading"]
        if d["json_error"]:
            errors.append(f"{tag}: {d['json_error']}")
            continue
        meta = d["meta"]
        for f in REQUIRED_FIELDS:
            if f not in meta:
                errors.append(f"{tag}: json field `{f}` missing")
        kind = meta.get("kind")
        if kind not in ids_mod.KIND_CODE:
            errors.append(f"{tag}: kind {kind!r} not in {sorted(ids_mod.KIND_CODE)}")
        mid = str(meta.get("id", ""))
        if not _TBD_RE.match(mid):
            try:
                parsed = ids_mod.parse_declaration_id(mid)
                if slug and parsed["slug"] != slug:
                    errors.append(f"{tag}: id slug {parsed['slug']!r} ≠ document slug {slug!r}")
                if kind in ids_mod.KIND_CODE and parsed["kind"] != ids_mod.KIND_CODE[kind]:
                    errors.append(f"{tag}: id kind code {parsed['kind']!r} ≠ kind {kind!r}")
            except ids_mod.IdentityError as exc:
                errors.append(f"{tag}: {exc}")
            if mid != tag:
                errors.append(f"{tag}: heading must equal the json id ({mid})")
            if mid in seen:
                errors.append(f"{tag}: duplicate id")
            seen.add(mid)
        if not d["source_statement"]:
            errors.append(f"{tag}: `{_H3_STATEMENT}` blockquote missing or empty")
        if not d["proof_section_present"]:
            errors.append(f"{tag}: `{_H3_PROOF}` section missing (use `{NO_PROOF}` when absent)")
        has_proof = meta.get("has_source_proof")
        if has_proof is True and d["source_proof"] is None:
            errors.append(f"{tag}: has_source_proof is true but no verbatim proof was given")
        if has_proof is False and d["source_proof"]:
            errors.append(f"{tag}: has_source_proof is false but a proof blockquote is present")
        for field in ("statement_nl", "conclusion"):
            v = meta.get(field)
            if isinstance(v, str) and _LEANISH_RE.search(v):
                warnings.append(f"{tag}: `{field}` looks like Lean code; the IR is natural language")
        if isinstance(meta.get("hypotheses"), list) and any(_LEANISH_RE.search(str(h)) for h in meta["hypotheses"]):
            warnings.append(f"{tag}: a hypothesis looks like Lean code")
        if src_lines is not None and d["source_statement"]:
            loc = _locate(src_lines, d["source_statement"])
            if loc is None:
                errors.append(f"{tag}: verbatim statement not found in the source (must be copied character for character)")
            else:
                d["located"] = {"lines": list(loc), "section": _section_at(src_lines, loc[0])}
            if d["source_proof"]:
                ploc = _locate(src_lines, d["source_proof"][:200])
                if ploc is None:
                    warnings.append(f"{tag}: verbatim proof not located in the source")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "slug": slug, "chapter": chapter,
            "declarations": [{"id": d["id"], "kind": d["meta"].get("kind"), "label": d["meta"].get("label"),
                              "located": d.get("located"), "section_sha256": d["section_sha256"]} for d in doc["declarations"]],
            "_doc": doc}


def assign_ids(text: str, *, source_text: str, slug: str, chapter: str) -> tuple[str, list[dict], list[str]]:
    """Replace ``TBD`` ids with section+ordinal ids. Returns ``(new_text, assignments, errors)``."""
    doc = parse(text)
    src_lines = source_text.splitlines()
    tbd: list[tuple[dict, int, str]] = []
    errors: list[str] = []
    for d in doc["declarations"]:
        mid = str(d["meta"].get("id", d["heading"]))
        if not _TBD_RE.match(mid):
            continue
        if not d["source_statement"]:
            errors.append(f"{d['heading']}: cannot assign an id without a verbatim statement")
            continue
        loc = _locate(src_lines, d["source_statement"])
        if loc is None:
            errors.append(f"{d['heading']}: verbatim statement not found in the source; cannot assign an id")
            continue
        sec = _section_at(src_lines, loc[0]) or "0"
        tbd.append((d, loc[0], sec))
    # ordinal = position among unlabelled items of the same kind in the same section, by source line
    counters: dict[tuple[str, str], list[tuple[int, dict]]] = {}
    for d, line, sec in tbd:
        counters.setdefault((d["meta"].get("kind"), sec), []).append((line, d))
    assignments: list[dict] = []
    new_text = text
    for (kind, sec), lst in counters.items():
        lst.sort(key=lambda t: t[0])
        for ordinal, (line, d) in enumerate(lst, start=1):
            try:
                new_id = ids_mod.declaration_id(slug, chapter, kind, section=sec, ordinal=ordinal)
            except ids_mod.IdentityError as exc:
                errors.append(f"{d['heading']}: {exc}")
                continue
            old_heading = f"## {d['heading']}"
            new_text = new_text.replace(old_heading, f"## {new_id}", 1)
            new_text = re.sub(r'("id"\s*:\s*")TBD(?:-\d+)?(")', rf"\g<1>{new_id}\g<2>", new_text, count=1)
            assignments.append({"heading": d["heading"], "id": new_id, "section": sec, "line": line})
    return new_text, assignments, errors


def section_for(text: str, decl_id: str) -> dict | None:
    doc = parse(text)
    for d in doc["declarations"]:
        if d["id"] == decl_id:
            return {k: v for k, v in d.items() if not k.startswith("_") and k != "span"}
    return None


def render_skeleton(*, slug: str, chapter: str, title: str, source_path: str, source_sha256: str, items: list[dict]) -> str:
    lines = ["---", f"math-tcs: {VERSION}", f"slug: {slug}", f"chapter: {chapter}", f"title: {title}",
             f"source_path: {source_path}", f"source_sha256: {source_sha256}", "---", f"# {title}", "",
             "## Conventions", "- (quote each section-wide convention verbatim → its meaning)", "",
             "## Open questions", "- none", ""]
    for it in items:
        meta = {"id": it["id"], "kind": it["kind"], "label": it.get("label"), "section": it.get("section"),
                "page": it.get("page"), "name": "", "statement_nl": "", "hypotheses": [], "conclusion": "",
                "variables": [], "definitions_used": [], "depends_on": [],
                "has_source_proof": bool(it.get("proof")), "mathlib_candidates": [],
                "difficulty": {"estimate": "", "reason": ""}, "questions": []}
        lines += [f"## {it['id']}", "```json math-tcs", json.dumps(meta, ensure_ascii=False, indent=2), "```",
                  _H3_STATEMENT]
        lines += [f"> {l}" for l in (it.get("statement") or "").splitlines()]
        lines.append(_H3_PROOF)
        if it.get("proof"):
            lines += [f"> {l}" for l in it["proof"].splitlines()]
        else:
            lines.append(NO_PROOF)
        lines += [_H3_INTERP, "", ""]
    return "\n".join(lines)


def write(path: Path, text: str) -> None:
    write_text_atomic(path, text if text.endswith("\n") else text + "\n")
