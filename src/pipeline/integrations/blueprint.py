"""Blueprint / TCSlib adapter.

Report 05 reconstructed how leanblueprint is used in this project and recommended the
**minimum** integration artifact, explicitly warning against elaborate synchronisation
that the evidence does not support. This module implements exactly that recommendation and
nothing beyond it.

The shape: **one record per approved declaration, and the ``.tex`` is a projection of it.**

Three consequences, each fixing a specific measured failure:

1. **Escaping happens in the projector.** Commit ``d9567d5`` in the historical repository
   applied 803 underscore escapes, 7 ampersands, 55 ``B&M`` fixes and 5 unclosed maths
   spans **to generated output**, and its own message records that the generator still
   emits all of them, so regenerating would reintroduce every one. Escaping here is done
   once, in code, and survives regeneration.
2. **``\\leanok`` comes from ``#print axioms``, never from a text scan.** The historical
   generator gated it on "no ``sorry`` in the declaration's line range", using ranges that
   stop before a ``sorry`` body, and emitted ``\\leanok`` for 33 of 33 chapter-1
   declarations. Here it is emitted iff trust is ``FULLY_VERIFIED``, which no text
   heuristic can compute -- ``whitney_inequalities`` has no ``sorry`` and is not proved.
3. **Metadata leaves LaTeX.** ``\\difficulty`` and the source citations lived in macros that
   expand to nothing, purely so Python could parse them back out. They are fields on the
   record now; the projector still emits the macros so the existing downstream tooling
   keeps working.

One addition beyond the strict minimum, argued in report 05 §5.4: **proof environments**.
The historical blueprint has 3,481 statements and five ``\\begin{proof}`` blocks, so it
cannot express how much of the project is proved -- the project's central quantity. Two
lines in the projector fix that.

Everything Blueprint-specific lives in this module. The core pipeline does not import it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.models import (
    OBJECT_KINDS,
    DeclarationRecord,
    ReviewStatus,
    SourceItemKind,
    TrustStatus,
)

__all__ = [
    "BlueprintRecord",
    "build_blueprint_records",
    "render_blueprint_tex",
    "write_blueprint",
    "latex_escape",
    "BLUEPRINT_ADAPTER_VERSION",
]

BLUEPRINT_ADAPTER_VERSION = "blueprint/v1"

#: leanblueprint environment for each source kind.
_ENVIRONMENT: dict[SourceItemKind, str] = {
    SourceItemKind.DEFINITION: "definition",
    SourceItemKind.CONSTRUCTION: "definition",
    SourceItemKind.NOTATION: "definition",
    SourceItemKind.THEOREM: "theorem",
    SourceItemKind.LEMMA: "lemma",
    SourceItemKind.COROLLARY: "corollary",
    SourceItemKind.PROPOSITION: "proposition",
    SourceItemKind.EXERCISE: "lemma",
    SourceItemKind.EXAMPLE: "example",
    SourceItemKind.REMARK: "remark",
}

#: Characters LaTeX treats specially outside maths mode. Applied only outside `$...$`.
_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
_MATH_SPAN_RE = re.compile(r"(\$\$.*?\$\$|\$[^$]*\$)", re.S)
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")


def latex_escape(text: str, *, in_math_ok: bool = True) -> str:
    """Escape text for LaTeX, leaving maths spans alone.

    The historical corpus is Markdown with inline LaTeX, so a naive escape would destroy
    every formula and a naive pass-through leaves 803 unescaped underscores. Splitting on
    maths spans first is what makes both correct.

        >>> latex_escape("edge_count of $G_1$ is 50%")
        'edge\\\\_count of $G_1$ is 50\\\\%'
    """
    def escape_plain(chunk: str) -> str:
        # Markdown code spans become \texttt{}, with their contents escaped.
        def code(m: re.Match[str]) -> str:
            inner = "".join(_ESCAPES.get(c, c) for c in m.group(1))
            return r"\texttt{" + inner + "}"

        chunk = _CODE_SPAN_RE.sub(code, chunk)
        out = []
        i = 0
        while i < len(chunk):
            if chunk.startswith(r"\texttt{", i):
                depth, j = 0, i
                while j < len(chunk):
                    if chunk[j] == "{":
                        depth += 1
                    elif chunk[j] == "}":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                out.append(chunk[i:j])
                i = j
                continue
            out.append(_ESCAPES.get(chunk[i], chunk[i]))
            i += 1
        return "".join(out)

    if not in_math_ok:
        return escape_plain(text)
    parts = _MATH_SPAN_RE.split(text)
    return "".join(p if p.startswith("$") else escape_plain(p) for p in parts)


def _title(record: DeclarationRecord) -> str:
    """A short human title. Never a raw Lean name, which is what produced 803 escapes."""
    source = record.source
    if source.name:
        return source.name
    if source.label:
        return f"{record.kind.value.capitalize()} {source.label}"
    return record.id


@dataclass
class BlueprintRecord:
    """One approved declaration, in the shape the blueprint needs.

    This, not the ``.tex``, is the integration artifact. The ``.tex`` is generated from it.
    """

    declaration_id: str
    lean_name: str
    module: str | None
    environment: str
    title: str
    informal: str
    source: dict[str, object]
    uses: list[str] = field(default_factory=list)
    trust_status: str = TrustStatus.UNKNOWN.value
    axioms: list[str] = field(default_factory=list)
    review_status: str = ReviewStatus.UNREVIEWED.value
    difficulty: int | None = None
    statement_sources: list[str] = field(default_factory=list)
    proof_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    provenance: dict[str, object] = field(default_factory=dict)

    @property
    def statement_formalized(self) -> bool:
        """The statement exists in Lean and compiles. This is what ``\\leanok`` asserts."""
        return self.trust_status not in (
            TrustStatus.COMPILE_FAILURE.value, TrustStatus.UNKNOWN.value
        )

    @property
    def proof_formalized(self) -> bool:
        """Proved, per the kernel. The only thing that earns a green node."""
        return self.trust_status == TrustStatus.FULLY_VERIFIED.value

    @property
    def not_ready(self) -> bool:
        """Vacuous or unbuildable: visibly different from merely unproved."""
        return self.trust_status in (
            TrustStatus.UNFINISHED_CONSTRUCTION.value,
            TrustStatus.BLOCKED_BY_UNTRUSTED_DEPENDENCY.value,
            TrustStatus.COMPILE_FAILURE.value,
        )

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, ensure_ascii=False)


def build_blueprint_records(
    registry: CorpusRegistry,
    chapter: str | int,
    *,
    require_approval: bool = True,
) -> list[BlueprintRecord]:
    """Project the corpus into blueprint records.

    Report 05 §4 answers "when should Blueprint first learn about a declaration?" with
    **Lean statement approved** -- early enough for the blueprint to show work in progress,
    which is what leanblueprint is for, and late enough that ``\\lean{}`` resolves. So the
    default admits approved declarations only; ``require_approval=False`` is for previewing.
    """
    records: list[BlueprintRecord] = []
    for record in registry.declarations_in_chapter(chapter):
        if not record.lean.name or not record.lean.statement:
            continue
        if require_approval and record.review.status is not ReviewStatus.APPROVED:
            continue

        uses = []
        for dependency_id in registry.prerequisites(record.id, include_mathlib=False):
            dependency = registry.resolve(dependency_id)
            if dependency and dependency.lean.name:
                uses.append(dependency.lean.name)

        annotation = record.annotation
        informal = _informal_prose(record)
        notes = []
        for mapping in record.mappings:
            if mapping.semantic_status.value != "equivalent":
                notes.append(
                    f"{mapping.aspect}: rendered as {mapping.lean_form} "
                    f"({mapping.mapping_type.value}, {mapping.semantic_status.value})"
                )

        records.append(BlueprintRecord(
            declaration_id=record.id,
            lean_name=record.lean.name,
            module=record.lean.module,
            environment=_ENVIRONMENT.get(record.kind, "lemma"),
            title=_title(record),
            informal=informal,
            source={
                "document": record.source.document_id,
                "chapter": record.source.chapter,
                "section": record.source.section,
                "label": record.source.label,
                "printed_page": record.source.span.printed_page if record.source.span else None,
                "statement": record.source.statement,
            },
            uses=sorted(set(uses)),
            trust_status=record.trust.status.value,
            axioms=list(record.trust.axioms),
            review_status=record.review.status.value,
            difficulty=annotation.difficulty if annotation else None,
            notes=notes,
            provenance={
                "adapter": BLUEPRINT_ADAPTER_VERSION,
                "lean_file": record.lean.file,
                "lean_line": record.lean.line,
            },
        ))
    return records


def _informal_prose(record: DeclarationRecord) -> str:
    """The informal description, from the annotation where there is one.

    Deliberately does **not** reproduce the book's verbatim statement. The historical
    generator stripped those by a rule its own author documented as "not airtight", leaking
    14 of 269 records; here the source text is carried in the *record's* ``source`` field
    for provenance and simply never rendered into the ``.tex``.
    """
    annotation = record.annotation
    parts: list[str] = []
    if annotation and annotation.conclusion:
        parts.append(annotation.conclusion)
    if annotation and annotation.stated_hypotheses:
        parts.append("Hypotheses: " + "; ".join(annotation.stated_hypotheses) + ".")
    if not parts and record.lean.declaration_kind in OBJECT_KINDS:
        parts.append(f"The object introduced by `{record.lean.name}`.")
    if not parts:
        parts.append(f"See `{record.lean.name}`.")
    return " ".join(parts)


def render_blueprint_tex(
    records: list[BlueprintRecord], *, chapter_title: str, section_title: str | None = None
) -> str:
    """Render blueprint records as leanblueprint LaTeX."""
    lines = [
        f"\\chapter{{{latex_escape(chapter_title)}}}",
        "%" * 79,
        f"\\section{{{latex_escape(section_title or chapter_title)}}}",
        "",
        f"% Generated by {BLUEPRINT_ADAPTER_VERSION} from approved declarations.",
        "% Every field here is derived: \\leanok from #print axioms, \\uses from the",
        "% compiler's dependency graph, \\difficulty from the annotation IR.",
        "% Edit the pipeline, not this file.",
        "",
    ]
    for record in records:
        lines.append(f"\\begin{{{record.environment}}}[{latex_escape(record.title)}]")
        lines.append(f"\\lean{{{record.lean_name}}}")
        lines.append(f"\\label{{{record.lean_name}}}")
        if record.not_ready:
            lines.append("\\notready")
        elif record.statement_formalized:
            lines.append("\\leanok")
        if record.uses:
            lines.append("\\uses{" + ", ".join(record.uses) + "}")
        if record.difficulty is not None and record.environment != "definition":
            # leanblueprint's scale is 1-7; the annotation grades 0-100.
            lines.append(f"\\difficulty{{{max(1, min(7, round(record.difficulty / 100 * 6) + 1))}}}")
        for source_id in record.statement_sources:
            lines.append(f"\\statementsource{{{source_id}}}{{}}")
        lines.append(latex_escape(record.informal))
        for note in record.notes:
            lines.append(f"\\emph{{Source correspondence:}} {latex_escape(note)}")
        lines.append(f"\\end{{{record.environment}}}")

        # Proof environments: the historical blueprint has 3,481 statements and five of
        # these, so it cannot show how much is proved. Two lines fix that.
        if record.environment != "definition":
            lines.append("\\begin{proof}")
            if record.proof_formalized:
                lines.append("\\leanok")
                lines.append(f"Formalized; see \\texttt{{{latex_escape(record.lean_name)}}}.")
            elif record.not_ready:
                lines.append("Not yet statable: " + latex_escape(record.trust_status.lower().replace("_", " ")) + ".")
            else:
                lines.append("Not yet formalized.")
            lines.append("\\end{proof}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_blueprint(
    registry: CorpusRegistry,
    chapter: str | int,
    *,
    out_dir: str | Path,
    chapter_title: str,
    require_approval: bool = True,
) -> dict[str, object]:
    """Write both artifacts: the JSONL record set, and the ``.tex`` projected from it."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = build_blueprint_records(registry, chapter, require_approval=require_approval)

    jsonl = out_dir / f"chapter-{chapter}.jsonl"
    jsonl.write_text("".join(r.to_json() + "\n" for r in records), encoding="utf-8")
    tex = out_dir / f"chapter-{chapter}.tex"
    tex.write_text(render_blueprint_tex(records, chapter_title=chapter_title), encoding="utf-8")

    return {
        "records": len(records),
        "jsonl": str(jsonl),
        "tex": str(tex),
        "leanok": sum(1 for r in records if r.statement_formalized and not r.not_ready),
        "proved": sum(1 for r in records if r.proof_formalized),
        "notready": sum(1 for r in records if r.not_ready),
        "skipped_unapproved": sum(
            1 for r in registry.declarations_in_chapter(chapter)
            if r.lean.name and r.review.status is not ReviewStatus.APPROVED
        ) if require_approval else 0,
    }
