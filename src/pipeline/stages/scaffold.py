"""Assemble accepted formalization proposals into a compilable Lean module.

This is the bridge between stage 2 and stage 3: the integrity checker needs a real file
that Lean can elaborate, and the proof stage needs somewhere to put a proof.

Two properties matter and are enforced here:

* **Dependency order.** Declarations are emitted in topological order over the Lean
  dependency graph so the module elaborates in one pass.
* **Provenance in the file.** Each declaration carries its source identity, printed page,
  and the verbatim book statement as a doc comment. Report 01 §B2: the summer's Lean was
  joined to the book only by string-matching on headings, and the terminal dataset lost
  the connection entirely. Here the id is in the file.

Only ``PROPOSED`` proposals are emitted. ``NEEDS_DESIGN`` and ``FAILED`` are listed in the
module header instead, so what is missing is visible rather than silently absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.models import DeclarationRecord, ProposalStatus, SorryKind

__all__ = [
    "render_scaffold",
    "ScaffoldPlan",
    "plan_scaffold",
    "split_modifiers",
    "replace_sorry",
    "strip_doc_comment",
]

SCAFFOLD_VERSION = "scaffold/v1"

#: Lines that must precede a doc comment rather than follow it. Lean attaches `/-- -/` to
#: the *next* declaration, so an `open ... in` or an attribute emitted between the comment
#: and the declaration makes the comment attach to the modifier and the file stops
#: parsing. This is exactly the class of surface friction report 04 §B7 measured -- nine
#: of fifteen build cycles in the one instrumented summer session -- and it is cheaper to
#: get right once here than to rediscover per declaration.
_MODIFIER_PREFIXES = ("open ", "@[", "set_option ", "attribute ", "local ", "scoped ")

#: Identifier tokens, for provisional ordering only.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.']*")


def strip_doc_comment(statement: str) -> str:
    """Remove a leading ``/-- ... -/`` block from a proposed declaration.

    Models routinely write their own doc comment, which is good instinct and the wrong
    place: this renderer generates one from the record -- source label, printed page, the
    verbatim book statement, added and dropped hypotheses, and every source-to-Lean
    mapping. Two doc comments in a row would attach the first to nothing and the file
    would not parse. The record's version is canonical because it is derived rather than
    written, so the model's is dropped.
    """
    text = statement.lstrip()
    if not text.startswith("/--"):
        return statement
    depth, i = 0, 0
    while i < len(text):
        if text.startswith("/-", i):
            depth += 1
            i += 2
        elif text.startswith("-/", i):
            depth -= 1
            i += 2
            if depth == 0:
                return text[i:].lstrip("\n")
        else:
            i += 1
    return statement  # unterminated; leave it alone and let Lean report it


def replace_sorry(statement: str, proof: str) -> str:
    """Replace a declaration's `sorry` body with a proof, preserving indentation.

    The proof text is normalised to a `by` block indented two spaces, which is what the
    rest of the module uses. A proof worker returning a bare tactic sequence and one
    returning a `by` block therefore both produce valid output.
    """
    head, sep, _body = statement.rpartition(":=")
    if not sep:
        raise ValueError(f"declaration has no `:=` to replace: {statement[:80]!r}")
    text = proof.strip()
    if text.startswith("by"):
        text = text[2:].strip()
    indented = "\n".join("  " + line if line.strip() else line for line in text.splitlines())
    return f"{head.rstrip()} := by\n{indented}"


def split_modifiers(statement: str) -> tuple[list[str], str]:
    """Split leading modifier lines off a declaration.

    >>> split_modifiers("open scoped Classical in\\nnoncomputable def f := 1")
    (['open scoped Classical in'], 'noncomputable def f := 1')
    """
    lines = statement.splitlines()
    modifiers: list[str] = []
    while lines and lines[0].strip().startswith(_MODIFIER_PREFIXES):
        modifiers.append(lines.pop(0))
    return modifiers, "\n".join(lines)


@dataclass
class ScaffoldPlan:
    module: str
    records: list[DeclarationRecord]
    imports: list[str]
    excluded: list[tuple[str, str]]  # (declaration_id, reason)

    @property
    def summary(self) -> dict[str, object]:
        return {
            "module": self.module,
            "declarations": len(self.records),
            "imports": len(self.imports),
            "excluded": len(self.excluded),
        }


def plan_scaffold(
    registry: CorpusRegistry, chapter: str | int, *, module: str | None = None
) -> ScaffoldPlan:
    """Decide what goes into the module, and in what order."""
    records = registry.declarations_in_chapter(chapter)
    proposals = {p.declaration_id: p for p in registry.store.read("proposals")}  # type: ignore[misc]

    included: list[DeclarationRecord] = []
    excluded: list[tuple[str, str]] = []
    imports: set[str] = set()
    for record in records:
        proposal = proposals.get(record.id)
        if proposal is None:
            continue  # not yet formalized; simply absent, not an error
        if proposal.status is not ProposalStatus.PROPOSED:
            excluded.append((record.id, f"{proposal.status.value}: {proposal.needs_design_reason or proposal.failure_reason}"))
            continue
        included.append(record)
        imports.update(proposal.imports)

    # Emission order. Lean-extracted dependencies do not exist yet -- the module has to
    # compile before `.ilean` can be read -- so ordering uses two provisional sources:
    # the source-level dependency graph, and the identifiers each statement actually
    # mentions. These are ordering hints only; the authoritative Lean dependency edges are
    # extracted by the integrity checker after a successful build (rule 5).
    owned = {p.lean_name: did for did, p in proposals.items() if p.lean_name}
    short = {name.rsplit(".", 1)[-1]: did for name, did in owned.items()}
    in_module = {r.id for r in included}

    def textual_dependencies(record: DeclarationRecord) -> set[str]:
        statement = proposals[record.id].statement or ""
        body = statement[statement.rfind(":=") + 2 :] if ":=" in statement else statement
        found: set[str] = set()
        for token in _IDENT_RE.findall(statement):
            tail = token.rsplit(".", 1)[-1]
            target = owned.get(token) or short.get(tail)
            if target and target != record.id and target in in_module:
                found.add(target)
        for token in _IDENT_RE.findall(body):
            tail = token.rsplit(".", 1)[-1]
            target = owned.get(token) or short.get(tail)
            if target and target != record.id and target in in_module:
                found.add(target)
        return found

    ordered: list[DeclarationRecord] = []
    seen: set[str] = set()
    by_id = {r.id: r for r in included}

    def visit(record: DeclarationRecord, stack: frozenset[str]) -> None:
        if record.id in seen or record.id in stack:
            return
        deps = set(registry.prerequisites(record.id, include_mathlib=False))
        deps |= textual_dependencies(record)
        for dep_id in sorted(deps):
            dep = registry.resolve(dep_id)
            if dep is not None and dep.id in by_id:
                visit(by_id[dep.id], stack | {record.id})
        if record.id not in seen:
            seen.add(record.id)
            ordered.append(record)

    for record in included:
        visit(record, frozenset())

    return ScaffoldPlan(
        module=module or f"Ch{chapter}",
        records=ordered,
        imports=sorted(imports),
        excluded=excluded,
    )


def render_scaffold(
    registry: CorpusRegistry,
    plan: ScaffoldPlan,
    *,
    chapter_title: str = "",
    module_name: str | None = None,
    proof_bodies: dict[str, str] | None = None,
) -> str:
    """Render the Lean source for a planned module.

    ``proof_bodies`` maps a declaration id to a tactic block that replaces its
    ``sorry``. The proof verifier uses it to assemble a candidate into a scratch
    module, so a failed attempt never touches the canonical one.
    """
    proof_bodies = proof_bodies or {}
    proposals = {p.declaration_id: p for p in registry.store.read("proposals")}  # type: ignore[misc]
    lines: list[str] = []
    lines += [f"import {i}" for i in plan.imports]
    lines.append("")
    lines.append("/-!")
    lines.append(f"# {module_name or plan.module}" + (f" — {chapter_title}" if chapter_title else ""))
    lines.append("")
    lines.append(f"Generated by {SCAFFOLD_VERSION}. Statements only: every theorem body is")
    lines.append("`sorry` by construction, and each declaration carries the identity of the source")
    lines.append("item it formalizes.")
    if plan.excluded:
        lines.append("")
        lines.append("## Not emitted")
        lines.append("")
        for decl_id, reason in plan.excluded:
            lines.append(f"* `{decl_id}` — {reason}")
    lines.append("-/")
    lines.append("")

    namespaces = {proposals[r.id].namespace for r in plan.records if proposals[r.id].namespace}
    namespace = next(iter(namespaces)) if len(namespaces) == 1 else None
    if namespace:
        lines += [f"namespace {namespace}", ""]

    variables = sorted({v for r in plan.records for v in proposals[r.id].variables})
    typeclasses = sorted({t for r in plan.records for t in proposals[r.id].typeclasses if "G.Adj" not in t})
    if variables or typeclasses:
        lines.append("variable " + " ".join(variables + typeclasses))
        lines.append("")

    for record in plan.records:
        proposal = proposals[record.id]
        src = record.source
        page = f", p. {src.span.printed_page}" if src.span and src.span.printed_page else ""
        modifiers, body = split_modifiers(strip_doc_comment(proposal.statement or ""))
        # An explicit override wins (the proof verifier assembling a candidate); otherwise
        # any proof already accepted for this declaration is applied.
        proof = proof_bodies.get(record.id, record.lean.proof)
        if proof is not None:
            body = replace_sorry(body, proof)
        lines.extend(modifiers)
        lines.append("/--")
        title = src.label or src.name or record.id
        lines.append(f"**{record.kind.value.capitalize()} {title}** — declaration id `{record.id}`")
        lines.append("")
        lines.append(f"Source: §{src.section or '?'}{page}, verbatim:")
        lines.append("")
        for para in src.statement.splitlines():
            lines.append(f"> {para}")
        if proposal.hypotheses_added:
            lines += ["", "Hypotheses added, with reasons:"]
            lines += [f"* {h}" for h in proposal.hypotheses_added]
        if proposal.hypotheses_dropped:
            lines += ["", "⚠ Hypotheses dropped:"]
            lines += [f"* {h}" for h in proposal.hypotheses_dropped]
        if proposal.mappings:
            lines += ["", "Source ↔ Lean:"]
            for m in proposal.mappings:
                lines.append(f"* {m.aspect}: `{m.source_form}` → `{m.lean_form}` "
                             f"({m.mapping_type.value}, {m.semantic_status.value})")
        blocking = [w for w in proposal.design_warnings if w.blocks]
        if blocking:
            lines += ["", "⚠ Blocking design warnings:"]
            lines += [f"* {w.code}: {w.message}" for w in blocking]
        if proposal.sorry_kind is SorryKind.OBJECT_PENDING:
            lines += ["", "⚠ UNFINISHED CONSTRUCTION: this object has no body, so every statement",
                      "about it is vacuous rather than merely unproved."]
        lines.append("-/")
        lines.append(body)
        lines.append("")

    if namespace:
        lines.append(f"end {namespace}")
    return "\n".join(lines) + "\n"
