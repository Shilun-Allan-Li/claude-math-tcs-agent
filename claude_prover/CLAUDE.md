# Math Proof Assistant System

Multi-agent system for constructing rigorous mathematical proofs. Splits each proof into small numbered steps so no single response hits the token wall.

## Directory layout (created at runtime)

```
proof/
  OUTLINE.md          ← master TODO list with all proof steps
  step_NN.md          ← one file per step (zero-padded)
  exploration.md      ← strategy notes, dead ends, examples
  assembled.md        ← final assembled proof (after /prove --assemble)
  review_step_NN.md   ← reviewer output per step
  review_assembled.md ← reviewer output for assembled proof
  archive/<ts>/       ← snapshot from /prove --reset
papers/
  <name>.md           ← formatted reference papers
```

`/prove --reset` archives the entire `proof/` contents into `proof/archive/<ts>/`. `papers/` is not reset.

## Agents

| Agent | Purpose |
|---|---|
| `proof-orchestrator` | Plans the proof, manages OUTLINE.md, assembles final proof |
| `proof-prover` | Writes one step at a time, saves to `proof/step_NN.md` |
| `proof-explorer` | Brainstorms strategies, tries examples, logs to `proof/exploration.md` |
| `proof-formatter` | Converts PDF / .tar LaTeX archives into agent-readable markdown |
| `proof-reviewer` | Reviews a completed step or assembled proof |
| `engineer` | Runs python / web search / PDF extract on demand |

## Commands

| Command | Usage |
|---|---|
| `/prove` | Start a proof, or `--assemble` / `--reset` |
| `/proof-step N` | Work on step N (or `review` / `review N`) |
| `/explore` | Brainstorm strategies |
| `/format-paper` | Convert a paper to markdown |
| `/proof-status` | Show progress |
| `/proof-outline` | View / update the outline |
| `/engineer` | Dispatch a small computation |

## Workflow

1. `/prove "Theorem: ..."` — explorer brainstorms, orchestrator writes `proof/OUTLINE.md`.
2. `/proof-step 1` — prover writes `proof/step_01.md`. Repeat for each step.
3. `/explore "..."` if stuck.
4. `/prove --assemble` — orchestrator concatenates step files into `proof/assembled.md`.
5. `/proof-step review` — reviewer audits the assembled proof.

## Subagent dispatch

Inter-agent calls go through the **Task tool**. The orchestrator dispatches prover / explorer / reviewer / formatter via Task. The prover and explorer dispatch the engineer via Task for computation.

## Token budget

- No agent writes more than ~800 words of proof in a single response. If a step is too large, split it via `/proof-outline split N`.
- Each agent reads only the files it needs.
- The orchestrator never writes proof content — it only structures and assembles.
