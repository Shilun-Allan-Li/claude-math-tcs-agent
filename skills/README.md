# skills/

**Capability multipliers** for the proving-agents in `claude_prover/`. Same department as those agents — content here exists only to be read by them.

A skill activates Claude's existing ability for a specific task pattern. It doesn't supply knowledge — Claude already has the math/TCS facts from training. A skill supplies *procedure*: the heuristic, the attack order, the writing shape.

## What belongs here vs. in `phds/knowledge_db/`

- `skills/` — procedural packs the agent **follows** at runtime: style packs, technique patterns, attack heuristics. Operational.
- `phds/knowledge_db/` — curated distilled material the agent **reads on demand**: heuristic-mind packs, domain playbooks. The phds' working memory.

A style guide for terse proof prose belongs here. A definition of LU decomposition belongs nowhere — Claude already knows. Don't author fact snippets.

## Layout

```
skills/
  styles/         # written-style packs
    concise_math_style.md
  README.md
```

Expect new sub-folders (e.g. `techniques/`, `attacks/`) as procedural patterns get authored.

## Authoring

Skills are authored by `phds/skill-creator/` and gated by `phds/skill-regulator/`. The format and verification rules live with those roles.
