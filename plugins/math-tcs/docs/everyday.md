# Everyday Lean assistant

The formalizer proposes a representation, a separate semantic reviewer checks its meaning,
and a proof worker proposes tactics. The Python harness checks and applies the result.
Skills are entry points, not replacements for these agents.

## Setup

Requires Python 3.11+, a supported macOS/Linux host, `lake`/`elan`, and an initialized Lean
project with dependencies already built and `lake-manifest.json` present. The package does
not install or update project dependencies. Core integration tests use Lean 4.25.0.

For GitHub installation in either host, follow the [quick start](../../../README.md#quick-start).
It uses `Shilun-Allan-Li/claude-math-tcs-agent`, independent of where users keep their projects.

For a downloaded or cloned checkout, open a terminal in its repository root and choose:

```bash
# Codex
codex plugin marketplace add .
codex plugin add math-tcs@math-tcs-local

# Claude Code
claude plugin marketplace add .
claude plugin install math-tcs@math-tcs-local --scope user
```

Then open your own Lean project in a new host session. Keep the checkout available when
using it as a local marketplace. To move it later, update the marketplace registration.

Codex: select the formalize, review, or simplify skill in the new thread.
Claude Code: use `/math-tcs:formalize`, `/math-tcs:review`, or `/math-tcs:simplify`.
The older stage skills are Claude-only even if the host lists them.
No user settings, personal marketplace, or hook trust entries are changed by this checkout.
Review and trust the installed hooks through the host UI before expecting automatic guidance.

Both hosts receive compact Lean guidance on session start and prompt submission inside Lean
projects. Hooks read files only and make no model calls. Set `MATH_TCS_ENABLED=0` to disable
automatic guidance; explicit skills still work. Codex supports the `CLAUDE_PLUGIN_ROOT`
compatibility variable used by the shared hook configuration.

Host contracts: [Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Claude hooks](https://code.claude.com/docs/en/hooks),
[Codex marketplaces](https://developers.openai.com/plugins/build/plugins),
[Claude marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).

For plugin development without installation, run `make dev TARGET="/path/to/your Lean project"`
from the checkout root. The plugin path is derived automatically from that checkout.
Legacy Mathlib tests likewise require an explicit `make test-lean TARGET="/path/to/project"`.

## Commands

Run from the project root; replace `MT` with `python3 /absolute/plugin/scripts/mathtcs.py`.
All task commands also accept `--root /absolute/project`.

```
MT check-file Main.lean --decl Demo.theorem_name --timeout 120
MT task begin --file Main.lean --source source.md --decl Demo.theorem_name --start 0 --end 0
MT task propose <id> --input replacement.txt
MT task review <id> --input review.json
MT task attempt <id> --input tactics.txt
MT task apply <id>
MT task status <id>
MT task abort <id>
```

The skill coordinator handles these commands; users need not manage offsets manually.
`start` and `end` delimit the authorized replacement using Unicode character offsets.
Replacement text contains one `__MATH_TCS_PROOF__` slot; tactics fill only that slot.
Simplify mode accepts only a proof-slot replacement, leaving surrounding source unchanged.
Definitions have real bodies; proof helpers are local `have`/`let` declarations.

Reports are durable `math-tcs/tasks/<id>/task.json` files containing the frozen source,
template history, reviews, attempts, diagnostics, and acceptance result. Treat these as
project-local artifacts, which may include private source material. They are not uploaded
by the harness; host model sessions receive the context their coordinator supplies.

Review JSON requires `snapshot`, `verdict`, `findings`, and `reason`. The exact contract and
host worker dispatch are in [agent-loop.md](agent-loop.md). A timeout or interrupted check
consumes an attempt. The four-attempt default covers proof-worker checks; application runs
one additional independent check. A missing review never authorizes an attempt.

Exit codes: 0 command succeeded, 1 refused/unverified/needs review, 2 invalid input or tool
error. Check JSON distinguishes successful compilation from verified selected declarations.
Unrelated `sorry` warnings do not invalidate an otherwise independent selected proof, but
are reported. A task's unsuccessful candidate never replaces the canonical file.

## Boundaries and recovery

One harness task owns the writer slot per project. Inspect the exact id before aborting an
interrupted task. Candidate checks and reviews remain on disk after abort. Source/context
changes require a new task; earlier reviews cannot authorize it. No stale lock stealing.

The harness serializes cooperating writers and rechecks freshness immediately before writing.
It cannot atomically coordinate with unrelated editors or sandbox hostile Lean metaprograms.
Read [protocol limits](agent-loop.md#limits) before treating it as a security boundary.
Proof-slot lexical containment deliberately rejects character literals, syntax quotations,
and unusual quoted declaration names. These unsupported cases are reported, not silently
rewritten. A model fidelity review is not a mathematical proof of source correspondence.

The old batch pipeline remains experimental; no manifest migration is needed. Neither a
complete cross-host live demonstration nor a measured improvement over a baseline should be
inferred from passing scripted tests. See [validation.md](validation.md) for actual evidence.

## Development checks

```
python3 -m pytest -q plugins/math-tcs/tests -m 'not lean'
python3 -m pytest -q plugins/math-tcs/tests/lean/test_plain.py
claude plugin validate plugins/math-tcs --strict
```

The new Lean tests create disposable projects and never modify tcslib. The legacy Lean suite
has different fixtures and is opt-in. Test new versions in both hosts before claiming support.
