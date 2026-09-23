# math-tcs — Claude Code plugin

## Everyday Lean assistant (Claude Code and Codex)

Use the new `formalize`, `review`, and `simplify` skills for individual declarations in
ordinary Lean files. They use dedicated formalizer/reviewer/proof-worker roles and a Python
harness with snapshot-bound review, proof-slot containment, bounded attempts, and independent
Lean acceptance checks. [Setup, commands, and limits](docs/everyday.md).

**The remaining documentation describes the older experimental Claude-only batch pipeline.**
Claims below about parallel writers, complete demos, and selective reruns are design intent;
the review in the repository identifies outstanding implementation limitations. The new
everyday workflow does not use that manifest or promotion path.

Translate → scaffold → verify → prove: a mathematics/TCS source excerpt becomes annotated
Markdown, then a Lean 4 module with `sorry` stubs in your project's layout, then reviewed
statements, then proofs that are promoted only when `#print axioms` shows no `sorryAx` and
nothing outside the axiom allowlist. Everything runs through your authenticated Claude
Code session: skills coordinate, custom agents do the mathematics, small stdlib Python
scripts do the deterministic work (Lean checks, files, manifest), and `/math-tcs:run` drives
the whole pipeline from a scripted workflow.

## Commands

| command | does |
|---|---|
| `/math-tcs:translate <source> [--slug S] [--chapter N]` | source file or inline excerpt → `math-tcs/annotated/<slug>-ch<N>.md` (stable ids, verbatim source, hypotheses, definitions, open questions) |
| `/math-tcs:scaffold <annotated-md \| slug> [--module Name] [--ids a,b] [--force]` | annotated Markdown → `<lib>/MathTcs/<Module>.lean` with explicit statements and `by sorry` bodies; missing terms are blockers, never stubs |
| `/math-tcs:verify <lean-file \| id \| slug> [--ids a,b]` | Lean elaboration (formal) + semantic reviewer ‖ reuse reviewer (model) on the same frozen revision → `math-tcs/reports/<id>/rev<N>/verify.{json,md}` with action `reuse \| prove \| repair_statement \| defer` |
| `/math-tcs:prove <lean-file \| id \| slug> [--ids a,b] [--budget N] [--force]` | budgeted proof attempts on a scratch copy; promotion only when `FULLY_VERIFIED`; helper lemmas tracked; statement changes returned for re-review |
| `/math-tcs:run <source> [--until translate\|scaffold\|verify\|prove] [--parallel K] [--budget N]` | the whole pipeline as one workflow run (`workflows/run.js`), with a run record at `math-tcs/runs/<started>.json` |

`--until` is parsed by code (`scripts/mathtcs.py args run …`) and the stage list is computed before anything starts.
`/math-tcs:ping [words] [--until stage]` is a diagnostic that prints how the plugin sees its arguments and root
(`workflows/ping.js` is the matching agent-resolution check used in phase 0).

## Requirements

- Claude Code ≥ 2.1.265 (plugin skills, custom agents, the Workflow tool).
- `python3` ≥ 3.11 (the scripts are stdlib-only; 3.14 tested).
- `elan`/`lake` on `PATH` and a target Lean project whose Mathlib is already built (`lake build` once or `lake exe cache get`). The plugin never runs `lake update` or a whole-project `lake build`; it elaborates single files with `lake lean <file> -- --json` (fallback `lake env lean --json`).

## Install

Validate first (from this repository):

```bash
claude plugin validate plugins/math-tcs --strict
claude plugin validate . --strict          # the local marketplace manifest
```

**Development loading (not persistent).** From this repository's root:

```bash
make dev TARGET="/path/to/your Lean project"
# edit the plugin, then in the session: /reload-plugins
```

**Persistent installation** (this repository is a local marketplace named `math-tcs-local`):

```bash
claude plugin marketplace add .   # run from this repository's root
claude plugin install math-tcs@math-tcs-local --scope user      # or --scope project|local
# restart Claude Code, then:
claude plugin list
claude plugin details math-tcs
```

