---
name: scaffold
description: math-tcs stage 2 — turn an annotated Markdown file into a Lean module in the project's layout, statements only with `sorry` bodies, after inspecting the project and Mathlib; missing terms become blockers. Use for "/math-tcs:scaffold <annotated-md | slug>".
argument-hint: <annotated-md-or-slug> [--module Name] [--ids a,b] [--force]
allowed-tools: Read, Write, Glob, Grep, Agent, AskUserQuestion, Bash(python3 *mathtcs.py*), Bash(date *)
---

Args: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" args scaffold $ARGUMENTS`
Project: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" project detect`
Now: !`date -u +%Y-%m-%dT%H:%M:%SZ`
Plugin root: !`echo "${CLAUDE_PLUGIN_ROOT}"`

You are the **scaffold coordinator**. The `math-tcs:lean-scaffolder` agent proposes statements; `mathtcs.py scaffold apply` validates them (theorem bodies must be exactly `sorry`; definitions must have real bodies), merges them into the module, elaborates, and updates the manifest. `MT` = `python3 "<Plugin root>/scripts/mathtcs.py"`; `NOW` = the timestamp above.

## Input contract

`Args.target` is an annotated Markdown path or a slug. `Project.config_exists` must be true (otherwise say to run `/math-tcs:translate` first). If `Args.errors` is non-empty, print them with `/math-tcs:scaffold <annotated-md | slug> [--module Name] [--ids a,b] [--force]` and stop.

## Steps

1. **Resolve declarations.** Path → read its front matter for `slug`/`chapter`/`title`; slug → `MT manifest list --slug <slug>` and take the `annotated.path` of its entries. Restrict to `Args.flags.ids` when given. Run `MT manifest stale <ids…>`: declarations that are `proved`, `human_edited`, or human-approved are **skipped** unless `--force` (list them as skipped with the reason).
2. **Module.** `Args.flags.module` or `MT scaffold module-name --title "<title>"` → `module_short`, `module`, `path`. Read the module file if it exists (never edit it by hand).
3. **Context.** Run `MT context scaffold <ids…> --annotated <annotated path>`; note each package path.
4. **Delegate.** Launch `math-tcs:lean-scaffolder` (Agent tool) with: the context package paths, `project` (root, lib, `src_dir`, `module_prefix`, namespace, Mathlib path `.lake/packages/mathlib/Mathlib`, toolchain), the module name and existing file path, `probe` = `MT probe check <Name…> --imports <M,N>` (say the imports the module already has, if any), and — on a repair round — `diagnostics`. Ask for the proposals JSON as its return value.
5. **Apply.** Write the returned JSON with Write to `math-tcs/context/scaffold/<slug>-ch<chapter>-proposals.json` (set `"module"` to `module_short` if absent), then run `MT scaffold apply <that file> --module <module_short> --at NOW` (add `--force` only if the user passed it). This runs Lean once (~20–60 s).
6. **Repair round (once).** If `elaboration.ok` is false or some written block is `blocked` from elaboration, re-launch the scaffolder with those diagnostics and the previous proposals, write the new proposals, and apply again. After that, remaining problems stay recorded as blockers.
7. **Report.** Table `id | outcome | lean name | difficulty (estimate) | trust | blockers`; the module path; whether the import was registered in the root file, otherwise the exact `import …` line to add for `lake build` (checking does not need it). End with `Next: /math-tcs:verify <module path>`.

## Failure behaviour

A proposal with a tactic body is rejected (`scaffold_failed`), a definition with a `sorry` body or a missing term is `blocked` — neither is stubbed. The canonical module is written only by `MT scaffold apply`. An agent that returns no JSON is recorded as `missing` for those ids and the step ends.
