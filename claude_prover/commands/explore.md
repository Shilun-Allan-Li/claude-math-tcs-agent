# /explore

Explore proof strategies, investigate an obstacle, or try examples.

## Usage
- `/explore "<question>"` — general strategy exploration
- `/explore "step N is blocked at <description>"` — mid-proof blocker

## Instructions

Dispatch the `proof-explorer` agent:

> "Explore the following question and append findings to `proof/exploration.md`. If `proof/OUTLINE.md` exists, read it first for context. Question: <user's question>."

Print the explorer's recommended strategy / blocker resolution.

$ARGUMENTS
