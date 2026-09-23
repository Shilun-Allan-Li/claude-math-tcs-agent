# Ordinary-file task protocol

The current host agent is the coordinator. Worker roles return text; only the coordinator
calls the harness. On Claude Code use `math-tcs:lean-formalizer`, `math-tcs:lean-semantic-reviewer`,
and `math-tcs:lean-proof-worker`. On Codex create separate read-only workers using the same
agent Markdown bodies as instructions. If delegation is unavailable, report that limitation;
do not silently substitute self-review and claim independent review.

Resolve this document's parent plugin directory. `MT` below means
`python3 <absolute-plugin-root>/scripts/mathtcs.py`. Pass argument arrays where possible and
quote paths for shell calls. Invoke from the target project or provide `--root <project>`.
Read project instructions before executing Lean. Honor restrictions; never override them by
claiming that the plugin outranks project instructions.
Require an initialized Lake environment and existing `lake-manifest.json` before starting.
Do not run initialization or dependency updates silently.

## Formalize / simplify

1. Select one fully qualified theorem name and the user-authorized edit range. Read the
   target verbatim. Offsets are zero-based Unicode character offsets, not bytes or lines.
   A new file uses 0/0; insertion into an existing file uses equal offsets. For simplify,
   select exactly the existing proof term, excluding the `:=` and following commands.
   If the selection is ambiguous, clarify rather than guessing a large replacement range.
2. Store the user's source excerpt (or exact simplification request) in a task-local input
   file under `math-tcs/inputs/` (use a unique directory). Do not alter the canonical Lean file.
   Run `MT task begin --file <target> --source <input> --decl <name> --start N --end N
   --mode formalize|simplify`. This returns an id and records a snapshot at
   `math-tcs/tasks/<id>/task.json`. One task may own a project's writer slot at a time.
3. Formalize: invoke the formalizer with the task JSON and relevant source paths. It returns
   the replacement text containing one `__MATH_TCS_PROOF__` token. Simplify: the replacement
   is just that token. Save this proposal under the input directory and run
   `MT task propose <id> --input <replacement-file>`.
4. Invoke a fresh semantic reviewer with the task JSON. Save its JSON unchanged and run
   `MT task review <id> --input <review.json>`. Require status `ready`. For divergence,
   return findings to the formalizer and resubmit/re-review (two repair rounds maximum).
   For material ambiguity, ask the user and end the task with `task abort`; begin again
   with the clarified source. Never manufacture a faithful verdict to move forward.
5. Invoke the proof worker with the reviewed task. Save returned tactics to an input file
   and run `MT task attempt <id> --input <tactics-file>`. Supply failed check diagnostics
   to the worker, stopping at four attempts by default. The CLI counts attempts before
   executing Lean, including interrupted checks. Statement-change requests go back to
   step 3 and a new review; they do not reset the proof budget.
6. Once status is `checked`, run `MT task apply <id>`. This independently checks the accepted
   candidate again, verifies context freshness, and writes only the selected target file.
   That acceptance check is separate from the four proof attempts. Never copy a candidate
   to the canonical file yourself. On failure or exhaustion, report the obligation and
   `MT task abort <id>` to release the writer slot; all task evidence remains available.
7. Report the edited file, theorem, axiom evidence, semantic-review conclusion, and task
   report path. Distinguish kernel evidence from model judgment. Do not claim a whole
   file is sorry-free merely because the selected theorem is verified.

`MT task status <id>` reads a durable task report and reconciles an interrupted application
against the saved original and candidate. Interrupted checks consume attempts but
leave the task resumable. If a task is stuck, inspect it and explicitly abort its exact id;
there is no time-based lock stealing. Review schema: `snapshot` (exact string), `verdict`
(`faithful`, `divergent`, `uncertain`), `findings` (unresolved issue strings), `reason`
(nonempty explanation). Only faithful with no unresolved findings advances.

## Review only

Read the source if supplied and the selected Lean declaration and dependencies. Invoke
the semantic reviewer independently with this material (no mutable task is required).
Run `MT check-file <file> --decl <qualified-name>` for formal evidence. Return findings with
file locations, compilation/axiom results, and a separate fidelity assessment. Without an
informal source, report fidelity as unassessed. Do not modify the file or acquire a writer slot.

## Limits

The task protocol is a cooperative local workflow, not a sandbox for hostile agents or
executable Lean metaprograms. Workers get no shell/write tools in Claude; on hosts without
equivalent restrictions this is a role contract. Budget enforcement covers harness calls,
not arbitrary Lean commands outside it. The harness controls accepted proof-slot edits;
the reviewer must verify that the proposed slot is in the intended theorem. Quoted declaration
names and syntax quotations in proofs are unsupported and fail explicitly.

Context invalidation conservatively hashes project/package Lean sources and Lake metadata;
it does not certify the provenance of externally modified compiled `.olean` artifacts.
Build dependencies normally before starting. The final freshness check protects observed
user edits, but cannot provide an atomic compare-and-swap against editors that ignore the
harness lock. Do not run external writers on the same target during acceptance.
