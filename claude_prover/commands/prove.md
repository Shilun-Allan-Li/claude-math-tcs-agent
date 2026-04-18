# /prove

Start or manage a mathematical proof.

## Usage
- `/prove "<theorem>"` — start a new proof
- `/prove --assemble` — assemble completed steps into `proof/assembled.md`
- `/prove --reset` — archive current proof and start fresh

## Instructions

Read the argument after this command. It is either `--assemble`, `--reset`, or a theorem statement.

---

**Theorem statement (or no flag):**

1. Check whether a proof is already in progress:

   ```
   python3 -m claude_prover.lib.cli status
   ```

   If the output is **not** `No proof in progress.`, ask the user whether to (a) continue, (b) archive and start fresh (`--reset`), or (c) cancel.

2. If starting fresh:
   - Delegate to the `proof-explorer` agent first: "Explore proof strategies for the theorem below. Append findings to `proof/exploration.md`. Theorem: <theorem>."
   - Then delegate to the `proof-orchestrator` agent: "Plan the proof of the theorem below using the exploration findings in `proof/exploration.md`. Decompose into steps no larger than ~500 words each. When the plan is ready, write it by calling:

     `python3 -m claude_prover.lib.cli outline-init <title> <strategy> <desc1> <desc2> ...`

     Then print the new outline. Theorem: <theorem>."

3. Print the outline and next-step suggestion:

   ```
   python3 -m claude_prover.lib.cli outline
   python3 -m claude_prover.lib.cli status
   ```

---

**`--assemble`:**

```
python3 -m claude_prover.lib.cli assemble
```

Print the returned path. If assembly fails (e.g. missing step files), surface the error. Optionally delegate to `proof-orchestrator` to polish transitions between steps — the mechanical concatenation is already done.

---

**`--reset`:**

```
python3 -m claude_prover.lib.cli archive
```

It prints the archive directory (e.g. `proof/archive/20260417-134016`). Confirm: "Previous proof archived to <dest>. Run `/prove "<theorem>"` to start a new one."

$ARGUMENTS
