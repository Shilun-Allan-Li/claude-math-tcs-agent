# distill/

Multi-agent backend that reads raw mathematician corpora and produces distilled packs. Output flows to `phds/knowledge_db/`, never directly to `skills/`.

## Two kinds of pack

The right unit of distillation depends on how much signal the source offers. Two modes, same template family.

- **Individual pack** — for great mathematicians whose corpus is large and whose style is canonical (Euler, Gauss, Riemann, Erdős, Grothendieck, …). Captures the **heuristic mind**: what they notice first, what they reach for, when they abandon a route. The person *is* the stable unit.
- **Batch pack** — for modern research, where any single paper-author is too noisy. The stable unit is 5–15 active authors in the same domain slice (e.g. "additive combinatorics, 2015–2025"). Captures the **domain playbook** — what those authors *share*.

Why not one size fits all: a single modern paper-author gives too little signal to isolate personal style from domain convention; distillation picks up noise. A single ancient great gives enough — the corpus is huge and the voice is documented.

## Layout

```
distill/
  agents/          # multi-agent specs that drive distillation
                   #   arxiv-collector.md, github-curator.md, corpus-collector.md
                   #   orchestrator.md (runs the pipeline end-to-end)
  sources/         # raw corpus material, the input
    heuristic_mind/                # individual-pack sources, per mathematician
      euler/  gauss/  riemann/  grothendieck/  erdos/  ...
    batches/                       # batch-pack sources
      CATALOG.md                     # MSC + arXiv index of recognized verticals
      math/<vertical>/               # 12 verticals (linear-algebra, number-theory, …)
      tcs/<vertical>/                # 9 verticals (algorithms, complexity-theory, …)
  templates/       # shape contracts for distilled output
    individual-template.md       # heuristic-mind pack
    batch-template.md            # domain-playbook pack
  reference/       # methodology notes for the distillers
    extraction-framework.md
  README.md
```

## Pipeline position

```
sources/  →  agents/ (multi-agent run)  →  pack  →  phds/knowledge_db/
```

A finished pack is *not* a skill. It enters the knowledge DB and waits for a phd to decide whether any of it should be promoted into `skills/`.
