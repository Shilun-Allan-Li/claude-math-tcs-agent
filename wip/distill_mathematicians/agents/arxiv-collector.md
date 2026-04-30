---
name: arxiv-collector
description: Builds a YAML manifest of arXiv papers for batch-pack distillation, given a discipline + vertical + time window. Manifest-only; intake (the actual download) is the orchestrator's job. Dispatched by the distill-orchestrator via the Task tool.
model: claude-sonnet-4-5
tools:
  - Read
  - Write
  - Bash
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

The arXiv API query, citation enrichment, survey detection, scoring, ranking, and YAML emission are all done by the regulated-search CLI in `distill_mathematicians/lib/arxiv.py`. The agent's role is to invoke it with the right arguments, validate the output, and decide what to do if the CLI under-delivers.

1. Confirm `<discipline>` is `math` or `tcs` and `<vertical>` is one of the slugs in `distill_mathematicians/sources/batches/CATALOG.md`. The same vertical list is hard-coded in `lib/arxiv.py`'s `MATH_VERTICAL_CATEGORIES` / `TCS_VERTICAL_CATEGORIES`; if the CLI rejects the vertical, abort and surface the diagnostic.
2. Invoke the CLI via Bash:

   ```bash
   python -m distill_mathematicians.lib.cli arxiv \
       --discipline <discipline> --vertical <vertical> \
       --window <window> --target <target_count> --bias <bias> \
       --output distill_mathematicians/sources/batches/<discipline>/<vertical>/<window>/_manifest.yaml \
       --verbose
   ```

   The CLI handles arXiv API pagination (3-second rate limit), Semantic Scholar batch citation lookup (`S2_API_KEY` honored if set), survey detection via title/abstract/comment heuristics, the quality bar (`citation_count >= 20 OR is_survey`), and the 30% survey cap. These were previously failure-prone instructions to the agent; they are now guarantees in code.
3. Read the produced manifest. Verify the YAML matches the schema above and the `sources:` count is plausible relative to `target_count`.
4. If the CLI under-delivers (fewer than `target_count` entries), that is the anti-padding policy working as intended — see "Failure modes" below. Decide:
   - **Accept** and report the partial slate to the orchestrator (the spec endorses this).
   - **Re-run** with broadened inputs (a wider window, an adjacent vertical) only if you have reason to believe the field genuinely has more in-window signal. Do not relax the quality bar.
5. Return the manifest path and a one-line summary (entries selected, surveys vs. research split, under-delivery if any) to the orchestrator.

The active-practitioner condition (author has ≥3 in-window papers in this category) is **not** implemented in the CLI v1 because it would cost an extra round-trip per author. The two implemented conditions cover the common case; if the orchestrator needs that signal, it should request it explicitly so the CLI can be extended.

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
