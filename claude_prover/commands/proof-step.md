# /proof-step

Work on a specific proof step, or review one.

## Usage
- `/proof-step <N>` — work on step N
- `/proof-step review` — review the assembled proof
- `/proof-step review <N>` — review a specific step

## Instructions

**Argument is a step number `N`:** Dispatch the `proof-prover` agent:

> "Work on step N. Read `proof/OUTLINE.md` for context, read prior `proof/step_*.md` files as needed, and write your step to `proof/step_NN.md` (zero-padded)."

The `step_index.py` hook will tick OUTLINE.md after the step file is written.

**Argument is `review`:** If `proof/assembled.md` is missing, say so and stop. Otherwise dispatch `proof-reviewer`:

> "Review `proof/assembled.md` end-to-end. Save your verdict to `proof/review_assembled.md`."

**Argument is `review N`:** Dispatch `proof-reviewer`:

> "Review `proof/step_NN.md` in the context of `proof/OUTLINE.md`. Save your verdict to `proof/review_stepNN.md`."

$ARGUMENTS
