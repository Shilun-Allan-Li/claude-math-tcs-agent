# /proof-status

Display the current state of the proof in progress.

## Instructions

Shell out to the CLI — it does all the deterministic work:

```
python3 -m claude_prover.lib.cli status
```

Run from the repo root (the module path resolves relative to `PYTHONPATH=.`). Print the CLI output verbatim; do not re-narrate.

If the CLI prints `No proof in progress.`, stop there — no agent invocation is needed.

$ARGUMENTS
