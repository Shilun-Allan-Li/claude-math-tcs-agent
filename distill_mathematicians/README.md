# distill_mathematicians

The single source of how skills are generated.

## Pipeline

```
collect.py   →   manifest.json   →   distiller   →   distilled/<area>/<vertical>/<id>.md   →   skill-creator   →   skills/...
   ↑                                     ↑                                                          ↑
   one script                            one agent                                                  one agent
   (arxiv API + great-mathematician      (routes via verticals.py                                   (arxiv → skills/<area>/<vertical>/...
    registry)                             from manifest tags)                                        great → skills/souls/<id>.md
                                                                                                     + config/soul.md entry)
```

Two skill kinds:

- **arxiv-derived** → `skills/<area>/<vertical>/<name>.md`, with a `Category: <area>-<vertical>` label inside the file. Loaded at the point of need by proving agents.
- **great-mathematician-derived** → `skills/souls/<source_id>.md` (a heuristic-mind fragment). Listed in `config/soul.md`; the user picks one "soul" at first login.

`run.py` is the queue manager — it reads `manifest.json` + `distilled/`, prints what's pending. The user steps the pipeline forward with `/distill`.

## Layout

```
distill_mathematicians/
  README.md
  manifest.json              ← the queue (gitignored)
  agents/
    distiller.md             ← reads one source → distilled/<id>.md
    skill-creator.md         ← reads one distilled file → at most one skill
  commands/
    distill.md               ← /distill — step the pipeline
  lib/
    collect.py               ← arxiv API + great-mathematician registry → manifest entries
    verticals.py             ← arxiv tag → (area, vertical-folder) routing table
    run.py                   ← queue manager
  sources/                   ← gitignored — local cache of fetched papers
    arxiv/
    great_mathematicians/
  distilled/                 ← gitignored — distiller outputs, sorted into <area>/<vertical>/
    math/<vertical>/<id>.md
    tcs/<vertical>/<id>.md
```

## Verticals

12 math (MSC primaries) + 9 TCS (arXiv cs.*). The full mapping lives in `lib/verticals.py`; `route(tags)` returns `(area, vertical)` for any source.

## Two source kinds, one taxonomy

Both modern arxiv papers and historical great-mathematician corpora are tagged with **arxiv categories** (`math.NT`, `cs.CC`, `math.HO`, etc.). One taxonomy, one queue, one distiller.

- **arxiv** — recent papers, pulled live from the arxiv API.
- **great** — canonical corpora of historical mathematicians (Euler, Gauss, Riemann, Erdős, Grothendieck). The registry in `collect.py` maps surname → list of canonical URLs + tags.

## Collecting

```bash
# Add 10 recent papers from numerical analysis to the manifest
python3 -m distill_mathematicians.lib.collect arxiv math.NA --n 10

# Add Euler's corpus to the manifest
python3 -m distill_mathematicians.lib.collect great euler

# See what's available
python3 -m distill_mathematicians.lib.collect list-categories
```

`collect.py` is idempotent on `(kind, id)` — re-running merges, doesn't duplicate.

## Stepping the pipeline

```bash
# See the queue
python3 -m distill_mathematicians.lib.run

# Step forward (in claude)
/distill              # auto-pick the next pending item
/distill 2401.12345   # distill this specific source
/distill skill euler-collected_works   # create a skill from this distilled file
```

## Adding a new great mathematician

Edit `REGISTRY` in `collect.py`. Each entry needs `title`, `url`, `kind_detail`, and `tags` (arxiv-style). No code changes elsewhere.

## Why this is so simple

The previous backend had collector agents, an extraction framework with three gates, an orchestrator, an extractor, an intake phase, a merge phase, a pack-write phase, and a regulator with a promotion log. None of it had ever produced a real pack.

This version is one script + two agents + one queue manager. If a skill turns out badly, you delete it. If you want a regulator, add it later.
