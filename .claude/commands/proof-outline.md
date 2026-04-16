# /proof-outline

View, update, or regenerate the proof outline.

## Usage
- `/proof-outline` — display the current outline
- `/proof-outline update` — re-run the orchestrator to revise the plan (e.g., after a blocker is resolved or a step is found to need splitting)
- `/proof-outline split <N>` — split step N into sub-steps (e.g., when the prover flagged it as too large)
- `/proof-outline add <description>` — add a new step at the end (e.g., for a missing case discovered during proof)

## Instructions

Read the argument after this command (if any).

---

**If no argument or `view`:**

Read and display `proof/OUTLINE.md` in full. If it doesn't exist, say: "No proof outline found. Run `/prove [theorem]` to create one."

---

**If argument is `update`:**

Use the `proof-orchestrator` agent. Pass it:
"The proof outline needs revision. Read proof/OUTLINE.md and all existing step files in proof/. Check for any ⚠️ BLOCKED or ⚠️ STEP TOO LARGE flags in the step files. Revise the outline to address these issues — split oversized steps, add missing steps, or restructure as needed. Update proof/OUTLINE.md in place, preserving [x] marks for completed steps."

---

**If argument is `split N`:**

Use the `proof-orchestrator` agent. Pass it:
"Split step [N] in proof/OUTLINE.md into two or more smaller sub-steps. Each sub-step should be completable in ~500 words. Read proof/step_NN.md if it exists to understand what was attempted. Create new step numbers (e.g., step Na, Nb or renumber as appropriate). Update proof/OUTLINE.md accordingly."

---

**If argument is `add <description>`:**

Use the `proof-orchestrator` agent. Pass it:
"Add a new step to proof/OUTLINE.md at the end (or at the most logical position) with the description: [description]. Assign it the next available step number. Update proof/OUTLINE.md."

---

After any update, display the revised outline.

$ARGUMENTS
