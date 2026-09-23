---
name: formalize
description: Formalize one mathematical statement or complete one Lean theorem in an existing project using a formalizer agent, independent semantic review, and checked proof attempts.
---

Read [working principles](../../guidance.md) and the [agent-loop protocol](../../docs/agent-loop.md).
Coordinate its formalize loop using the shared Python harness. This skill is the entry point;
the formalizer and proof worker do the mathematics, and a separate reviewer checks fidelity.
Work on one user-selected declaration at a time. Ask only when ambiguity affects meaning or
the requested edit range. Preserve unrelated edits and use `task apply` for canonical writes.
Default to four proof attempts and at most two statement repairs; report unresolved work.
