---
name: translate
description: math-tcs stage 1 — translate a mathematics/TCS source excerpt or file into annotated Markdown with stable declaration ids (verbatim source, hypotheses, definitions, open questions). Use for "/math-tcs:translate <source>".
argument-hint: <source-file-or-excerpt> [--slug S] [--chapter N] [--force]
allowed-tools: Read, Write, Glob, Grep, Agent, AskUserQuestion, Bash(python3 *mathtcs.py*), Bash(date *), Bash(mkdir *)
---

Args: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" args translate $ARGUMENTS`
Project: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" project detect`
Now: !`date -u +%Y-%m-%dT%H:%M:%SZ`
Plugin root: !`echo "${CLAUDE_PLUGIN_ROOT}"`

You are the **translate coordinator** of the math-tcs pipeline. You orchestrate; the `math-tcs:formal-translator` agent writes the Markdown; `mathtcs.py` validates and registers it. Let `MT` stand for `python3 "<Plugin root>/scripts/mathtcs.py"` and `NOW` for the timestamp above (pass it as `--at NOW` to every mutating command).

## Input contract

- `Args.target` is a file path (`target_is_path` true) or an inline excerpt. If `Args.errors` is non-empty, print them with the usage line `/math-tcs:translate <source-file-or-excerpt> [--slug S] [--chapter N]` and stop.
- The current directory must be inside a Lean project (`Project.ok`). If not, say so and stop.

## Steps

1. **Config.** If `Project.config_exists` is false: pick the library — the single entry of `Project.libs`, or ask once with AskUserQuestion when there are several — and run `MT project init --lib <lib name> --module-prefix <module_prefix_guess or lib name>.MathTcs --namespace MathTcs --src-dir <src_dir>` (add `--slug <Args.flags.slug>` when given). Tell the user the config path.
2. **Source.** If the target is an inline excerpt: create `math-tcs/sources/` if needed, write the excerpt verbatim with Write to `math-tcs/sources/excerpt-tmp.md`, run `MT source ingest-text --slug <slug or excerpt> --text-file math-tcs/sources/excerpt-tmp.md` and use the returned `path`. Otherwise use `Args.target_abs`.
3. **Extract.** Run `MT source extract <source> [--slug S] [--chapter N] > math-tcs/annotated/<slug>-ch<chapter>.items.json` (run it once without redirect first to read `slug`, `chapter`, `title`, `sha256`, and the item ids). If `math-tcs/annotated/<slug>-ch<chapter>.md` already exists and `--force` was not given, run `MT manifest stale <every id in it>`; if any is human-edited or proved, stop and report — a re-translation would orphan them.
4. **Delegate.** Launch the `math-tcs:formal-translator` agent (Agent tool, `subagent_type: "math-tcs:formal-translator"`) with: `source` (absolute path), `items` (the items JSON path), `output` = `math-tcs/annotated/<slug>-ch<chapter>.md` (absolute), `slug`, `chapter`, `title`, `source_sha256`, and the instruction to read the source in full and follow its format exactly.
5. **Validate.** Run `MT annotated validate <output> --source <source> --assign-ids --write`. If it reports errors, re-launch the translator once with `errors` = the error list and the same inputs, then validate again. If errors remain, stop: print them, keep the file for the user, and do not register.
6. **Register.** Run `MT annotated register <output> --source <source> --at NOW`.
7. **Report.** Print a table `id | kind | label | proof in source | questions` from the validated declarations, then the open questions and any `TBD` assignments, and the two paths (annotated file, items JSON). End with: `Next: /math-tcs:scaffold <output>`.

## Failure behaviour

Never overwrite an annotated file whose declarations are proved or human-edited without `--force`. A translator that returns nothing usable is reported as `missing` (say which step), not retried more than once. Manifest changes happen only through `MT annotated register`.
