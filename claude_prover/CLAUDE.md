# Math Proof Assistant System

This directory contains a coordinated multi-agent system for constructing rigorous mathematical proofs. It is designed to avoid the token-limit failure mode of trying to write an entire proof in one shot.

## Core Principle

Proofs are broken into small, manageable steps. Each step is worked on independently and saved to a file. An outline (TODO list) tracks the overall structure and completion status.

## Directory Layout (created at runtime)

```
proof/                 ← owned by orchestrator + prover + reviewer; reset by /prove --reset
  OUTLINE.md          ← Master TODO list with all proof steps
  step_01.md          ← Completed proof step 1
  step_02.md          ← Completed proof step 2
  ...
  exploration.md      ← Ideas, failed attempts, strategy notes (explorer-owned)
  assembled.md        ← Final assembled proof (when complete)
  review_step_NN.md   ← Reviewer output per step (reviewer-owned)
  review_assembled.md ← Reviewer output for assembled proof
  archive/<ts>/       ← Snapshots from /prove --reset and intern reconciliation
  .intern_inbox/      ← Hook→intern message bus (orphans.json, reconciliation reports)
papers/                ← Owned by formatter (writes) and prover/explorer (read-only)
  <name>.md           ← Formatted versions of source papers
```

`/prove --reset` archives the entire `proof/` contents (OUTLINE, every step, exploration.md, every review_*.md, assembled.md) into `proof/archive/<timestamp>/`. `papers/` is not reset — formatted papers persist across proofs.

## Available Agents

| Agent | Purpose |
|---|---|
| `proof-orchestrator` | Plans the proof, manages OUTLINE.md, assembles final proof |
| `proof-prover` | Works on a single proof step, saves result to step_N.md |
| `proof-explorer` | Explores proof strategies, logs ideas, tries examples |
| `proof-formatter` | Converts PDF / .tar LaTeX archives into agent-readable markdown |
| `proof-reviewer` | Reviews a completed step or assembled proof for correctness |

## Available Commands

| Command | Usage |
|---|---|
| `/prove` | Start a new proof — provide the theorem statement |
| `/proof-step` | Work on a specific step number from the outline |
| `/explore` | Brainstorm strategies for a theorem or stuck point |
| `/format-paper` | Convert a PDF or .tar LaTeX archive to readable markdown |
| `/proof-status` | Display current proof progress and TODO list |
| `/proof-outline` | Update or regenerate the proof outline |

## Workflow

1. `/prove "Theorem: ..."` — orchestrator reads the theorem, creates `proof/OUTLINE.md` with numbered steps
2. Inspect `proof/OUTLINE.md` to see the plan
3. `/proof-step 1` — prover agent works only on step 1, writes `proof/step_01.md`
4. `/proof-step 2` — work on step 2 (can reference step 1's result), writes `proof/step_02.md`
5. Continue until all steps marked `[x]` in OUTLINE.md
6. Run `/prove --assemble` — orchestrator reads all step files and writes `proof/assembled.md`
7. `/proof-step review` — reviewer checks the assembled proof

If stuck at any step: `/explore "why X implies Y"` — explorer logs strategies to `proof/exploration.md`

## Subagent dispatch

All inter-agent calls in this system go through the **Task tool**. The orchestrator dispatches the prover, explorer, reviewer, formatter, and the intern via Task. The prover and explorer dispatch the engineer (`engineers/agents/engineer.md`) via Task for any computation, search, or extraction. Slash commands like `/proof-step` and `/engineer` are user-facing entry points; agent-to-agent dispatch is always Task.

## Review-result loop

When a reviewer turn produces `proof/review_step_NN.md` or `proof/review_assembled.md` with verdict `NEEDS REVISION` or `FAIL`, the orchestrator surfaces the issue and **asks the user** before re-dispatching the prover. The user always has the final call on whether to re-prove. See `agents/proof-orchestrator.md` § "Review-result loop" for the protocol.

## Token-Budget Discipline

- **No agent writes more than ~800 words of proof in a single response.** If a step is too large, it should be split into sub-steps by updating OUTLINE.md.
- Each agent reads only the files it needs — not the entire proof history.
- The orchestrator never writes the proof itself; it only plans and assembles.
