---
name: prove
description: math-tcs stage 4 — prove verified declarations one at a time on a scratch copy with a bounded attempt budget, then promote only proofs whose `#print axioms` contain no sorryAx and only allowlisted axioms. Use for "/math-tcs:prove <lean-file | id | slug>".
argument-hint: <lean-file-or-id-or-slug> [--ids a,b] [--budget N] [--force]
allowed-tools: Read, Write, Glob, Grep, Agent, Bash(python3 *mathtcs.py*), Bash(date *)
---

Args: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" args prove $ARGUMENTS`
Project: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" project detect`
Now: !`date -u +%Y-%m-%dT%H:%M:%SZ`
Plugin root: !`echo "${CLAUDE_PLUGIN_ROOT}"`

You are the **prove coordinator**. The `math-tcs:proof-worker` agent works only in `math-tcs/scratch/<id>/work.lean`; `mathtcs.py promote` re-checks the result against the current canonical module and writes it only when the main declaration is `FULLY_VERIFIED`. Each declaration has one writer at a time (a lock). `MT` = `python3 "<Plugin root>/scripts/mathtcs.py"`; `NOW` = the timestamp above.

## Input contract

`Args.target` is an id, slug, or module path; `--ids` narrows; `--budget N` overrides `config.prove.budget`; `--force` also takes declarations whose verify action is not `prove`/`reuse`. If `Args.errors` is non-empty print them with `/math-tcs:prove <lean-file | id | slug> [--ids a,b] [--budget N] [--force]` and stop.

## Steps

1. **Eligibility.** Resolve ids as in verify. Eligible = status ∈ {`verified`, `unfinished`, `failed`} and `verify.action` ∈ {`prove`, `reuse`} (or `--force`), not `proved`, and `MT manifest stale <id>` reports no `statement_changed`/`verify_stale`. Report every ineligible id with its reason (`skipped`).
2. For **each** eligible declaration, in order (definitions and dependencies first):
   a. `MT manifest lock <id> --stage prove --at NOW` — if refused, skip with the lock info.
   b. `MT scratch prepare <id>` → `work`; `MT context prove <id>` → `context path`.
   c. Launch `math-tcs:proof-worker` with `context`, `work`, `check` = `MT check --file <work> --tag prove/<id> --brief`, `budget`, and the axiom allowlist from the config. Ask for its result JSON.
   d. Write the result JSON with Write to `math-tcs/reports/<id>/prove-result.json`, then `MT report prove <id> --result math-tcs/reports/<id>/prove-result.json --at NOW`.
   e. If `result == "proved"`: `MT promote <id> --attempt <work> --at NOW`. Promotion may still refuse (trust not `FULLY_VERIFIED`, statement changed, non-allowlisted axiom); record what it says.
   f. **Always** `MT manifest unlock <id>` — also after any failure in b–e.
3. **Report.** Table `id | result | promoted | trust | axioms | helpers (proved/unproved) | attempts`, the paths of the prove reports and, for `statement_change_required`, the `statement-change-rev<N>.md` file to review. Re-verification is needed for those ids.

## Failure behaviour

Never promote a proof with `sorryAx` or with an axiom outside the allowlist; never let the worker edit the canonical file; a worker returning nothing is `missing` (recorded, lock released). A proof relying on an unproved helper stays `unfinished`.
