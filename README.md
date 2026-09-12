# claude-math-tcs-agent

A local Claude Code plugin marketplace (`math-tcs-local`) with one plugin:

- [`plugins/math-tcs`](plugins/math-tcs/README.md) — translate → scaffold → verify → prove mathematics/TCS sources into Lean 4, with a scripted workflow coordinator behind `/math-tcs:run`.

Requirements and the exact install / activation / update commands are in the plugin README.
`IMPLEMENTATION_PLAN.md` is the approved plan with its status; `pipeline_kickoff_plan.md` is the requirements source.

```bash
make validate      # claude plugin validate --strict (plugin + marketplace)
make test          # unit tests (no Lean)
make test-lean     # Lean-backed tests against $TARGET (default: ~/Desktop/projects/research/tcslib)
make dev           # claude --plugin-dir … inside the target
make install       # persistent: marketplace add + plugin install (user scope)
```
