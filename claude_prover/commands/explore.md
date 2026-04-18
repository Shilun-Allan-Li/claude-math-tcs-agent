# /explore

Explore proof strategies, investigate an obstacle, or try examples.

## Usage
- `/explore "<question>"` — general strategy exploration
- `/explore "step N is blocked at <description>"` — mid-proof blocker

## Instructions

Read the user's question after this command.

1. Gather context:
   - If `proof/OUTLINE.md` exists: `python3 -m claude_prover.lib.cli outline` to show current plan.
   - If the user mentioned a step number N: resolve its file with `python3 -m claude_prover.lib.cli step-path <N>` and `Read` it.
   - If `proof/exploration.md` exists, the agent will append to it rather than overwrite.

2. Delegate to the `proof-explorer` agent. Pass it:

   > "Explore the following question and append findings to `proof/exploration.md`. Question: <question>. Context: <outline path, step path, or 'no proof in progress'>."

3. After the explorer returns, report:
   - recommended strategy / blocker resolution,
   - dead ends,
   - remaining open questions,
   - any ⚠️ counterexample found (flag prominently).

$ARGUMENTS
