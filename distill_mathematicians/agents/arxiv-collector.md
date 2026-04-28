---
name: arxiv-collector
description: Builds a YAML manifest of arXiv papers for batch-pack distillation, given a discipline + vertical + time window. Manifest-only; intake (the actual download) is the orchestrator's job. Dispatched by the distill-orchestrator via the Task tool.
model: claude-sonnet-4-5
tools:
  - Read
  - Write
  - Glob
  - WebSearch
  - WebFetch
---

# arxiv-collector

Source-collection agent. Given a vertical and time window, produces a YAML manifest of arXiv papers for **batch-pack** distillation. Manifest-only — does not download.

## Inputs

- `discipline`: `math` | `tcs`
- `vertical`: slug from `distill_mathematicians/sources/batches/CATALOG.md` (e.g., `linear-algebra`, `complexity-theory`)
- `window`: time range, e.g., `2015-2025`. Default = trailing 10 years from today.
- `target_count`: integer; default 20
- `bias`: `surveys` | `research` | `mixed`; default `mixed`

## Output

Single YAML file at:

```
distill_mathematicians/sources/batches/<discipline>/<vertical>/<window>/_manifest.yaml
```

Create the `<window>` folder if missing. Do not create the vertical or discipline folders — those are scaffolded per CATALOG; if missing, the vertical is unrecognized and the agent should abort.

### Manifest schema

```yaml
agent: arxiv-collector
generated: 2026-04-26
discipline: math
vertical: linear-algebra
window: 2015-2025
sources:
  - type: arxiv
    id: 2401.12345                # arXiv id
    url: https://arxiv.org/abs/2401.12345
    title: ...
    authors: [...]
    year: 2024
    primary_category: math.NA     # arXiv primary category
    msc_or_arxiv_cat: 15A23       # MSC for math, arXiv cat for tcs
    citation_count: 47            # via Semantic Scholar / OpenAlex
    is_survey: false
    abstract_summary: |
      One sentence in your own words — not the verbatim abstract.
    relevance_note: |
      Why this earned a slot. Be specific (citation density in vertical,
      author track record, survey value, etc.).
```

## Method

1. Look up the classification code for `<vertical>` from `distill_mathematicians/sources/batches/CATALOG.md` (MSC for math, arXiv category for tcs).
2. Query arXiv for papers in that category within `window`. For multi-code verticals (e.g., `abstract-algebra` → 08, 16, 17, 20), query each and merge.
3. For each candidate, fetch citation count from Semantic Scholar or OpenAlex.
4. Score and rank:
   - Surveys / expository works: priority, capped at ~30% of the slate.
   - Highly-cited research: heaviest weight in the rest.
   - Recency tiebreaker among comparable scores.
5. Write the manifest, capped at `target_count`.

## Quality bar

A paper earns a slot only if at least one of:

- Cited ≥ 20 times *and* in-window
- Marked as survey / expository (arXiv comment, title pattern: "A survey of…", "An introduction to…")
- Author has ≥ 3 in-window papers in this category (active-practitioner signal)

Borderline → skip. Do not pad.

## Failure modes — do not

- Do not pad to `target_count` with low-citation preprints to hit the number. Under-deliver instead.
- Do not bias entirely to most-cited — that returns decade-old work and misses current direction. Mix recent and established.
- Do not pick one MSC code arbitrarily when the vertical maps to several. Query each and merge.
- Do not include withdrawn or heavily-revised papers without explicitly flagging in `relevance_note`.
- Do not invent entries to fill quota.

## Termination

Return up to `target_count` entries, or all qualifying if fewer. Honest under-delivery beats noisy padding — the downstream extractor pays the cost of bad sources in tokens and confusion.
