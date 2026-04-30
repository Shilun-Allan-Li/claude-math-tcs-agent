# wip/

Work-in-progress backend for skill production. Not active.

## Why this is parked

The system was designed with a full distillation pipeline (`distill_mathematicians/` → `phds/knowledge_db/` → skill-creator → skill-regulator → `skills/`) before any pack had been distilled or any skill had been generated. The infrastructure outweighed the input — 0 packs, 0 generated skills, 1 hand-authored style skill.

Parking until a real pack exists. When you have one, lift the bare minimum from here back into active layout — don't restore the whole apparatus.

## Contents

- `distill_mathematicians/` — collector agents (arxiv, github, corpus), extractor, orchestrator, and a 1500-line lib for arXiv API + Semantic Scholar + GitHub search + canonical-source registry. The 600-line `reference/extraction-framework.md` is a methodology doc.
- `phds/` — skill-creator + skill-regulator specs, knowledge_db skeleton.

## Restore protocol

When the first real pack is ready:

1. Don't move the whole tree back. Pick the one collector you actually need and copy it into a fresh `distill_mathematicians/` at the root.
2. Keep `phds/skill-creator/` minimal — a pack-to-skill conversion is a one-shot per pack, not a full subagent + draft/rejected/promoted log.
3. The capability-multiplier test in `wip/phds/skill-creator/skill-creator.md` is the only useful artifact from the whole tree. Inline it as a checklist in `skills/README.md`.
