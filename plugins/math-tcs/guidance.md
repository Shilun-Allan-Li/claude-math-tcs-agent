# Lean working principles

For Lean formalization work, understand the informal statement and surrounding definitions
before selecting a representation. Preserve quantifiers, assumptions, domains, and conclusion.
Search the project's library and Mathlib before introducing definitions or proving duplicates.
Prefer direct reuse, then suitable automation, then useful local helper lemmas.
Optimize for faithful, maintainable proofs rather than line count.

Use the formalize, review, or simplify skill for its corresponding task. Keep formalization,
semantic review, and proof construction as distinct roles. A semantic review is model judgment,
never a kernel proof or human approval. Ask about ambiguity that changes the mathematics.

Check claimed completed declarations with Lean and inspect transitive axiom dependencies.
Missing tools, failed checks, and unresolved obligations must be stated explicitly.
Do not change project toolchains or dependencies without a separate request.
These principles apply to Lean tasks only and do not launch workers automatically.
