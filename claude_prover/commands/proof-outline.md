# /proof-outline

View, update, or regenerate the proof outline.

## Usage
- `/proof-outline` — display the current outline
- `/proof-outline update` — re-run the orchestrator to revise the plan
- `/proof-outline split <N>` — split step N into sub-steps
- `/proof-outline add <description>` — add a new step at the end

## Instructions

**No argument:** Read `proof/OUTLINE.md` and print it.

**`update` / `split N` / `add <desc>`:** Dispatch `proof-orchestrator` with the user's request. The orchestrator edits `proof/OUTLINE.md` in place and preserves `[x]` marks on completed steps.

$ARGUMENTS
