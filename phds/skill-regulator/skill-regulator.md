---
name: skill-regulator
description: Promotion gate for skills authored by skill-creator. This skill should be used when a draft skill needs review for promotion to the active skills/ tree, or when a periodic audit of existing skills is run.
---

# Skill Regulator

The second phds role. The organizer (`skill-creator`) authors; the regulator decides whether the draft ships to `skills/` or stays in draft. Also runs periodic audits of the active skills tree to catch staleness, conflicts, and skills that no proving-agent actually reads.

## Two operating modes

### Mode 1 — Promotion review (per-draft)

**Input.** A draft at `phds/skill-creator/drafts/<skill-name>.md` (or `<skill-name>/` directory for a full package), produced by `skill-creator` from a knowledge_db pack.

**Output.** A decision — `PROMOTE` / `REVISE` / `REJECT` — with a one-line rationale.

- `PROMOTE` → move draft to `skills/<category>/<skill-name>(.md|/)`. Append entry to `phds/skill-regulator/promoted.log`.
- `REVISE` → leave draft in place. Append rationale inline at the top of the draft for skill-creator to act on.
- `REJECT` → move draft to `phds/skill-creator/rejected/<skill-name>(.md|/)`. Append rationale.

### Mode 2 — Periodic audit (whole tree)

Scan `skills/` and flag for review. Output a single report at `phds/skill-regulator/audits/<YYYY-MM-DD>.md` with one decision per flagged skill.

## Promotion gates

A draft promotes only if **all** gates pass. Each gate's failure routes to `REVISE` (fixable upstream) or `REJECT` (not fixable).

### Gate 1 — Capability-multiplier (REJECT if fails)

Apply the **two-check test** from `phds/skill-creator/skill-creator.md` §"The capability-multiplier test":

1. **Behavior delta** — would a proving-agent loaded with this skill behave measurably differently than a vanilla Claude on an in-scope problem?
2. **Transformer-failure-mode mapping** — does the draft explicitly map to one of the seven failure-mode buckets in `skills/README.md`?

Failure modes:

- Skill restates a definition Claude already has from training → REJECT.
- Skill repeats generic advice ("be rigorous", "check assumptions") → REJECT.
- Skill is operational but trivially derivable from the problem statement → REJECT.
- Skill describes a real human-mathematician habit but doesn't map to a transformer failure mode → REJECT (the rule may belong in `knowledge_db/` as reference material; not in `skills/`).

This gate is binary. A skill that fails it should not be revised; it should never have been authored. The rationale on REJECT helps skill-creator avoid the same shape next time.

### Gate 2 — Named consumer (REVISE if fails)

Body must name at least one of: `explorer`, `prover`, `reviewer`, `formatter`. The named consumer must plausibly load this skill at the point of need (e.g., a route-selection skill names `explorer` or `prover`, not `formatter`).

### Gate 3 — Source citation (REVISE if fails)

Body must contain a `Source:` line referencing a pack path under `phds/knowledge_db/`, ideally the specific `INCLUDE` rule the skill operationalizes. Hand-authored skills with no citation are flagged for human review, not silently promoted.

### Gate 4 — Scope tightness (REVISE if fails)

One task pattern per skill. If the draft bundles multiple patterns ("everything about linear algebra"), REVISE — skill-creator must split.

### Gate 5 — Conflict detection (REVISE if fails)

Search existing skills for overlap:

```bash
grep -ri "<task-pattern-keywords>" skills/
```

If an existing skill addresses the same pattern:

- **Substantively duplicate** → REVISE: merge into the existing skill, adding the new source pack as a citation.
- **Contradictory** (different recommended first move for the same pattern) → REVISE: skill-creator must reconcile by reading both source packs and producing a unified rule, or by scoping each rule's preconditions explicitly.

### Gate 6 — Verification (REVISE if fails)

Run the mechanical checks in `phds/skill-creator/skill-creator.md` §Verification. Any failure → REVISE.

## Audit signals (mode 2)

For each skill in `skills/`, check:

- **Stale** — source pack mtime is later than the skill's last edit. The underlying knowledge has updated; the skill may need re-derivation.
- **Orphan** — skill cites a `phds/knowledge_db/` pack that no longer exists.
- **Unused** — skill has not been read by any proving-agent in <window>. Requires read-tracking; if unavailable, this gate is skipped.
- **Duplicate** — two or more skills cover the same task pattern.
- **Drift** — skill cites no source, or cites a path that doesn't resolve.

Each flagged skill gets one of:

- `KEEP` — false positive; audit was conservative.
- `MERGE` — fold into another skill; report names which.
- `RETIRE` — move to `phds/skill-regulator/retired/<skill-name>(.md|/)`. Skills are not deleted; retirement preserves the audit trail and prevents re-authoring of a previously-rejected pattern.
- `REVISE` — return to skill-creator for re-authoring against the current source pack.

## Anti-bloat posture

The regulator's standing bias is **fewer, sharper skills**.

- When a draft is borderline between PROMOTE and REJECT → default to REJECT. The cost of a missing skill is "Claude does what it would have done anyway"; the cost of a noise skill is "Claude loads useless context every time the trigger fires."
- When two skills overlap → prefer merge over coexistence.
- When a draft covers ground similar to a previously-retired skill → check `retired/` before promoting. Do not relitigate a rejected pattern unless the source has materially changed.

## What the regulator does NOT do

- Does not author skills. That's skill-creator's job. If a draft fails a gate, the regulator routes it back; it does not edit in place.
- Does not rewrite `knowledge_db/` packs. If the underlying pack is wrong, the issue is upstream in `distill_mathematicians/`; the regulator surfaces the problem but does not patch downstream artifacts.
- Does not auto-promote on partial gate-pass. All gates are required.
- Does not touch `claude_prover/`. Same rule as everywhere else in the backend.

## Filesystem layout used by the regulator

```
phds/
  skill-creator/
    drafts/            # in-flight drafts (regulator reads from here)
    rejected/          # REJECTed drafts with appended rationale (audit trail)
  skill-regulator/
    skill-regulator.md # this file
    promoted.log       # one-line entry per PROMOTE
    audits/            # YYYY-MM-DD.md reports from mode 2
    retired/           # RETIREd skills (audit trail)
```

These directories are created on first use; do not pre-scaffold them empty.

## Termination

**Promotion review** ends in exactly one of:

- `PROMOTE` — skill at final path under `skills/`; entry in `promoted.log`.
- `REVISE` — draft stays at `phds/skill-creator/drafts/`, rationale appended inline.
- `REJECT` — draft at `phds/skill-creator/rejected/`, rationale appended.

**Audit run** ends with the report at `phds/skill-regulator/audits/<YYYY-MM-DD>.md`. Decisions in the report are advisory until acted on — by skill-creator (for `REVISE`) or by the regulator itself (for `MERGE` and `RETIRE`).
