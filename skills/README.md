# skills/

**The product of this whole repo.** Every other tier — `distill_mathematicians/`, `phds/`, the engineer, the intern — exists to feed accurate, well-targeted skills into this directory. The proving-agents in `claude_prover/` do their work by reading what lives here at the point of need.

## What a skill is, in this system

A skill is a **procedural patch for a specific failure mode of transformer-style next-token computation on math.**

The proving-agents are large language models. Under the hood, an LLM is a probabilistic next-token predictor — close to a Bayesian-ish learner over text, very different from how a human mathematician thinks. We are not trying to redefine that machinery; we are trying to add the right *external procedure* on top of it so it solves real proofs reliably.

This is the design center for everything in `skills/`:

> **Take the model's actual computation pattern as given. Identify a failure mode. Author a procedural skill that compensates for it.**

Not: "what would a human mathematician learn here?" The model is not a human; copying human pedagogy is the wrong map. The right question is what *this kind of learner* — given how it actually computes — needs added.

## The transformer-failure-mode taxonomy

Every skill in this repo should map to at least one of these. If a draft skill doesn't, the regulator rejects it.

1. **Computation offload.** Arithmetic, large case enumeration, symbolic manipulation, citation lookup — all unreliable from a token-predictor. Skills tell the prover *when* to dispatch the engineer (calculator/web-search/index-source), not how to compute by itself. The engineer is the calculator; skills install the discipline of using it.

2. **External memory / scratchpad discipline.** Transformers lack durable state across long outputs. The system already gives them external memory (`proof/OUTLINE.md`, `step_NN.md`, `exploration.md`); skills enforce *how to use it* — "name the invariant in step 1, refer to it by name in later steps; do not re-derive."

3. **Route-selection overrides.** Pattern-matching defaults to *most frequent* route in training data, not *most appropriate* for this problem. Skills override the default: "for symmetric matrices, try spectral structure before coordinate computation, even though coordinate computation is more common in textbooks."

4. **Hypothesis-check rituals.** Transformers fluently produce locally-plausible, globally-wrong sentences. Skills install pause points: "before invoking theorem X, restate its hypotheses; verify each one." The point is not that the model "doesn't know" the hypotheses — it's that fluency outpaces verification unless verification is structurally enforced.

5. **Anti-hallucination scaffolds.** "If a citation is needed, dispatch engineer `web-search`; do not improvise the citation." "If a numerical bound is needed, dispatch `run-python`; do not write the digits from memory."

6. **Search-tree pruning prompts.** Transformers go depth-first along the highest-likelihood branch. Skills install breadth checks: "before committing to a route, list two alternatives and the pop-condition for each."

7. **Compression / decompression discipline.** When to compress a multi-step argument into a named theorem cite; when to *expand* a casually-worded step into explicit quantifiers. The default is uneven; skills make the choice deterministic.

A skill is not a fact, a definition, or a textbook restatement. The model already has those in weights. **Skills add procedure, not knowledge.**

## What belongs here vs. in `phds/knowledge_db/`

- `skills/` — procedural patches the agent **follows** at runtime: style packs, technique patterns, attack heuristics, dispatch rituals. Operational, imperative, narrowly scoped.
- `phds/knowledge_db/` — curated distilled material the agent **reads on demand**: heuristic-mind packs, domain playbooks. The phds' working memory.

A style guide for terse proof prose belongs here. A definition of LU decomposition belongs nowhere — Claude already knows. Don't author fact snippets.

## Layout

```
skills/
  styles/         # written-style patches (concise prose, theorem-cite discipline, …)
    concise_math_style.md
  techniques/     # technique patches (route-selection overrides, decomposition rituals)
  attacks/        # first-move heuristics tied to recognizable problem features
  README.md
```

Categories grow as the phds promote skills into them. Empty categories are not pre-scaffolded — a folder appears the first time a skill is promoted into it.

## How a skill gets here

Authored by `phds/skill-creator/`, gated by `phds/skill-regulator/`. The regulator's promotion gates and the source-citation contract (`Source:` line referencing a `phds/knowledge_db/` pack) are the entry rules.

A skill that has no traceable source pack is flagged for human review. A skill that doesn't map to a transformer-failure-mode in the taxonomy above is rejected — not revised.
