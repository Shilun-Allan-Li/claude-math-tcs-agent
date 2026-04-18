# /proof-step

Work on a specific proof step, or review one.

## Usage
- `/proof-step <N>` — work on step N (e.g., `/proof-step 3`)
- `/proof-step review` — review the assembled proof
- `/proof-step review <N>` — review a specific step

## Instructions

Read the argument after this command.

---

**Argument is a step number `N`:**

1. Preflight — this checks the outline exists, step N is in it, and flags unmet prerequisites:

   ```
   python3 -m claude_prover.lib.cli step-preflight <N>
   ```

   If it exits non-zero, print the message and stop. If it prints `WARN:` lines, surface them to the user before proceeding.

2. Resolve the target path:

   ```
   python3 -m claude_prover.lib.cli step-path <N>
   ```

3. If `proof/exploration.md` exists, `Read` it and mention any content relevant to step N before delegating.

4. Delegate to the `proof-prover` agent. Pass it:

   > "Work on step N of the proof. Read `proof/OUTLINE.md` for context and the path from step-path above. Save your step to that file."

5. After the prover returns, mark the step done:

   ```
   python3 -m claude_prover.lib.cli mark-done <N>
   ```

6. Print the new status:

   ```
   python3 -m claude_prover.lib.cli status
   ```

---

**Argument is `review` (no number):**

If `proof/assembled.md` does not exist, say: "No assembled proof found. Run `/prove --assemble` first." Otherwise delegate to `proof-reviewer`:

> "Review the assembled proof in `proof/assembled.md` end-to-end. Save your verdict to `proof/review_assembled.md`."

---

**Argument is `review N`:**

Delegate to `proof-reviewer`:

> "Review step N from `proof/step_NN.md` in the context of `proof/OUTLINE.md`. Save your verdict to `proof/review_stepNN.md`."

$ARGUMENTS
