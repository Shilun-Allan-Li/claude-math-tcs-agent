---
name: verify
description: math-tcs stage 3 — elaborate a scaffolded declaration with Lean, then run the semantic reviewer and the reuse reviewer concurrently on the same frozen revision and combine them into one report with a recommended action (reuse | prove | repair_statement | defer). Use for "/math-tcs:verify <lean-file | id | slug>".
argument-hint: <lean-file-or-id-or-slug> [--ids a,b]
allowed-tools: Read, Write, Glob, Grep, Agent, Bash(python3 *mathtcs.py*), Bash(date *)
---

Args: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" args verify $ARGUMENTS`
Project: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" project detect`
Now: !`date -u +%Y-%m-%dT%H:%M:%SZ`
Plugin root: !`echo "${CLAUDE_PLUGIN_ROOT}"`

You are the **verify coordinator**. Elaboration is a formal check done by `mathtcs.py snapshot`; the two reviewers are model reviews; the combined report keeps the three apart and records that no human has approved anything. `MT` = `python3 "<Plugin root>/scripts/mathtcs.py"`; `NOW` = the timestamp above.

## Input contract

`Args.target` is a declaration id, a slug, or a Lean module path (relative to the project). `Args.flags.ids` narrows the set. If `Args.errors` is non-empty print them with `/math-tcs:verify <lean-file | id | slug> [--ids a,b]` and stop.

## Steps

1. **Resolve ids.** id → itself; slug → `MT manifest list --slug <slug>`; module path → `MT manifest list --module <module name>` (the module name is `<module_prefix>.<file stem>`). Keep entries whose status is `scaffolded`, `verified`, `needs_statement_review`, `deferred`, `unfinished` or `failed`; report `blocked`/`translated` ones as skipped with the reason.
2. For **each** declaration:
   a. `MT snapshot <id> --at NOW` → `dir`, `context`, `statement_sha256`, `elaboration`. If it returns `skipped` (existing representation), record that and continue.
   b. **Launch both reviewers in one message** (two Agent calls in the same turn): `math-tcs:semantic-reviewer` and `math-tcs:reuse-reviewer`, each given `context` = the absolute `context.json` path and told to review exactly that revision and echo its `statement_sha256`; the reuse reviewer also gets `probe` = `MT probe check <Name…> --imports <M,N>` and `MT probe tactic --file <module path> --id <id> --tactic "exact?"`.
   c. Write each reviewer's JSON with Write to `<dir>/semantic.json` and `<dir>/reuse.json`. If a reviewer returned nothing usable, do not write its file (the combiner records it as `missing`); relaunch that reviewer once first.
   d. `MT report combine <id> --rev <rev> --at NOW`.
3. **Report.** Table `id | elaboration (ok/trust) | semantic (verdict) | reuse (verdict) | action | status`, each report's `verify.md` path, and the sentence: "Reviews are model reviews; `human_approval` stays `none` until `MT manifest approve <id> --by <name>` is run by a person; only the elaboration column is a formal check." End with `Next: /math-tcs:prove <slug>` for actions `prove`/`reuse`, and the `repair_statement`/`defer` ids that need attention.

## Failure behaviour

Reviewers get no Write/Edit tools; if one modifies nothing and returns nothing it is `missing`. A revision mismatch (a reviewer echoing another sha) is recorded and the action falls back to `defer`. Elaboration timeouts are recorded as `repair_statement` evidence. The canonical module is never modified here.
