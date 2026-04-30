# skills/

Procedural patches the proving-agents read at the point of need.

## What a skill is

A skill is a **procedural patch for a specific failure mode of token-prediction on math.**

The proving-agents are LLMs — probabilistic next-token predictors, not human mathematicians. Skills don't restate facts (those are already in weights). Skills install *procedure* the predictor doesn't apply on its own.

Design center:

> **Take the model's actual computation pattern as given. Identify a failure mode. Write a procedure that compensates for it.**

## The seven failure modes

Every skill should map to at least one:

1. **Computation offload** — when to dispatch the engineer instead of computing in-token (arithmetic, large case enumeration, citation lookup).
2. **External memory discipline** — how to use `OUTLINE.md`, step files, exploration notes (name invariants, refer by name, don't re-derive).
3. **Route-selection overrides** — overriding the most-frequent-pattern default (e.g., "for symmetric matrices, try spectral structure before coordinate computation").
4. **Hypothesis-check rituals** — pause points before invoking a theorem (restate hypotheses, verify each).
5. **Anti-hallucination scaffolds** — "if a citation is needed, dispatch web-search; don't improvise."
6. **Search-tree pruning** — breadth checks before committing to depth-first ("list two alternatives and pop-conditions").
7. **Compression / decompression discipline** — when to cite-by-name vs. expand into explicit quantifiers.

A skill that doesn't map to any of these is not a skill in this system.

## What belongs vs. doesn't

- **Belongs:** style guides for compact proof prose, technique patterns ("invariant-first for algorithm proofs"), attack heuristics ("for monotone problems, try extremal first").
- **Doesn't:** definitions, theorem statements, glossary entries. Claude already has those. Skills add procedure, not knowledge.

## Layout

```
skills/
  styles/         # written-style patches
    concise_math_style.md
  techniques/     # technique patches (route-selection)
  attacks/        # first-move heuristics
```

Categories grow when a real skill lands in them. Empty folders aren't pre-scaffolded.

## Authoring

A new skill is one markdown file. Name it after the task pattern. Body: imperative rules. Frontmatter optional. Each skill should:

- name at least one consumer agent (`prover`, `explorer`, `reviewer`, `formatter`),
- declare which failure-mode bucket(s) it patches,
- contain no second-person ("you / your") prose,
- be tight — one task pattern per skill.
