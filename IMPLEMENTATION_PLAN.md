# Implementation plan — math-tcs

> Superseded for everyday use by the formalizer → semantic reviewer → proof-worker task
> loop in `plugins/math-tcs/docs/agent-loop.md`. The historical batch plan below remains
> experimental. Current implementation and validation limits are recorded in
> `plugins/math-tcs/docs/everyday.md` and `plugins/math-tcs/docs/validation.md`.

> Approved plan (2026-09-13). Requirements source: `pipeline_kickoff_plan.md`.
> Status checklist is maintained at the top; the plan body below is the approved text.

## Status

- [x] 0. This file written
- [x] 1. Phase 0 spike — skeleton plugin, runtime unknowns recorded in `plugins/math-tcs/docs/phase0-findings.md`
- [x] 2. Deterministic scripts (`plugins/math-tcs/scripts/mathtcs/*`) + tests
- [x] 3. Agents + stage skills (translate, scaffold, verify, prove)
- [x] 4. Scripted coordinator `plugins/math-tcs/workflows/run.js` + static tests
- [ ] 5. One complete demonstrated run on the demo source in tcslib (recorded in README + `examples/demo/expected/run-demo.json`)
- [ ] 6. Packaging: README, Makefile, `claude plugin validate --strict`, persistent install + update walkthrough

---

## Context

`pipeline_kickoff_plan.md` asks for an installable Claude Code plugin `math-tcs` (stages **translate → scaffold → verify → prove**, plus `run --until`). The revised direction: put the orchestration behind `/math-tcs:run` into a **Claude Code dynamic workflow** — a script that owns stage ordering, parallel worker execution, context selection, bounded retries, and result collection — while LLM agents do translation, formalization, semantic review, and proof construction, and deterministic helper scripts do Lean verification, file handling, and manifest bookkeeping. Existing pieces are reused: the four stage skills and five agents from the previous plan (same definitions serve both the manual skills and the workflow), the artifact contracts (annotated Markdown IR, manifest, verify/prove reports), and the session's own authentication (no API keys). Verification rules are preserved unchanged; every failed or missing result is recorded explicitly.

**Installed runtime (checked):** Claude Code 2.1.269 exposes the `Workflow` tool. Scripts are plain JS with `export const meta = {name, description, phases}` (pure literal), body hooks `agent(prompt, {label, phase, schema, model, effort, agentType, isolation})`, `pipeline(items, ...stages)` (no barrier), `parallel(thunks)` (barrier), `phase()`, `log()`, `args`, `budget`, `workflow()` (one nesting level), `resumeFromRunId` caching. **No filesystem, no Node APIs, no `Date.now()`** — deterministic steps must be executed by an agent with Bash; `schema` forces validated structured output; `agentType` resolves custom subagents from the same registry as the Agent tool; a skipped/dead agent returns `null`. Concurrency cap min(16, CPUs−2). Invocation is by `scriptPath` (any path on disk) + `args`; each run shows a permission dialog and the user has explicitly opted into workflow orchestration for `/math-tcs:run`.

