# researchers/

Bridge department between `distill/` and `claude_prover/`. One team, flat structure. The phds receive distilled packs from `distill/`, **sort and curate** them, and generate the procedural skills the proving-agents use.

## What lives in `knowledge_db/`

Curated, sorted, **useful distilled material** — nothing else. No textbook restatements (Claude already has those facts in weights). No raw dumps. A pack reaches `knowledge_db/` only when the phds judge it actually moves Claude's performance.

```
phds/knowledge_db/
  individuals/        # heuristic-mind packs (per-mathematician)
  batches/            # domain-playbook packs (per-domain-slice)
```

The phds sort material as it arrives — by topic, by source, by whatever cut serves the prover. **Topic taxonomy is not pre-scaffolded**; it emerges from real packs.

## Roles

Two responsibilities, same department.

- **Organizer** (`skill-creator/`) — sorts the knowledge_db, then authors the procedural skills (style packs, technique patterns, attack heuristics) that proving-agents follow.
- **Regulator** (`skill-regulator/`) — gates promotion. A pack stays in the knowledge_db until the regulator clears a derived skill for `skills/`. If no proving-agent will use it, no skill ships — the pack still lives in `knowledge_db/` as reference material the phds keep.

## Layout

```
phds/
  knowledge_db/         # curated distilled material, sorted by phds
    individuals/
    batches/
  skill-creator/        # organizer role
  skill-regulator/      # regulator role
  README.md
```

## Pipeline position

```
distill/  →  knowledge_db/ (sorted by phds)  →  skill-creator  →  skill-regulator  →  skills/
                  │                                                                     │
                  └────────────── proving-agents read on demand ───────────────────────┘
                                                                                        │
                                                              proving-agents follow ────┘
```

The knowledge_db is the persistent memory of curation work. Skills are the operational surface — derived, gated, scoped tightly to what the prover actually uses.
