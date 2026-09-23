---
name: review
description: Review a Lean declaration or diff for mathematical fidelity, maintainability, and proof trust without modifying source files.
---

Read [working principles](../../guidance.md) and the Review only section of the
[agent-loop protocol](../../docs/agent-loop.md). Read the supplied informal source and
the changed declarations with their definitions. Delegate semantic review independently;
use `check-file` for compiler and axiom evidence. For a diff, inspect all affected declarations
and report anything that could not be checked. Keep model findings separate from formal
evidence. Without source, do not claim source fidelity. Do not edit Lean files or start a task.