**Other verified facts:** target project = `~/Desktop/projects/research/tcslib` (Lean v4.25.0, `lakefile.lean`, lib `TCSlib`, Mathlib built; ships its own `.claude/agents/lean-*` — no name collisions); artifacts live in `math-tcs/` at the target root; `lake env lean --json <file>` emits one JSON message per line (`severity` ∈ error|warning|information, `kind: "hasSorry"` for sorry warnings, `#print axioms` arrives as an `information` message — the transitive-sorry case reports `[sorryAx]` with no textual sorry); `lake lean <file>` also exists (builds project imports first); Python 3.14 (`tomllib` in stdlib) → scripts stdlib-only. Old engine code to port lives at `b753236:src/pipeline/{lean/build.py, lean/axioms.py, lean/names.py, stages/scaffold.py, stages/prove.py, checkers/lean_integrity.py, corpus/ids.py, stages/source_items.py}` and prompts at `b753236:prompts/*` (glass's copies are byte-identical).

---

## Architecture

```
/math-tcs:run <source> [--until S]   (SKILL.md: parse args via script, stamp time, call Workflow tool)
        │
        ▼  Workflow({scriptPath: ${CLAUDE_PLUGIN_ROOT}/workflows/run.js, args:{…}})
   run.js — scripted coordinator (JS, deterministic control flow)
   ├─ phase Translate : runner(source extract) → translator agent → runner(validate, ≤2 fix rounds) → runner(register)
   ├─ phase Scaffold  : runner(context scaffold) → scaffolder agent → runner(scaffold apply) → ≤2 repair rounds on elaboration errors
   ├─ phase Verify    : pipeline(decls): runner(snapshot) → parallel[semantic-reviewer ‖ reuse-reviewer] → runner(save + combine)
   ├─ phase Prove     : batches of K: runner(lock) → prover agent → runner(promote | record) → runner(unlock)   [promotions serialized]
   └─ phase Collect   : runner(run record) → return summary {per-id per-stage status ∈ ok|failed|missing|skipped}
        │
        ├─ LLM agents   (agentType): formal-translator, lean-scaffolder, semantic-reviewer, reuse-reviewer, proof-worker
        ├─ tool-runner  (agentType, tools: Bash+Write, haiku, ≤3 turns): runs one `mathtcs.py …` command, returns its JSON
        └─ scripts      python3 ${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py <cmd>  (only writer of manifest/Lean/reports)
```

- **Coordinator in code:** `run.js` decides stage order, `--until` cut-off, what context each agent gets (paths produced by `mathtcs.py context`), retry bounds (constants), parallelism (`args.parallel` provers; two reviewers per declaration; all declarations pipelined), and collects results. No stage decision is left to prose.
- **Deterministic work through agent tools:** because the workflow runtime cannot exec, every script call goes through `runner(cmd)` = `agent("Run exactly this command … return stdout JSON", {agentType: 'tool-runner', schema: RUNNER_RESULT, effort: 'low'})`. A runner result with `exit ≠ 0` is a recorded failure, never a throw that loses the run.
- **Stage skills stay usable on their own** (`/math-tcs:translate|scaffold|verify|prove`) and follow the same scripts/agents — the workflow is the scripted `run` on top, not a replacement.

## Repository layout (this repo = local marketplace + plugin)

```
.claude-plugin/marketplace.json                 name: math-tcs-local; plugins: [{name: math-tcs, source: ./plugins/math-tcs, version}]
IMPLEMENTATION_PLAN.md                          this plan (step 0)
plugins/math-tcs/
  .claude-plugin/plugin.json                    name math-tcs, version 0.1.0
  workflows/run.js                              the scripted coordinator (+ schemas.js content inlined — one file, no imports)
  skills/{translate,scaffold,verify,prove,run}/SKILL.md
  agents/{formal-translator,lean-scaffolder,semantic-reviewer,reuse-reviewer,proof-worker,tool-runner}.md
  scripts/mathtcs.py                            single CLI dispatcher (stdlib only)
  scripts/mathtcs/{args,project,config,ids,source_items,annotated_md,manifest,context,lean_json,lean_check,axioms,probe,blocks,scaffold,promote,report,runs}.py
  templates/{annotated.md,block.lean,module-header.lean,verify.md}
  examples/demo/source/01_unit-1-divisibility.md          (port of b753236 demo source)
  examples/demo/expected/{annotated.md,proposals.json,Divisibility.lean,verify-*.json,run-demo.json}
  tests/{test_args,test_ids,test_source_items,test_annotated_md,test_blocks,test_manifest,test_report,test_lean_json,test_runjs_static}.py  tests/lean/{test_check,test_e2e_scripts}.py
  docs/phase0-findings.md                       answers to the unknowns below
  README.md                                     install/activate/update/usage + the demonstrated run
Makefile                                        validate / test / dev / install / update
```

Target-project artifacts (paths from `math-tcs/config.json`):
`math-tcs/{config.json, manifest.json, .gitignore}`, `math-tcs/sources/<slug>-<sha8>.md` (inline excerpts), `math-tcs/annotated/<slug>-ch<N>.md`, `math-tcs/context/<stage>/<id>.json`, `math-tcs/reports/<id>/rev<N>/{statement.lean,context.json,elaboration.json,semantic.json,reuse.json,verify.json,verify.md}`, `math-tcs/reports/<id>/prove-rev<N>-<k>.json`, `math-tcs/scratch/<id>/attempt-<n>.lean` (gitignored), `math-tcs/locks/<id>.json`, `math-tcs/runs/<startedAt>.json`, and the Lean module `<src_dir>/<ModulePrefix as path>/<Slug>.lean` (tcslib: `TCSlib/MathTcs/Divisibility.lean`).

## Contracts (unchanged rules, refined shapes)

**IDs** (`ids.py`, port of `b753236:src/pipeline/corpus/ids.py`): `<slug>-ch<C>-<kindcode>-<label|section-ordinal>`, `KIND_CODE = def|thm|lem|cor|prop|ex|exm|con|not|rem`, `normalize_label`, `content_fingerprint`; helpers `<lean_name>.aux_<n>`. Slug/chapter precedence: `--slug/--chapter` > config > filename (`^(\d+)[_-]`, `ch(\d+)`) > first H1 `(Unit|Chapter|Lecture|Section)\s+N` > first numbered label > `"0"`; persisted in config so IDs never drift.

**Annotated Markdown IR** (`annotated/v1`): YAML front matter (`slug, chapter, title, source{path,sha256}, conventions[{quote,meaning}], open_questions[]`), then one `## <id>` section per item containing a ```` ```yaml math-tcs ```` block (`id|TBD, kind, label, section, page, source_lines, name, statement_nl, hypotheses[], conclusion, variables[{name,type,from}], definitions_used[{term,id}], depends_on[{ref,id,role}], has_source_proof, mathlib_candidates[{name,status}], difficulty{estimate,reason}, questions[{text,blocks_formalization}]`), `### Source statement (verbatim)` blockquote, `### Source proof (verbatim)` blockquote or exactly `_No proof in source._`, `### Interpretation (agent)` prose. Validator: verbatim quotes must locate in the source (whitespace-normalised), `TBD` ids get `section+ordinal` in source order, no tactic tokens in yaml fields, `has_source_proof` consistent.

**Config** (`math-tcs/config.json`): `lean{lib, src_dir, module_prefix, namespace, check: "lake lean", timeout_s: 600, register_in_root, root_file}`, `axioms{allow: [propext, Classical.choice, Quot.sound]}` (`sorryAx` rejected even if listed), `prove{budget: 4, max_helpers: 3, parallel: 1}`, `ids{slug}`, `paths{…}`. `project detect` parses `lakefile.toml` (tomllib) or `lakefile.lean` (regex `lean_lib «X»` + optional `srcDir`); lib name and module prefix are separate fields (glass: lib `GlassFixtures`, flat modules; tcslib: prefix `TCSlib`, `srcDir "."`, hand-maintained `TCSlib.lean` root).

**Manifest** (`manifest/v1`, atomic tmp+rename): per id `{kind, label, slug, chapter, source{path,sha256,section,page,lines,excerpt_sha256}, annotated{path,rev,section_sha256}, lean{representation: new|existing, path, module, name, rev, statement_sha256, block_sha256, existing_name, owner}, status ∈ translated|scaffolded|blocked|scaffold_failed|verified|needs_statement_review|proved|unfinished|failed|deferred, trust{status, axioms, checked_rev}, verify{rev, report, action}, prove{attempts, budget, last_report}, helpers[{name,trust}], blockers[], human_edited, human_approval{status,by,rev,at}, lock, history[]}`. `statement_sha256` = signature only (`split_statement` at bracket depth 0) so proof edits don't bump `rev`; a signature change bumps `lean.rev` and invalidates verify/prove. `manifest stale` reports `source_changed | annotation_changed | block_changed(human_edited) | statement_changed`. Proved or human-edited blocks are never rewritten without `--force` (the proposal is written to `reports/<id>/proposed-rev<N>.lean` instead). Locks: `math-tcs/locks/<id>.json {stage, started_at, ttl_min}`; `lock` exits 1 on a live lock.

**Lean block format:** line-comment markers `-- math-tcs:begin id=<id> rev=<n>` … `-- math-tcs:end id=<id>` placed *before* modifiers and the doc comment (whitespace to Lean's parser); one `namespace` per file from config; no file-level `variable` lines (blocks self-contained); generated doc comment carries kind/label, id, source ref + verbatim statement, verbatim proof or `_No proof in source._`, `Difficulty (estimate): <level> — <reason>`; ported `split_modifiers`, `strip_doc_comment`, `replace_proof`; `classify_body` rejects tactic bodies at scaffold; definitions may map to an existing declaration (`representation: existing`) instead of a block; missing terms → `blockers`, status `blocked`, nothing stubbed for definitions.

**Lean check** (`mathtcs.py check --file F [--substitute ID --proof-file P] [--axioms]`): copy module to `math-tcs/scratch/<id>/attempt-<n>.lean`, optionally substitute one proof, append `#print axioms <name>` for every declaration and helper, run `lake lean <scratch> -- --json` (fallback `lake env lean --json`) with timeout, parse JSON lines, attribute diagnostics to blocks by line range, compute `trust ∈ FULLY_VERIFIED|DIRECT_SORRY|TRANSITIVE_SORRY|UNFINISHED_CONSTRUCTION|NONSTANDARD_AXIOM|COMPILE_FAILURE` (port of `_compute_trust` + allowlist). Scratch copies never import the canonical module, so no root registration is needed for checking.

**Verify report** (`verify-report/v1`): `elaboration{kind: formal_check, …}`, `semantic_review{kind: model_review, statement_sha256, verdict, fidelity_findings[], degenerate_case_findings[]}`, `reuse_review{kind: model_review, statement_sha256, verdict ∈ exists_exact|exists_adaptable|not_found|not_searched, searched[], candidates[{name, owner, evidence{check, probe{tactic, ok, term}}, adaptation}]}`, `human_approval{kind: human, status: none}`, `recommended_action{action, reason, evidence[], priority, reuse_hint}`, `consistency{same_revision}`. `report combine` refuses mismatched `statement_sha256`. Action rules, first match wins: (1) elaboration failed / `COMPILE_FAILURE` / `NONSTANDARD_AXIOM` → `repair_statement`; (2) fidelity `fail` with severity ≥ high and confidence ≥ 0.6, or degenerate `outcome: false` → `repair_statement`; (3) blockers, blocking questions, or a blocked dependency → `defer`; (4) `exists_exact` with a successful probe → `reuse` (source record and block kept; only the proof source changes); (5) `exists_adaptable` with `#check` evidence → `prove` + `reuse_hint`; (6) else `prove`. `not_found` never raises priority.

**Prove report** (`prove-report/v1`): `{id, lean_rev, statement_sha256, budget, attempts[{n, proof_sha256, ok, trust, axioms, errors[], strategy}], result ∈ proved|unfinished|failed|statement_change_required, helpers[{name, trust}], statement_change|null, promoted}`; `proved` requires `FULLY_VERIFIED` after `promote` re-checks against the *current* canonical block; a helper on `sorry` → `TRANSITIVE_SORRY` → `unfinished`, obligation listed.

**Run record** (`math-tcs/runs/<startedAt>.json`, `run-record/v1`): `{started_at, args, stages_planned, stages_run, declarations: {id: {translate|scaffold|verify|prove: {status: ok|failed|missing|skipped, reason, artifacts[], attempts}}}, agents: [{label, phase, status, null_result}], summary}`. `missing` = an agent returned `null` (skipped or terminal error); `skipped` = cut by `--until`, ineligible, locked, or stale-blocked, always with `reason`.

## The scripted coordinator — `workflows/run.js`

```js
export const meta = { name: 'math-tcs-run', description: 'Translate → scaffold → verify → prove a source through math-tcs',
  phases: [{title:'Translate'},{title:'Scaffold'},{title:'Verify'},{title:'Prove'},{title:'Collect'}] }
// args: {pluginRoot, projectRoot, source, slug, chapter, until, stages:[...], parallel, budget, force, startedAt, agentPrefix}
const MAX_TRANSLATE_FIX = 2, MAX_SCAFFOLD_REPAIR = 2, MAX_REVIEW_RETRY = 1, MAX_PROVER_RESPAWN = 1
const T = n => `${args.agentPrefix}${n}`            // '' or 'math-tcs:' — decided in phase 0
const py = c => `python3 "${args.pluginRoot}/scripts/mathtcs.py" ${c}`
const runner = (cmd, label, phase, files) => agent(RUNNER_PROMPT(cmd, files), {agentType: T('tool-runner'), schema: RUNNER_RESULT, effort: 'low', label, phase})
const rec = {}  // rec[id][stage] = {status, reason, ...}; every null → {status:'missing'}
```
- **Translate:** `runner(source extract)` → `agent(translatorPrompt(ctx), {agentType: T('formal-translator'), schema: TRANSLATE_RESULT})` → `runner(annotated validate --assign-ids --write)`; on validator errors re-prompt the translator with the error list up to `MAX_TRANSLATE_FIX`; then `runner(annotated register)` → `decls[]`. `--until translate` returns here.
- **Scaffold:** `runner(context scaffold --ids …)` (script selects: annotated sections, existing module text, project declaration index from grep, candidate Mathlib names) → scaffolder agent (schema `PROPOSALS`) → `runner(scaffold apply proposals.json)`; if elaboration errors, up to `MAX_SCAFFOLD_REPAIR` repair rounds with the diagnostics; blocked ids recorded with blockers.
- **Verify:** `pipeline(scaffolded, snapshot, review, combine)` where `snapshot = id => runner(snapshot ID)`, `review = (snap, id) => parallel([semantic, reuse])` (barrier is correct: `combine` needs both; a `null` reviewer is retried once, then recorded `missing` and `combine` runs with the other side marked missing → action `defer` if the semantic side is missing), `combine = (both, id) => runner(save both JSON files + report combine)`.
- **Prove:** eligible = `action ∈ {prove, reuse}` ∧ not locked ∧ not stale; process in batches of `args.parallel` (sequential batches, items within a batch via `parallel`): `runner(lock)` → `agent(proverPrompt, {agentType: T('proof-worker'), schema: PROVE_RESULT})` (the prover runs `mathtcs.py check/probe` itself; budget from args) → `null` → respawn once → else record; `result === 'proved'` → promotion through a JS mutex (`chain = chain.then(() => runner(promote …))`) → `runner(unlock)` in a `finally`-equivalent (also on failure).
- **Collect:** `runner(runs record --json '<rec>')` (runner writes the object to `math-tcs/runs/<startedAt>.json` then calls the script to validate/normalise) → `return {planned, ran, counts, perId}`; `log()` prints per-phase progress and anything dropped (no silent caps).
- **Budget / resume:** guard loops on `budget.remaining()` when a target is set; the `run` skill records `runId` in the run record so `resumeFromRunId` can continue an interrupted run with cached prefix.

**Schemas** (inline JSON Schema objects in `run.js`): `RUNNER_RESULT {exit:int, stdout_json:object|null, stderr:string}`, `TRANSLATE_RESULT {path, ids:[…], tbd:int}`, `PROPOSALS {proposals:[{id, kind, lean_name, representation, existing_name, imports[], opens[], statement, doc_extra, difficulty{estimate,reason}, deviations[], blockers[], names_checked[]}]}`, `SEMANTIC_REVIEW`, `REUSE_REVIEW`, `PROVE_RESULT` (shapes as in Contracts).

## Commands (skills)

Common: `allowed-tools: Read, Write, Glob, Grep, Agent, AskUserQuestion, Bash(python3 *mathtcs.py*)`; first lines inject `` !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" args <stage> $ARGUMENTS` `` and `` !`… project detect` `` so `--until`, `--ids`, `--budget`, path-vs-excerpt are parsed by code.

| command | contract | behaviour |
|---|---|---|
| `/math-tcs:run <source> [--until translate\|scaffold\|verify\|prove] [--parallel K] [--budget N] [--slug] [--chapter]` | Args JSON (`stages` computed by script) + `startedAt` from `` !`date -u +%FT%TZ` `` | init config if missing (ask once, persist); write inline excerpt to `math-tcs/sources/` if not a path; call **Workflow** `{scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/run.js", args: {...}}`; on completion print the per-id table from the returned summary and the run-record path; on interruption print the `resumeFromRunId` instruction |
| `/math-tcs:translate` / `scaffold` / `verify` / `prove` | as in the previous plan (manual single-stage coordinators) | same scripts and agents, delegation via the Agent tool; verify launches both reviewers in one message; prove locks/promotes/unlocks per id |

Failure behaviour is uniform: a script exit ≠ 0 or an agent `null` becomes an explicit `failed`/`missing` entry (manifest `history` + run record) and the command continues with the remaining ids; nothing is silently dropped; canonical Lean is written only by `scaffold apply` and `promote`.

## Agents (`agents/*.md`, `model: inherit` unless noted)

| agent | tools | role / source prompt |
|---|---|---|
| `formal-translator` | Read, Grep, Glob, Write | `annotate` prompt rules (inherited hypotheses, verbatim quotes, honest `uncertain`); writes the annotated md |
| `lean-scaffolder` | Read, Grep, Glob, Bash (probe only) | `formalize` rules (source authoritative, statements only, record deviations, probe every name); returns proposals |
| `semantic-reviewer` | Read, Grep, Glob; `disallowedTools: Write, Edit, Bash` | `check-source` + `check-semantic`; echoes `statement_sha256` |
| `reuse-reviewer` | Read, Grep, Glob, Bash (`mathtcs.py probe` only) | `check-library` + searches project and `.lake/packages/*`; evidence required ("if Lean says a name does not exist, it does not exist") |
| `proof-worker` | Read, Grep, Glob, Bash (`check`, `probe`), Write (scratch only) | `prove` + `repair`; attempt loop within budget; never edits the statement — returns `statement_change`; `maxTurns` ~80 |
| `tool-runner` | Bash, Write; `model: haiku`, `maxTurns: 3` | runs exactly one given command (optionally writing given JSON to given paths first) and returns `{exit, stdout_json, stderr}` — no reasoning, no retries of its own |

## Installation, activation, update, usage (README)

- Validate: `claude plugin validate plugins/math-tcs --strict` (and the repo root for the marketplace).
- Dev: from tcslib, `claude --plugin-dir /Users/rxw/Desktop/projects/research/claude-math-tcs-agent/plugins/math-tcs`; `/reload-plugins` after edits.
- Persistent: `claude plugin marketplace add /Users/rxw/Desktop/projects/research/claude-math-tcs-agent` → `claude plugin install math-tcs@math-tcs-local --scope user` → restart → `claude plugin details math-tcs` (cache: `~/.claude/plugins/cache/math-tcs-local/math-tcs/<version>/`, enabled via `enabledPlugins` in `~/.claude/settings.json`).
- Update: bump `version` in both manifests → `claude plugin marketplace update math-tcs-local && claude plugin update math-tcs@math-tcs-local` → restart.
- Usage: `cd ~/Desktop/projects/research/tcslib && claude` → `/math-tcs:run /abs/path/notes.md --until verify` (approve the workflow dialog) → read `math-tcs/reports/*/rev1/verify.md` → `/math-tcs:run … ` or `/math-tcs:prove <id>`.
- Note: tcslib's `.claude/CLAUDE.md`/`AGENTS.md` forbid `lake build` loops for its own agents; math-tcs uses per-file `lake lean` by spec — documented, with a suggested one-line exemption.

## Implementation order

0. Write this plan to `/Users/rxw/Desktop/projects/research/claude-math-tcs-agent/IMPLEMENTATION_PLAN.md` (with a status checklist); keep `pipeline_kickoff_plan.md` as the requirements source.
1. **Phase 0 spike** — skeleton plugin (manifests, one `ping` skill, `tool-runner` + one echo agent, a 3-agent `workflows/ping.js`); dev-load in tcslib and record in `docs/phase0-findings.md`: (a) `agentType` string for plugin agents (`tool-runner` vs `math-tcs:tool-runner`) → `args.agentPrefix`; (b) Workflow call from a SKILL.md with `scriptPath` under `${CLAUDE_PLUGIN_ROOT}` (dev dir and cache dir) and `args` object; (c) whether the agent file's `tools`/`model` apply under `agentType`; (d) `!` injection with `$ARGUMENTS` and `${CLAUDE_PLUGIN_ROOT}` inside `allowed-tools`; (e) `lake lean <file> -- --json` forwarding on v4.25 and v4.32, fallback `lake env lean --json`; (f) `lakefile.lean` srcDir regex on tcslib.
2. **Scripts** — `args, project, config, ids, source_items, annotated_md, manifest, context, lean_json, lean_check+axioms, blocks, scaffold, probe, report, promote, runs`; unit tests (stdlib) + `lean`-marked tests against tcslib (good file, compile error, direct sorry, the `divides_add_add` TRANSITIVE_SORRY fixture, substitute+axioms → FULLY_VERIFIED, `probe check dvd_add`, `probe exact`); commit demo fixtures.
3. **Agents + stage skills** — translate and scaffold first (demo module elaborates with stubs), then verify (parallel reviewers, `combine`), then prove (`check` loop, `promote`, allowlist).
4. **`workflows/run.js`** — phases, runner helper, schemas, bounded retries, batching, promotion mutex, null → `missing`, run record; `tests/test_runjs_static.py` checks the file parses as ES module, `meta` is a literal, phase titles match, no `Date.now()`; `--until` unit-tested through `mathtcs.py args run`.
5. **Demonstrate one complete run** — in tcslib: `/math-tcs:run plugins/math-tcs/examples/demo/source/01_unit-1-divisibility.md --until prove`; expected: 6 items translated, `TCSlib/MathTcs/Divisibility.lean` scaffolded (local `Divides`, thm 1.1–1.3, exercises), verify reports with three separate sections + provenance line, thm 1.1/1.2 `proved` with only allowlisted axioms, thm 1.3 `unfinished` or `proved` via 1.2, exercises per their action; save `math-tcs/runs/<ts>.json` as `examples/demo/expected/run-demo.json` and write the transcript summary (agent count, wall time, any `missing`) into README "Demonstrated run". Then re-run → all proved blocks `skipped: already proved`, nothing rewritten; hand-edit one statement → `stale: statement_changed` → re-verified only.
6. **Packaging** — README, Makefile, `validate --strict`, persistent install + update walkthrough executed once and recorded; `examples/demo/expected/` regression fixtures.

## Verification

- `claude plugin validate plugins/math-tcs --strict` → 0; `pytest plugins/math-tcs/tests` (Lean tests skip unless `MATH_TCS_TEST_PROJECT` points at a project with `.lake/packages/mathlib`).
- Scripts-only e2e (`lean` marker): temp module `MathTcsTest.Divisibility` in the target: extract → validate expected md → `scaffold apply` expected proposals → `snapshot` → `combine` with fixture reviewer JSON → `promote` with fixture proof → manifest statuses/trust asserted → cleanup.
- Workflow demo (step 5) is the acceptance test: run record contains every id × stage with an explicit status; `journal.jsonl` shows both reviewers per id ran concurrently under the same `statement_sha256`; no canonical write outside `scaffold apply`/`promote`; `#print axioms` on promoted theorems ⊆ allowlist; interrupted run resumes with `resumeFromRunId`.
- Persistent install: fresh `claude` in tcslib lists `/math-tcs:*` and the six agents without `--plugin-dir`; version bump → update → `claude plugin details` shows it.

## Risks / unknowns (retired in phase 0 or explicitly recorded)
1. Plugin agent naming under `agentType`/`subagent_type` (prefix or not) — `args.agentPrefix`.
2. Workflow invocation ergonomics from a skill: permission dialog per run (documented), `scriptPath` resolution under the plugin cache directory.
3. Structured output + custom agents: schema instruction is appended to the agent's system prompt — confirm reviewers still return only findings.
4. `lake lean … -- --json` forwarding and cold-import time (~20 s per check; the prover's budget counts checks, `timeout_s` is per check).
5. Runner reliability for shell quoting: JSON payloads are written by the runner's Write tool to given paths, never passed as shell arguments.
6. tcslib's project CLAUDE.md is injected into every subagent; agent prompts name the math-tcs rule that overrides it (per-file `lake lean`, scratch only).
