"""Lean tooling. Rule 5: Lean is authoritative for Lean facts.

Nothing in this package asks a model anything. Compile status, diagnostics, axioms,
declaration positions and dependencies all come from `lake`, from `#print axioms`, and
from the compiler's own `.ilean` artifacts.

Report 03 §0.2 is why this is a package rather than a heuristic: the summer built two
text-based `sorry` detectors and the second was structurally wrong for every
`sorry`-bodied declaration, marking 33 of 33 chapter-1 declarations as proved.
"""

from pipeline.lean.axioms import AxiomReport, print_axioms
from pipeline.lean.build import BuildResult, Diagnostic, lake_build
from pipeline.lean.ilean import IleanIndex, LeanDeclaration, read_ilean

__all__ = [
    "AxiomReport", "BuildResult", "Diagnostic", "IleanIndex", "LeanDeclaration",
    "lake_build", "print_axioms", "read_ilean",
]
