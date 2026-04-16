# /explore

Explore proof strategies, investigate a specific obstacle, or try examples for a mathematical question.

## Usage
- `/explore "<question or theorem>"` — general strategy exploration before starting a proof
- `/explore "why does <claim> hold"` — investigate a specific claim
- `/explore "counterexample to <statement>"` — search for a counterexample
- `/explore "step N is blocked at <description>"` — investigate a mid-proof blocker

## Instructions

Read the user's message following this command invocation. It contains the question or obstacle to explore.

---

Use the `proof-explorer` agent to explore the question. Pass it the user's full question plus any relevant context:

1. If `proof/OUTLINE.md` exists, mention it so the agent knows the overall proof context.
2. If `proof/exploration.md` exists, tell the agent to append to it (not overwrite).
3. If the user mentioned a step number, tell the agent to read that step file.

Pass the agent:
"Explore the following question and append your findings to proof/exploration.md. Question: [user's question]. [Context: current proof outline exists at proof/OUTLINE.md / we are working on step N / etc.]"

---

After the explorer completes, report:
1. The recommended strategy or resolution (extracted from exploration.md).
2. Any dead ends identified (so the user knows not to retry them).
3. Any remaining open questions.
4. If a counterexample was found: flag it prominently with ⚠️ and suggest reconsidering the theorem statement.

$ARGUMENTS