The installed copy lives under `~/.claude/plugins/cache/math-tcs-local/math-tcs/<version>/`; activation is the
`enabledPlugins["math-tcs@math-tcs-local"] = true` entry that `install` writes to `~/.claude/settings.json`
(toggle with `/plugin`). A `--plugin-dir` load of the same name wins over the installed copy for that session only.

**Update.** Bump `version` in `plugins/math-tcs/.claude-plugin/plugin.json` *and* in
`.claude-plugin/marketplace.json`, commit, then:

```bash
claude plugin marketplace update math-tcs-local
claude plugin update math-tcs@math-tcs-local
# restart Claude Code
```

`make validate | test | test-lean | dev | install | update` at the repository root wrap all of the above.

## Usage

From inside the target project:

```
/math-tcs:run /abs/path/notes.md --until verify        # approve the workflow dialog once
```

Then read `math-tcs/reports/*/rev1/verify.md`, and either

```
/math-tcs:run /abs/path/notes.md                       # completes with prove (verified ids are skipped, not redone)
/math-tcs:prove dn-ch1-thm-1.2 --budget 6              # one declaration by hand
```

On first use the plugin detects the project (`lean-toolchain`, `lakefile.toml`/`lakefile.lean`, `lean_lib`
entries) and writes `math-tcs/config.json`:

```json
{"lean": {"lib": "TCSlib", "src_dir": ".", "module_prefix": "TCSlib.MathTcs", "namespace": "MathTcs",
          "check": "lake lean", "timeout_s": 600, "register_in_root": false, "root_file": "TCSlib.lean"},
 "axioms": {"allow": ["propext", "Classical.choice", "Quot.sound"]},
 "prove": {"budget": 4, "max_helpers": 3, "parallel": 1}, "ids": {"slug": "dn"}}
```

`register_in_root: true` makes scaffold append `import TCSlib.MathTcs.<Module>` to the root file so `lake build`
covers the new module (checking never needs it). `sorryAx` is rejected even if listed in `allow`.

## Where things go (in the target project)

```
math-tcs/config.json  manifest.json  .gitignore        ids → paths, revisions, status, trust, locks, history
math-tcs/annotated/<slug>-ch<N>.md  (+ .items.json)   the intermediate representation
math-tcs/reports/<id>/rev<N>/{statement.lean, context.json, elaboration.json, semantic.json, reuse.json, verify.json, verify.md}
math-tcs/reports/<id>/prove-rev<N>-<k>.json           every prove attempt report; statement-change-rev<N>.md when the prover objects
math-tcs/runs/<started_at>.json                       run records (every id × stage has status ok|failed|missing|skipped + reason)
math-tcs/scratch/, locks/, context/                   gitignored working files
<src_dir>/<module_prefix as path>/<Module>.lean       e.g. TCSlib/MathTcs/Divisibility.lean
```

Lean blocks are delimited by `-- math-tcs:begin id=<id> rev=<n>` … `-- math-tcs:end id=<id>` line comments.
The generated doc comment carries the kind and label, the id, the source reference and verbatim statement, the
verbatim proof (or `_No proof in source._`), the difficulty *estimate* with its reason, and declared deviations.

## Rules that are enforced by scripts, not by prompts

- identity is source-derived (`<slug>-ch<N>-<kind>-<label|section-ordinal>`), never hashed from wording;
- theorem bodies at scaffold are exactly `sorry`; a tactic body is rejected; a definition with a `sorry` body or
  a missing term is `blocked`;
- both reviewers read the same frozen snapshot and must echo its `statement_sha256`; a mismatch is recorded and
  the action falls back to `defer`;
- action rules (first match): elaboration failed / nonstandard axiom → `repair_statement`; high-severity
  fidelity `fail` (confidence ≥ 0.6) or a `false` instantiation → `repair_statement`; blockers / blocking
  questions / blocked dependency → `defer`; `exists_exact` **with a probe** → `reuse`; else `prove` (a
  `not_found` never raises priority);
