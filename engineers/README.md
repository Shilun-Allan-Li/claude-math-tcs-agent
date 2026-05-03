# engineers

Compute helper for the proof-prover and proof-explorer.

The engineer is a thin Sonnet subagent that runs one bounded computation per call and returns a short report. The prover and explorer dispatch it via the Task tool when a step needs verification or a citation lookup.

## Layout

```
engineers/
  agents/engineer.md     ← agent spec
  lib/cli.py             ← compute primitives (run-test, sympy, search)
```

Scratch files and run logs go in `engineering/` at the repo root (gitignored). Logs land in `engineering/runs/<utc-ts>_<verb>_<name>.log`.

## Compute primitives

All run in a subprocess with a wall-clock timeout (default 30 s) and save the full log:

```
python3 -m engineers.lib.cli run-test <file.py> [--timeout S]
python3 -m engineers.lib.cli sympy "<expression>" [--timeout S]
python3 -m engineers.lib.cli search <pred.py> --range a..b
        [--mode counterexample|witness] [--timeout S]
```

`pred.py` for `search` must define `predicate(n) -> bool`. `sympy` runs the expression with `from sympy import *` in scope (sympy must be installed for the python on PATH).

The verb axis is *kind of computation*, not which prover stage called it — the same `run-test` is reachable from `/prove`, `/explore`, or `/proof-step`.

## When to dispatch

- A claim depends on numerical or symbolic verification → `run-test` or `sympy`.
- A conjecture should be checked against small cases → `search`.
- A citation needs to be looked up → web search.
- A reference paper needs to be extracted from PDF/LaTeX → `pdftotext` / `tar`.

If the computation is one line, the prover may run it inline via Bash instead of dispatching.
