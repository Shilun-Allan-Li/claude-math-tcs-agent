# Validation record — 2026-09-24

## Completed locally

Final run: **76 non-Lean tests passed; 7 real Lean integration tests passed**.
The four legacy Lean tests were not run. Plugin and marketplace validation passed.

- Unit/regression tests cover task ownership, incomplete reviews, uncertainty, old snapshot
  rejection, two repair rounds, proof budgets, interrupted checks, proof-term containment,
  simplification scope, project changes during acceptance, package definition changes,
  independent acceptance failure, CLI round trips, hook activation/opt-out, and legacy
  workflow status handling.
- Five real Lean integration tests run in disposable projects on Lean 4.25.0: namespace,
  section-variable and local-notation checks; direct and transitive `sorry`; nonstandard
  axioms; nonexistent declarations; compile errors; timeouts; and a full task through
  independent acceptance and a subsequent check of the written file; completion of an
  unfinished theorem and simplification of an existing proof by reusing `Nat.zero_add`.
- Claude plugin strict validation, the Codex plugin schema validator, and the three new
  skill validators pass. Hook tests verify read-only behavior and malformed-input handling.
- Portability tests copy the plugin to a different directory containing spaces and Unicode,
  invoke its CLI from a separate Lean project's subdirectory, execute both hook commands,
  and resolve the shared skill references. Makefile checks cover a relocated checkout,
  a relative target path with spaces, and rejection of a missing target. These tests do
  not install a plugin or call a model service.
- Public discovery now exposes only `formalize`, `review`, `simplify`, and their three
  `lean-*` workers. The public CLI rejects retired stage commands without writing artifacts.
- Two additional real Lean tests invoke the public CLI as subprocesses for existing-sorry
  completion and proof simplification: begin → propose → review → failed attempt → passing
  attempt → apply → check-file → status. They verify preservation of surrounding source,
  refusal of `sorry`, durable task reports, and absence of legacy stage artifacts.
- The old user-facing demo and batch skills/agents were removed. Example data needed by
  regression tests lives under `tests/fixtures/legacy`; the old CLI is an internal module
  used explicitly by legacy tests, not a route in the public entry point.

These tests validate mechanics. Their fixture semantic reviews are not evidence of model
fidelity, and their fixture tactics are not evidence of agent proof-solving performance.

## Live validation remains pending

Installed CLI versions inspected: Claude Code 2.1.270 and Codex CLI 0.154.0.
A bounded Claude proof-worker smoke test was attempted and interrupted without a model
response (reported API usage and cost were zero). Codex CLI could not initialize inside
the filesystem sandbox. Automatic approval review rejected the escalated live test because
it would use the existing login and transmit project-specific role instructions externally.
No cross-host live success or installed-hook activation is claimed.

Before release, run the following in **each host**, on disposable projects, recording the
host/model version, prompt, task JSON, output diff, check results, human intervention, and
available runtime/usage metrics:

| Scenario | Required observation |
| --- | --- |
| Formalize a source statement using an existing lemma | Separate formalizer and reviewer; accepted source fidelity; Lean-checked proof |
| Complete an unfinished theorem | Only the selected range changes; independent acceptance succeeds |
| Simplify an existing proof | Original statement and definitions preserved; resulting proof checks |
| Deliberately weaken a source statement | Reviewer returns divergent; no proof application |
| Give an unresolved or false statement | Explicit unfinished/needs-review outcome; canonical file preserved |

Use the same tasks and host/model settings without the plugin for a comparison. Do not
publish speed, cost, or quality improvements until measured. Personal installation, hook
trust, public distribution, and external-user pilots are not performed by the test suite.
