# distill/

Style packs that tell an agent how to write proofs in a given tradition. Each pack captures proof and writing habits — what theorems land first, what gets cited vs. rederived, what hypotheses get checked silently, how compression is done without losing rigor.

## Two kinds of pack

The right unit of distillation depends on how much signal the source offers. Two modes, same template.

### individuals/

For **great mathematicians whose corpus is large and whose style is canonical** — Euler, Gauss, Euclid, Cauchy, Riemann, Noether, Erdős, Grothendieck, … The corpus is voluminous, the voice has been studied for decades, and person-level signal survives distillation. The person *is* the stable unit.

### batches/

For **modern research**, where any single paper-author is too noisy — one paper, co-authored, scoped to a sub-sub-domain, shaped by current fashion. The stable unit is a batch of 5–15 active authors in the same domain slice; what they *share* is the domain's real proof habits. Use this for "additive combinatorics, 2015–2025", "spectral graph theory, last decade", and so on.

**Why not one size fits all.** A single modern paper-author gives too little signal to isolate personal style from domain convention and advisor habits — distillation picks up noise. A single ancient great gives *enough* signal — the corpus is huge, the voice is documented, and the personal style is what is worth copying in the first place.

## File layout

```
distill/
  individuals/
    euler.md
    gauss.md
    erdos.md
    ...
  batches/
    additive-combinatorics.md
    spectral-graph-theory.md
    ...
  individual-template.md                   # template for individual packs (heuristic mind)
  batch-template.md                        # template for batch packs (domain playbook)
  concise_math_style.md                    # hand-authored, shape-compatible
  readme.md                                # this file
```

One pack per file. Kebab-case filename — surname for individuals, domain slug for batches. No frontmatter, no manifest; `grep -r "<keyword>" distill/` finds every pack that addresses it.

## Authoring a new pack

**Individual pack:**

1. Pick a mathematician whose style is sharply identified, not just "someone good." Check there is enough primary material — collected works, extended correspondence, several books or long papers.
2. Read a representative cross-section of the primary material, looking for *recurring* habits, not isolated brilliance.
3. Fill the sections of `individual-template.md` — lead with heuristic content (first moves, reframings, characteristic tools), not written-style patterns.
4. The pack passes when a reader blind to the name can recognize the voice from the pack alone.

**Batch pack:**

1. Fix the domain and a time window (e.g. "algorithmic graph theory, 2015–2025").
2. Pick 5–15 active authors in that slice. Prefer breadth over depth; the batch exists to wash out idiosyncrasy.
3. Read 3–5 papers per author, looking for patterns *across* authors, not within any one.
4. Fill the sections of `batch-template.md` — lead with the decision table and attack stack. If a section has no stable signal across the batch, delete rather than invent.
5. The pack passes when a reader blind to the source batch can still tell what the domain values.

## Usage

Agents read one style pack plus a handful of `skills/` snippets at the point of need — via `Read`, no Skill-tool invocation. The pack tells the agent *how* to write proofs in the tradition; the snippets tell it *what* facts to use.
