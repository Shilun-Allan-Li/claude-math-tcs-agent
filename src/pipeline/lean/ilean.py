"""Read the compiler's ``.ilean`` artifacts.

``.ilean`` records, per symbol, where it is defined and every position that references it.
That gives exact declaration positions and an exact dependency graph -- both extracted
from the compiler rather than inferred.

One caveat, recorded because it caused a real defect in the summer corpus: the reference
ranges are *usage* positions, so a declaration whose body is ``sorry`` produces no
references and its recorded extent stops at the signature. Report 05 §3.4 traces the false
``\\leanok`` on 33 of 33 chapter-1 declarations to exactly this. Positions here are
therefore used for *locating* declarations, never for deciding trust; trust comes from
:mod:`pipeline.lean.axioms`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["LeanDeclaration", "IleanIndex", "read_ilean"]

#: `.ilean` positions are **0-based**; `lake` diagnostics are **1-based**. Everything this
#: module returns is normalised to 1-based, so a declaration range and a build warning can
#: be compared directly. Getting this wrong shifts every range by one line and silently
#: misattributes a `sorry` to the neighbouring declaration.
_LINE_BASE_OFFSET = 1


@dataclass(frozen=True)
class LeanDeclaration:
    name: str
    module: str
    line: int
    column: int
    end_line: int
    end_column: int
    name_line: int = 0

    def contains(self, line: int) -> bool:
        return self.line <= line <= self.end_line


@dataclass
class IleanIndex:
    module: str
    declarations: dict[str, LeanDeclaration] = field(default_factory=dict)
    #: user -> set of symbols it references (local and external).
    dependencies: dict[str, set[str]] = field(default_factory=dict)
    #: symbol -> module it is defined in, for anything referenced.
    symbol_module: dict[str, str] = field(default_factory=dict)
    direct_imports: list[str] = field(default_factory=list)

    def local_dependencies(self, name: str) -> list[str]:
        """References defined in this same module."""
        return sorted(d for d in self.dependencies.get(name, ()) if d in self.declarations)

    def external_dependencies(self, name: str) -> list[str]:
        """References defined elsewhere -- Mathlib, core, other project modules."""
        return sorted(d for d in self.dependencies.get(name, ()) if d not in self.declarations)

    def reverse_dependencies(self, name: str) -> list[str]:
        return sorted(user for user, deps in self.dependencies.items() if name in deps)


def read_ilean(path: str | Path) -> IleanIndex:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    module = data.get("module", "")
    index = IleanIndex(module=module, direct_imports=list(data.get("directImports", [])))

    # `decls` maps a name to eight integers: the full declaration range (which *includes*
    # the doc comment and the body), then the range of the name itself.
    #
    #     "SimpleGraph.edgeConnectivity_le_minDegree": [86, 0, 101, 7, 99, 8, 99, 37]
    #                                                   ^full 86-101^  ^name at 99^
    #
    # The full range is what should be used to locate a declaration's text. The summer's
    # `build_dep_graph.py` instead derived ranges from the *usage* tuples in `references`,
    # which stop at the last position that produces a reference -- and a `sorry` body
    # produces none. That is the root cause of the false `\leanok` on 33 of 33 chapter-1
    # declarations (report 05 §3.4). Reading `decls` avoids the whole class of error.
    for name, span in data.get("decls", {}).items():
        if not isinstance(span, list) or len(span) < 4:
            continue
        index.declarations[name] = LeanDeclaration(
            name=name,
            module=module,
            line=int(span[0]) + _LINE_BASE_OFFSET,
            column=int(span[1]),
            end_line=int(span[2]) + _LINE_BASE_OFFSET,
            end_column=int(span[3]),
            name_line=(int(span[4]) if len(span) >= 6 else int(span[0])) + _LINE_BASE_OFFSET,
        )

    for key, value in data.get("references", {}).items():
        ident = json.loads(key) if isinstance(key, str) else key
        const = ident.get("c") or ident.get("const") or {}
        symbol = const.get("n")
        if not symbol:
            continue
        index.symbol_module.setdefault(symbol, const.get("m", ""))
        definition = value.get("definition")
        if definition and symbol not in index.declarations and const.get("m") == module:
            index.declarations[symbol] = LeanDeclaration(
                name=symbol, module=module,
                line=int(definition[0]) + _LINE_BASE_OFFSET, column=int(definition[1]),
                end_line=int(definition[2]) + _LINE_BASE_OFFSET, end_column=int(definition[3]),
                name_line=int(definition[0]) + _LINE_BASE_OFFSET,
            )
        for usage in value.get("usages", []):
            if len(usage) >= 5 and usage[4]:
                index.dependencies.setdefault(usage[4], set()).add(symbol)
    return index
