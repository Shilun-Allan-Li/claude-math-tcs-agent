# /proof-outline

View, update, or regenerate the proof outline.

## Usage
- `/proof-outline` — display the current outline
- `/proof-outline update` — re-run the orchestrator to revise the plan
- `/proof-outline split <N>` — split step N into sub-steps
- `/proof-outline add <description>` — add a new step at the end

## Instructions

Read the argument (if any).

---

**No argument or `view`:**

```
python3 -m claude_prover.lib.cli outline
```

Print the output verbatim.

---

**`update`:**

Use the `proof-orchestrator` agent. Pass it:

> "The proof outline needs revision. Read `proof/OUTLINE.md` and any step files flagged with ⚠️ BLOCKED or ⚠️ STEP TOO LARGE (get the list with `python3 -m claude_prover.lib.cli list-blockers`). Revise the outline in place — split oversized steps, add missing ones — and preserve the `[x]` marks on completed steps."

---

**`split N`:**

Use the `proof-orchestrator` agent. Pass it:

> "Split step N in `proof/OUTLINE.md` into smaller sub-steps. Each should fit in ~500 words. If `proof/step_NN.md` exists, read it for context. Renumber as appropriate."

---

**`add <description>`:**

Use the `proof-orchestrator` agent. Pass it:

> "Add a new step to `proof/OUTLINE.md` with this description: `<description>`. Assign the next available step number."

---

After any update, display the revised outline with `python3 -m claude_prover.lib.cli outline`.

$ARGUMENTS
