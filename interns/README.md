# interns

Lower-tier file-organization layer for the proof workflow.

## Core principle

The intern layer keeps the runtime `proof/` tree clean as users iterate on outlines mid-proof. It does NOT write math, decide proof correctness, or touch `skills/` / `phds/` / `engineering/`.

Two layers split by cost: deterministic hooks (no LLM) for the easy 80%, a Haiku subagent for ambiguous reconciliation.

## Layout

```
interns/
  agents/intern.md        ← Haiku subagent for reconciliation judgment calls
  commands/intern.md      ← /intern reconcile
  README.md
```

Plus the deterministic hook scripts wired in `.claude/settings.local.json`:

```
.claude/hooks/
  step_index.py           ← keeps OUTLINE.md ticks in sync with step files
  outline_diff.py         ← detects orphaned step files when outline changes
  review_dedupe.py        ← archives older review files when multiple exist per step
  archive_gc.py           ← compresses old archive dirs at session end
```

## Two-layer split

**Layer A — deterministic hooks (no LLM):**
- Fire on `PostToolUse` (Write/Edit) and `Stop` (session end).
- Pure file operations: tick syncing, orphan detection, review dedupe, archive compression.
- 80% of the cleanup work happens here for zero tokens.

**Layer B — intern subagent (Haiku):**
- Triggered when `outline_diff.py` writes `proof/.intern_inbox/orphans.json`.
- Reads the inbox, decides per file (archive / flag-renumber / flag-ambiguous), moves files, writes a reconciliation report, clears the inbox.
- Never deletes, never renumbers (renumbering is the orchestrator's call).

## Trigger flow

```
user edits proof/OUTLINE.md (removes step 3)
   ↓
PostToolUse hook outline_diff.py runs (no LLM)
   ↓
writes proof/.intern_inbox/orphans.json with step_03 listed
   ↓
next turn: orchestrator notices orphans.json
   ↓
spawns intern subagent (Haiku)
   ↓
intern moves proof/step_03.md → proof/archive/<ts>/orphaned/step_03.md
intern writes proof/.intern_inbox/reconciliation_<ts>.md
intern clears proof/.intern_inbox/orphans.json
```

## Inbox contract

`proof/.intern_inbox/` is the message bus between hooks and the intern.

- `orphans.json` — written by `outline_diff.py`, read+cleared by intern. Shape:
  ```json
  {
    "detected_at": "2026-04-27T03:42:13.909869+00:00",
    "orphans": [
      {"step": 3, "file": "proof/step_03.md", "reason": "step number not in outline"}
    ]
  }
  ```
- `reconciliation_<ts>.md` — written by intern, persists for audit.

## Permissions

| Layer | Tool surface | Write scope | Network |
|---|---|---|---|
| Hooks | none (Python stdlib) | `proof/` only | no |
| Intern | Read, Write, Edit, Glob, Bash | `proof/` only | no |

Neither layer touches `skills/`, `phds/`, or `engineering/`.

## Manual invocation

```
/intern reconcile
```

Triggers the intern subagent directly. Useful for: testing, recovering from a missed auto-trigger, or reconciling without waiting for an orchestrator turn.
