# /prove

Start or manage a mathematical proof.

## Usage
- `/prove "<theorem>"` — start a new proof
- `/prove --assemble` — assemble completed steps into `proof/assembled.md`
- `/prove --reset` — archive current proof and start fresh

## Instructions

Read the argument after this command.

**Theorem statement (or no flag):**

1. If `proof/OUTLINE.md` exists, ask the user whether to (a) continue, (b) `--reset`, or (c) cancel.
2. Dispatch the `proof-explorer` agent to brainstorm strategies and append findings to `proof/exploration.md`.
3. Dispatch the `proof-orchestrator` agent to write `proof/OUTLINE.md` based on the exploration.
4. Print the new outline.

**`--assemble`:** Dispatch `proof-orchestrator` to read every `proof/step_NN.md` in order and write `proof/assembled.md`.

**`--reset`:** Run `python3 -m claude_prover.lib.cli archive`. Print the archive directory.

$ARGUMENTS
