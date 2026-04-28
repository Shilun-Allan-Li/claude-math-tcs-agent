# claude-math-tcs-agent

A multi-agent system for writing rigorous mathematical and TCS proofs with Claude — without hitting token walls, without hallucinated citations, and without losing the thread on long arguments. The customer surface is `claude_prover/`. The rest of the repo is a backend that produces the *skills* those agents read.

## What this does

Five proving agents work on a theorem together:

- **proof-orchestrator** plans the proof, maintains an outline, assembles the final draft, and drives the review loop.
- **proof-explorer** brainstorms strategies, tries small cases, looks for counterexamples.
- **proof-prover** writes one numbered step at a time (~500 words each, hard cap at 800).
- **proof-reviewer** audits completed steps and the assembled proof.
- **proof-formatter** converts source PDFs / LaTeX archives into clean markdown the other agents can read.

They share state through a `proof/` directory (outline + step files + exploration notes + reviews) and delegate any computation, citation lookup, or PDF extraction to a separate **engineer** subagent that runs sandboxed code and returns audited reports. A small **intern** subagent keeps the `proof/` tree clean when outlines change.

## Why use it

A single-prompt proof bumps into the token wall and produces fluent-but-broken math. Splitting the work across focused subagents — each with a small input scope, a small output budget, and external memory — solves three failure modes at once:

- **Token limits.** No one agent ever writes more than ~800 words; the proof is assembled from independent step files.
- **Hallucinated citations and arithmetic.** Computation, citation lookup, and source extraction are routed to the engineer subagent, which logs every byte to an audit dir.
- **Lost-thread errors on long proofs.** The outline (`OUTLINE.md`) and per-step files give the model durable scratchpad memory; review is a separate pass with its own reading discipline.

The proving-agents themselves are general-purpose Claude. What makes them good at math is the **skills** they read at the point of need — procedural patches authored by the backend in this repo.

## How the backend works

The backend exists for one reason: to produce accurate, well-targeted skills. Information flows in one direction:

```
distill_mathematicians/  ──▶  phds/knowledge_db/  ──▶  skills/  ──▶  claude_prover/
        (extract)             (sort + curate)        (author + gate)    (read on demand)
                                     │                                          ▲
                                     └─── claude_prover also reads ─────────────┘
                                          knowledge_db on demand
```

- **`distill_mathematicians/`** — multi-agent backend. Reads raw mathematician corpora (collected works of Euler/Gauss/Riemann/Erdős/Grothendieck; arXiv papers and curated GitHub repos by domain vertical) and produces distilled packs. Two pack types: *individual packs* capturing a great mathematician's heuristic mind, *batch packs* capturing a domain's current playbook.
- **`phds/knowledge_db/`** — curated, sorted, useful distilled material. No textbook restatements (Claude already has those). Every pack here has earned its slot.
- **`phds/skill-creator/` + `phds/skill-regulator/`** — bridge department. Authors skills from packs; gates them against a two-check test (behavior delta + transformer-failure-mode mapping). Drafts that pass land in `skills/`; drafts that fail are rejected with rationale.
- **`skills/`** — the product. Procedural patches the proving-agents read at the point of need. Categorized as `styles/`, `techniques/`, `attacks/`. **Skills add procedure, not knowledge** — see `skills/README.md` for the design center.
- **`engineers/`** — request-response compute service. Runs Python/C++/MATLAB, web search, PDF/source indexing, token counting. Sandboxed; every call audited.
- **`interns/`** — file housekeeping. Hooks + a Haiku subagent reconcile the `proof/` tree when the user edits the outline.

## How to use it (quick start)

```bash
# 1. Install the customer surface in your project (see claude_prover/README.md for full install)
PROJECT=/path/to/your/project
cp claude_prover/CLAUDE.md $PROJECT/.claude/CLAUDE.md
cp claude_prover/agents/*  $PROJECT/.claude/agents/
cp claude_prover/commands/* $PROJECT/.claude/commands/
# (also copy engineer + intern + hooks for the full system)

cd $PROJECT && claude .

# 2. Optional — convert a reference paper
/format-paper papers/source/my_reference.pdf

# 3. Start a proof
/prove "Theorem (Bolzano–Weierstrass): Every bounded sequence in R^n has a convergent subsequence."

# 4. Inspect the outline, then work step by step
/proof-status
/proof-step 1
/proof-step 2
…

# 5. Stuck? Explore.
/explore "why the diagonal argument works in step 4"
/proof-step 4   # retry with exploration notes available

# 6. When all steps are [x], assemble and review
/prove --assemble
/proof-step review
```

## How to use it (backend / building skills)

If you want to extend the skill library:

```bash
# 1. Run a distillation job (writes a pack to phds/knowledge_db/)
#    — individual mode for a great mathematician
#    — batch mode for a domain slice (e.g., "additive combinatorics, 2015–2025")
#    See distill_mathematicians/agents/orchestrator.md for the job spec.

# 2. The phds skill-creator drafts a skill from the pack
#    drafts/<skill-name>.md
#    See phds/skill-creator/skill-creator.md.

# 3. The phds skill-regulator gates the draft
#    PROMOTE → moves to skills/<category>/
#    REVISE  → returns with rationale
#    REJECT  → moves to phds/skill-creator/rejected/
#    See phds/skill-regulator/skill-regulator.md.

# Skills are read by the proving-agents on demand. No registry — each
# skill's frontmatter description is its trigger summary, and agents
# discover skills by listing the relevant skills/<category>/ folder.
```

## Tier map

| Tier | Owner | Read by | Reset by |
|---|---|---|---|
| `claude_prover/` | end users | — | re-install |
| `proof/`, `papers/` (runtime) | the proving-agents | the proving-agents | `/prove --reset` (proof/), persistent (papers/) |
| `engineering/artifacts/` (runtime) | engineer | engineer | gitignored, never committed |
| `skills/` | phds/skill-creator + skill-regulator | proving-agents | manual (regulator audit) |
| `phds/knowledge_db/` | phds | proving-agents (on demand), skill-creator | accumulates across distillation runs |
| `distill_mathematicians/` | distillation backend | phds | per-run dirs in `runs/` |

Each tier has its own README with the contract.

## Project status

Design phase complete. The customer-surface specs (`claude_prover/`), the backend specs (`distill_mathematicians/`, `phds/`), the engineer service (specs + Python harness), and the intern (specs + hooks) are all in place. The Python CLI scaffolding for `/prove`, `/proof-step`, etc. (`claude_prover/lib/`) is the next coding milestone; the agent specs above describe the contract that scaffolding must satisfy.

## License

See `LICENSE`.
