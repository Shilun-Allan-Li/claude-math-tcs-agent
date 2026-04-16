# /prove

Start or manage a mathematical proof.

## Usage
- `/prove` — start a new proof interactively
- `/prove --assemble` — assemble completed steps into `proof/assembled.md`
- `/prove --reset` — archive current proof and start fresh

## Instructions

Read the user's message following this command invocation carefully. It may contain a theorem statement, or it may be `--assemble` or `--reset`.

---

**If the user provides a theorem statement** (or no flag is given):

Use the `proof-orchestrator` agent to:

1. Check if `proof/OUTLINE.md` already exists. If it does, ask the user: "A proof is already in progress (see proof/OUTLINE.md). Do you want to (a) continue it, (b) start a new proof and archive the old one, or (c) reset?"

2. If starting fresh:
   - Create the `proof/` directory if needed
   - Run the `proof-explorer` agent first with the theorem statement to identify the best proof strategy. Pass it: "Explore proof strategies for the following theorem before the orchestrator plans the proof: [theorem]"
   - Then run the `proof-orchestrator` agent to create `proof/OUTLINE.md` based on the exploration findings.

3. After the outline is created, display:
   ```
   Proof plan created. Here's the outline:
   [print OUTLINE.md]

   Run `/proof-step 1` to begin the proof.
   Run `/explore "[question]"` if you want to investigate any part further first.
   ```

---

**If the flag is `--assemble`**:

Use the `proof-orchestrator` agent to assemble the proof. Pass it: "Assemble the proof by reading all completed step files and writing proof/assembled.md."

Then report what was assembled.

---

**If the flag is `--reset`**:

1. Archive the current proof: `mkdir -p proof/archive && mv proof/OUTLINE.md proof/step_*.md proof/exploration.md proof/review_*.md proof/assembled.md proof/archive/ 2>/dev/null`
2. Confirm: "Previous proof archived to `proof/archive/`. Ready for a new proof. Run `/prove [theorem]`."

$ARGUMENTS
