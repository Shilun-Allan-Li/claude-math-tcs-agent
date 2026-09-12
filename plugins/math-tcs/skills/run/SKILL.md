---
name: run
description: math-tcs pipeline — translate → scaffold → verify → prove a source through the scripted workflow coordinator (stage ordering, parallel reviewers/provers, bounded retries and result collection in code). Use for "/math-tcs:run <source> [--until verify]".
argument-hint: <source-file-or-excerpt> [--until translate|scaffold|verify|prove] [--parallel K] [--budget N] [--slug S] [--chapter N] [--module Name] [--force]
allowed-tools: Read, Write, Glob, Grep, Workflow, AskUserQuestion, Bash(python3 *mathtcs.py*), Bash(date *), Bash(mkdir *)
---

Args: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" args run $ARGUMENTS`
Project: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" project detect`
Now: !`date -u +%Y-%m-%dT%H:%M:%SZ`
Plugin root: !`echo "${CLAUDE_PLUGIN_ROOT}"`

You are the **run coordinator**. The whole run is executed by the workflow script `workflows/run.js` (the user opted into workflow orchestration by invoking this command); your job is to prepare its inputs deterministically, launch it once, and report its results. `MT` = `python3 "<Plugin root>/scripts/mathtcs.py"`; `NOW` = the timestamp above.

## Input contract

`Args.target` is a source path or an inline excerpt; `Args.stages` is the computed stage list (`--until` already applied). If `Args.errors` is non-empty, print them with `/math-tcs:run <source> [--until translate|scaffold|verify|prove] [--parallel K] [--budget N]` and stop. The current directory must be inside a Lean project.

## Steps

1. **Config.** If `Project.config_exists` is false: pick the library — the single entry of `Project.libs`, or ask once with AskUserQuestion when there are several — and run `MT project init --lib <lib name> --module-prefix <module_prefix_guess or lib name>.MathTcs --namespace MathTcs --src-dir <src_dir>` (add `--slug <Args.flags.slug>` when given). Do not read other skill files; everything needed is here.
2. **Source.** If `Args.target_is_path`, let `SOURCE` = `Args.target_abs`. Otherwise the target is an inline excerpt: `mkdir -p math-tcs/sources`, write the excerpt verbatim with Write to `math-tcs/sources/excerpt-tmp.md`, run `MT source ingest-text --slug <Args.flags.slug or excerpt> --text-file math-tcs/sources/excerpt-tmp.md`, and let `SOURCE` be the returned `path`.
3. **Stage the workflow.** `MT workflow stage` → `scriptPath` (a copy of `run.js` inside the project, because the Workflow tool only loads scripts under the working directory).
4. **Launch.** Call the **Workflow** tool exactly once:
   - `scriptPath`: the path from step 3
   - `args`: `{"pluginRoot": "<Plugin root>", "projectRoot": "<Project.root>", "source": "<SOURCE>", "slug": <Args.flags.slug or null>, "chapter": <Args.flags.chapter or null>, "module": <Args.flags.module or null>, "until": <Args.flags.until or "prove">, "stages": <Args.stages>, "parallel": <Args.flags.parallel or config prove.parallel or 1>, "budget": <Args.flags.budget or config prove.budget>, "force": <Args.flags.force>, "startedAt": "<NOW>", "agentPrefix": "math-tcs:"}`
   Do not pass the script inline and do not run the stages yourself; if the tool is refused, stop and say so.
5. **Report.** From the workflow's return value print: the stages planned vs run; a table `id | translate | scaffold | verify (action) | prove (result) | status | trust`; the counts of `ok/failed/missing/skipped` per stage; the run record path (`math-tcs/runs/<startedAt>.json`) and the workflow `runId` (for `resumeFromRunId` if the run was interrupted); the report paths under `math-tcs/reports/`. Every `missing`/`failed` entry must appear with its reason.

## Failure behaviour

An interrupted or failed workflow still leaves the manifest and per-stage reports consistent (every script step is atomic); tell the user to rerun the same command — completed declarations are skipped by the staleness rules — or to resume with the printed `runId`.
