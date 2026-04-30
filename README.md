# claude-math-tcs-agent

A multi-agent system for writing rigorous mathematical and TCS proofs with Claude — without hitting token walls, without hallucinated citations, and without losing the thread on long arguments.

## What this does

Five proving agents work on a theorem together:

- **proof-orchestrator** — plans the proof, maintains the outline, assembles the final draft.
- **proof-explorer** — brainstorms strategies, tries small cases, looks for counterexamples.
- **proof-prover** — writes one numbered step at a time (~500 words each, 800 hard cap).
- **proof-reviewer** — audits completed steps and the assembled proof.
- **proof-formatter** — converts source PDFs / LaTeX archives into clean markdown.

They share state through a `proof/` directory (outline + step files + exploration notes + reviews) and dispatch the **engineer** subagent for computation, citation lookup, or PDF extraction.

## Why use it

- **Token limits.** No agent ever writes more than ~800 words; the proof is assembled from independent step files.
- **Hallucinated citations and arithmetic.** Computation and lookup go through the engineer.
- **Lost-thread errors.** The outline (`proof/OUTLINE.md`) and per-step files give the model durable scratchpad memory.

## Layout

```
claude_prover/             ← proof agent surface (agents, commands, lib)
engineers/                 ← compute helper (engineer subagent + /engineer)
distill_mathematicians/    ← skill production: arxiv + great-mathematician → distiller → skill-creator
skills/                    ← procedural patches the proof agents read at the point of need
proof/                     ← runtime: OUTLINE + step files + reviews + assembled proof
papers/                    ← runtime: formatted reference papers
.claude/                   ← live install (agents/commands are per-file symlinks)
wip/                       ← parked old backend (see wip/README.md)
```

## How skills are produced

`distill_mathematicians/` is the only path. One script collects sources (arxiv API + a small registry of historical mathematicians like Euler, Gauss, Riemann, Erdős, Grothendieck — all tagged with arxiv categories so one taxonomy covers both). Two agents process them: the **distiller** extracts operational heuristics from one source; the **skill-creator** turns one distilled file into at most one skill. A queue manager (`run.py`) tracks what's pending; `/distill` steps the pipeline forward.

```bash
python3 -m distill_mathematicians.lib.collect arxiv math.NA --n 10   # add sources
python3 -m distill_mathematicians.lib.collect great euler            # add Euler corpus
python3 -m distill_mathematicians.lib.run                            # see queue
/distill                                                             # step forward
```

## Quick start

```bash
# 1. Install the customer surface in your project
PROJECT=/path/to/your/project
mkdir -p $PROJECT/.claude/agents $PROJECT/.claude/commands $PROJECT/.claude/hooks
cp claude_prover/CLAUDE.md $PROJECT/.claude/CLAUDE.md
cp claude_prover/agents/*  $PROJECT/.claude/agents/
cp claude_prover/commands/* $PROJECT/.claude/commands/
cp engineers/agents/engineer.md $PROJECT/.claude/agents/
cp engineers/commands/engineer.md $PROJECT/.claude/commands/
cp .claude/hooks/step_index.py $PROJECT/.claude/hooks/

# 2. (Optional) Convert a reference paper
/format-paper papers/source/my_reference.pdf

# 3. Start a proof
/prove "Theorem (Bolzano–Weierstrass): Every bounded sequence in R^n has a convergent subsequence."

# 4. Inspect the outline, then work step by step
/proof-status
/proof-step 1
/proof-step 2

# 5. Stuck? Explore.
/explore "why the diagonal argument works in step 4"
/proof-step 4

# 6. When all steps are [x], assemble and review
/prove --assemble
/proof-step review
```

## Requirements

For PDF formatting: `pdftotext` (poppler-utils) or `pandoc`. For tar/zip: standard `tar` and `unzip`.

## License

See `LICENSE`.
