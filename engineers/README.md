# engineers

Lower-tier service layer for upstream agents (`claude_prover/`, `distill_mathematicians/`).

## Core principle

The engineer layer is **request-response only**. It receives a bounded tool request and returns a compact audited report.

It does NOT decide:
- proof strategy
- whether a theorem is true
- whether a distilled pattern should be promoted
- whether a generated skill is conceptually correct
- what the final proof should say

Engineer reports facts. The caller interprets.

## Layout

```
engineers/
  agents/engineer.md       ← single subagent, model=sonnet
  commands/engineer.md     ← /engineer <verb> <json-args>
  lib/
    audit.py               ← begin / run / finalize harness (portable timeout)
    cli.py                 ← dispatcher: `python3 engineers/lib/cli.py <verb> <json>` runs a verb end-to-end through the audit harness, prints the report
    verbs/                 ← one Python module per verb (run_python, run_cpp, …)
  README.md
```

The agent normally calls `audit.py begin / run / finalize` directly (see the agent spec). `cli.py` is the equivalent path for callers that prefer to invoke a verb without going through the agent — it composes the same harness into a single command.

Runtime artifacts (gitignored):

```
engineering/
  artifacts/
    <request_id>/
      request.json     ← what was asked
      stdout.txt       ← full stdout from execution
      stderr.txt       ← full stderr
      report.json      ← compact report returned to caller
      files_out/       ← any files the verb produced
```

`request_id` format: `YYYYMMDDTHHMMSSZ-<verb>-<6char-hex>`.

## Verb menu

| verb | input schema | what it does |
|---|---|---|
| `run-python` | `{code, files_in[]?, timeout_s}` | Execute Python in the sandbox, capture stdout/stderr/exit. |
| `run-cpp` | `{source, stdin?, compile_flags[]?, timeout_s}` | Compile + run C++ via g++. |
| `run-matlab` | `{script, timeout_s}` | Run MATLAB batch script (requires matlab on PATH). |
| `web-search` | `{query, k, recency_days?}` | Top-k web results with `{url, title, snippet}`. |
| `index-source` | `{path\|url, kind: pdf\|tex\|tar\|repo}` | Extract + chunk a source into `files_out/chunk_NNN.txt`. |
| `count-tokens` | `{path\|text, model}` | Token count for the named model. |
| `compute` (escape hatch) | `{lang, script, env_pkgs[]?, timeout_s}` | Run arbitrary script in any supported language. Use only when no named verb fits. |

Output shape (every verb): `{request_id, verb, exit_code?, duration_s?, stdout_excerpt, stderr_excerpt, files_out[], finished_at, ...verb-specific fields}`. Excerpts are head/tail of 40 lines each; full output stays in the artifact dir.

## Invocation

**From a subagent (primary path):** dispatch the `engineer` agent with a single message of the form `<verb> <json-args>`.

**From the CLI or another agent:** `/engineer <verb> <json-args>`.

**From `distill_mathematicians/` collectors:** same `/engineer` slash command. Migration of existing inlined HTTP/extraction is non-blocking — switch when convenient.

## Forbidden

The engineer cannot:
- Write outside `engineering/artifacts/<request_id>/`.
- Read or write `proof/`, `skills/`, `phds/knowledge_db/`. (Read on `papers/` and `skills/` is permitted for context.)
- Make mathematical judgments. It reports `stdout: 3.14159`, never "therefore the theorem holds."
- Chain verbs. One invocation = one verb. Multi-step work is the caller's responsibility.

## Adding a new verb

A `compute(...)` request that has been used 3+ times for the same shape becomes a candidate for promotion. To add a new named verb:

1. Add the schema and `How:` section to `engineers/agents/engineer.md` under "Verb menu".
2. Add the row to the table here.
3. Add the verb name to `KNOWN_VERBS` in `engineers/lib/audit.py`.

No other registry to update.
