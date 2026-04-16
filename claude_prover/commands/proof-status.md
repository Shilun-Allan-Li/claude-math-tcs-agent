# /proof-status

Display the current state of the proof in progress: what's done, what's next, and any blockers.

## Instructions

No arguments needed. Read the current proof state and display a summary.

---

1. Check if `proof/OUTLINE.md` exists.
   - If not: "No proof in progress. Run `/prove [theorem]` to start one."

2. Read `proof/OUTLINE.md` to extract:
   - The theorem name
   - The proof strategy
   - All steps with their `[ ]` / `[x]` status

3. Scan for step files: glob `proof/step_*.md` to find which steps have files written.

4. Check for blocker flags: grep `proof/step_*.md` for `⚠️ BLOCKED` or `⚠️ STEP TOO LARGE`.

5. Check if `proof/assembled.md` exists.

6. Check if any review files exist: glob `proof/review_*.md`.

7. Display a formatted status report:

```
## Proof Status: [Theorem Name]

Strategy: [one-line strategy from OUTLINE.md]

### Progress
[x] Step 01: [description]        ← file exists
[x] Step 02: [description]        ← file exists
[ ] Step 03: [description]        ← NOT STARTED  ← NEXT STEP
[ ] Step 04: [description]
...

Completed: X / Y steps

### Blockers
⚠️  Step 03 is BLOCKED: [description from step file if found]

### Assembly
[assembled.md exists? Yes/No]

### Reviews
[List any review files and their verdicts if found]

### Suggested Next Action
Run `/proof-step 3` to work on the next incomplete step.
[OR: All steps done! Run `/prove --assemble` to assemble the proof.]
[OR: Step N is blocked. Run `/explore "..."` to investigate.]
```

$ARGUMENTS
