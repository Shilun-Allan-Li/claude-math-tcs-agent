"""The four checkers, and the orchestrator that fans out over them.

1. **Lean integrity** — deterministic; the kernel's answer, never a model's (rule 5).
2. **Source fidelity** — does the Lean say what the source says?
3. **Library context** — does this declaration need to exist, in this form?
4. **Semantic sanity** — is it vacuous or false in a degenerate case?

Each of 2-4 is a hybrid: a deterministic pre-pass for what a program can decide exactly,
then a model for the judgement that remains.
"""

from pipeline.checkers.hybrid import (
    check_library_context,
    check_semantic_sanity,
    check_source_fidelity,
)
from pipeline.checkers.lean_integrity import check_lean_integrity
from pipeline.checkers.orchestrator import CheckReport, run_checkers

__all__ = ["run_checkers", "CheckReport", "check_lean_integrity",
           "check_source_fidelity", "check_library_context", "check_semantic_sanity"]
