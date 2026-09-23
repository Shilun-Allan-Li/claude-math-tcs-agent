---
name: simplify
description: Simplify a selected Lean proof through library reuse and maintainable tactics while preserving its theorem statement and checking the result.
---

Read [working principles](../../guidance.md) and the [agent-loop protocol](../../docs/agent-loop.md).
Use its simplify mode, selecting exactly the existing proof term. The replacement proposal
is just `__MATH_TCS_PROOF__`; do not change imports, definitions, binders, or conclusions.
A separate reviewer confirms the selection; the proof worker proposes tactics and local helpers.
Prefer maintainability over fewer lines. Apply only after the harness's independent check.
If the original proof is already clear, leave it unchanged and explain why briefly.
