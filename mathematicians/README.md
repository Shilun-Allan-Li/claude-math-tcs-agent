# mathematicians/

Knowledge layer for proof agents. The workflow layer — orchestrator, explorer, prover, reviewer, formatter — lives in `claude_prover/`. This tree holds what the agents *know* and *how they write*.

```
mathematicians/
  skills/      # fact library — snippets of math and TCS knowledge
  distill/     # style packs — how proofs are written in a tradition
  README.md
```

## skills/

Flat-markdown snippets (150–400 words each), organized as `skills/domains/<math|tcs>/<vertical>/<concept>.md`. Definitions, theorems, pitfalls, notation conventions — one concept per file. Agents grep the folder and `Read` the handful of snippets relevant to the current step. No frontmatter, no manifest; the folder is the index.

See `skills/skill-creator/SKILLS.md` for the authoring contract and verification checks.

## distill/

Style packs capturing proof and writing habits. Two kinds, picked by how much signal the source offers:

- **individuals/** — great mathematicians whose corpus is large and style canonical (Euler, Gauss, Euclid, Erdős, Grothendieck, …). The corpus is voluminous, the voice is well-documented, and person-level signal survives distillation. Here the *person* is the stable unit.
- **batches/** — modern research, where any single paper-author is too noisy. The stable unit is a batch of 5–15 peers in a domain slice; what they *share* is the domain's real proof habits.

Both kinds use the same template (`distill/mathematician-distillation-template.md`), since the sections describe a *style*, not a *who*. Only the "Source profile" differs: a person's collected works vs. a domain batch.

See `distill/readme.md` for authoring details.

## How agents use this

At the point of need, an agent picks one style pack from `distill/` and a handful of `skills/` snippets, reads them, and proceeds. The pack tells it *how* to write the proof; the snippets tell it *what* facts to use. Both reads are plain `Read`, not `Skill`-tool invocation.
