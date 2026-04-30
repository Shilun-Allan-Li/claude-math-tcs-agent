# engineers

Compute helper for the proof-prover and proof-explorer.

The engineer is a thin Sonnet subagent that runs one bounded computation per call (python, web search, PDF extract) and returns a short report. The prover and explorer dispatch it via the Task tool when a step needs verification or a citation lookup.

## Layout

```
engineers/
  agents/engineer.md     ← agent spec
  commands/engineer.md   ← /engineer slash command
```

Scratch files go in `engineering/` at the repo root (gitignored).

## When to use

- A claim depends on numerical or symbolic verification.
- A citation needs to be looked up (web search) instead of recalled.
- A reference paper needs to be extracted from PDF/LaTeX.

If the computation is one line, the prover may run it inline via Bash instead of dispatching.