- promotion re-checks against the *current* canonical module; the statement signature must be unchanged;
  `FULLY_VERIFIED` only (no `sorryAx`, axioms ⊆ allowlist); a helper on `sorry` leaves the target `unfinished`;
- proved and human-edited blocks are never rewritten without `--force` (the proposal is saved next to the
  report instead); a human edit of a statement bumps the revision and invalidates verify/prove results;
- one writer per declaration (`math-tcs/locks/<id>.json`), promotions serialized;
- every stage result is recorded explicitly — `missing` when an agent returned nothing, `skipped` with a reason.

Model reviews are labelled as such in every report; `human_approval` stays `none` until a person runs
`python3 scripts/mathtcs.py manifest approve <id> --by <name>`.

## The workflow coordinator (`workflows/run.js`)

`/math-tcs:run` stages a copy of `run.js` into `<project>/math-tcs/workflows/` (the Workflow tool only loads
scripts under the working directory) and launches it with `{pluginRoot, projectRoot, source, slug, chapter,
until, stages, parallel, budget, force, startedAt, agentPrefix: "math-tcs:"}`. The script owns:

- stage order and the `--until` cut-off; phases `Translate → Scaffold → Verify → Prove → Collect`;
- bounded retries: ≤2 translator fix rounds on validator errors, ≤2 scaffolder repair rounds on elaboration
  errors, 1 reviewer retry, 1 prover respawn;
- parallelism: `pipeline()` over declarations for verify with the two reviewers in a `parallel()` barrier per
  declaration; provers in batches of `--parallel K`, promotions through a mutex;
- context selection by code (`mathtcs.py context <stage> <id>` packages: annotation, verbatim source, sibling
  signatures, definitions used, project grep matches, reuse hints);
- result collection: `math-tcs/runs/<startedAt>.json` with an explicit status for every declaration × stage.

The runtime has no filesystem access, so every deterministic step runs through the `math-tcs:tool-runner`
agent (haiku, `Bash` + `Write`, ≤4 turns) which executes exactly one `mathtcs.py` command and returns its JSON.
Resume an interrupted run with the printed `runId` (`Workflow({scriptPath, resumeFromRunId})`).

## Scripts (`scripts/mathtcs.py`)

`args`, `project detect|init`, `ids make`, `source extract|ingest-text`, `annotated validate|register|section|skeleton`,
`manifest get|list|set-status|set|lock|unlock|stale|touch|approve`, `scaffold apply|extract|module-name|module-path`,
`check`, `snapshot`, `probe check|tactic`, `report combine|prove`, `promote`, `scratch prepare`, `context`, `runs record`,
`workflow stage`. Every command prints one JSON object; exit 0 ok, 1 refused (the JSON says why), 2 error.

## Tests

```bash
cd plugins/math-tcs/tests
python3 -m pytest -q -m "not lean"                      # unit: args, ids, extraction, IR, blocks, manifest, action rules, run.js static
MATH_TCS_TEST_PROJECT="/path/to/your Lean project" python3 -m pytest -q -m lean
```

The Lean tests write a throwaway module (`math-tcs-test/`) and, for the scripts-only end-to-end test, a
temporary project that symlinks the target's `.lake`; they never touch the target's own sources.

## Demonstrated run

See `docs/demo-run.md` (written from the first complete `/math-tcs:run` on `examples/demo/source/01_unit-1-divisibility.md`
in tcslib) and `examples/demo/expected/` for the artifacts a run produces.

## Notes for tcslib

tcslib's `AGENTS.md`/`.claude/CLAUDE.md` tell its own agents never to run `lake build`/`lean`. math-tcs runs
per-file `lake lean` on scratch copies by design (the spec requires real elaboration); consider adding to tcslib's
CLAUDE.md: "math-tcs may run `lake lean` on files under `math-tcs/scratch/`."
