# /proof-step

Work on a specific proof step, or review the assembled proof.

## Usage
- `/proof-step <N>` — work on step number N (e.g., `/proof-step 3`)
- `/proof-step review` — run the reviewer on the assembled proof
- `/proof-step review <N>` — run the reviewer on a specific step

## Instructions

Read the argument after this command to determine the step number or action.

---

**If a step number N is provided:**

1. First check `proof/OUTLINE.md` exists. If not, tell the user: "No proof outline found. Run `/prove [theorem]` first."

2. Check if `proof/step_NN.md` already exists (use zero-padded number, e.g., `step_03.md`).
   - If it exists: ask "Step N already has a file (`proof/step_NN.md`). Do you want to (a) redo it, (b) review it, or (c) skip to the next step?"

3. Check if all prerequisite steps (all steps before N) are marked `[x]` in OUTLINE.md.
   - If not: warn "Step N depends on earlier steps that are not yet complete: [list them]. It is recommended to complete those first, but you can proceed anyway."

4. Check `proof/exploration.md` — if it has content relevant to this step, mention it to the user before delegating.

5. Use the `proof-prover` agent to work on this step. Pass it:
   "Work on step [N] of the proof. The outline is in proof/OUTLINE.md. Complete this step and save it to proof/step_NN.md."

6. After the prover completes, update OUTLINE.md to mark step N as `[x]` if the prover didn't already do so.

7. Report back:
   ```
   Step N complete: [one-line summary from the step file]

   Progress: X/Y steps done
   Next: Run `/proof-step N+1` to continue.
   ```

---

**If the argument is `review`** (no step number):

Use the `proof-reviewer` agent. Pass it: "Review the assembled proof in proof/assembled.md end-to-end."

If `proof/assembled.md` does not exist, say: "No assembled proof found. Run `/prove --assemble` first, then review."

---

**If the argument is `review N`** (with step number):

Use the `proof-reviewer` agent. Pass it: "Review step [N] from proof/step_NN.md in the context of proof/OUTLINE.md."

$ARGUMENTS
