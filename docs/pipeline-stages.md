# Pipeline stages

Each stage is a typed transformation over persisted artifacts. Model-backed stages load a
versioned prompt; deterministic stages consult no model at all.

| # | stage | in → out | model? | command |
|---|---|---|---|---|
| 0a | ingest-pdf | PDF → Markdown + manifest | yes (per page) | `pipeline ingest-pdf` |
| 0 | ingest | Markdown → `SourceItem` + cross-reference edges | **no** | `pipeline ingest` |
| 1 | annotate | `SourceItem` + context → `AnnotatedDeclaration` | yes | `pipeline annotate` |
| 2 | formalize | `AnnotatedDeclaration` + context → `FormalizationProposal` | yes | `pipeline formalize` |
| 2b | scaffold | proposals → a compilable Lean module | **no** | `pipeline scaffold` |
| 3 | check | source + annotation + proposal → `CheckerFinding[]` | 3 of 4 | `pipeline check-all` |
| — | review | findings + risk → `ReviewDecision` | **human** | `pipeline review` |
| 4 | prove | approved statement + context → `ProofAttempt` | yes | `pipeline prove` |
| 5 | verify | Lean build + `#print axioms` → `TrustStatus` | **no** | `pipeline check` |

---

## 0. Ingest — deterministic

Markdown becomes `SourceDocument`, `SourceChapter`, a set of `SourceItem`, and the
cross-reference edges the source itself states.

Nothing here calls a model. A printed label, the section it sits under, and the page
marker above it are all mechanically recoverable, and the earlier effort measured what
happens when they are left to an agent instead: raw chapters carried 9–24 `<!-- p.NNN -->`
markers each and the annotated chapters carried **zero**. Page provenance died at the
annotation boundary.

Cross-references are extracted by regex — "by theorem 1.2" becomes a typed edge with
`source_extracted` provenance, exact enough to gate on. No model is asked.

**Output:** `source-items.jsonl`, `edges.jsonl`, `declarations.jsonl`

## 1. Annotate — model

One section in, an `AnnotatedDeclaration` per item out. The agent annotates; the program
assigns identity.

The load-bearing field is `stated_hypotheses`: every condition the source requires,
*including* ones stated once at the top of a section and inherited silently. A statement
formalized without one of these is not merely unproved — it is false, and it compiles.

For items the source does not number (definitions in running prose), the agent must return
a **verbatim quote**, which the program locates in the source to derive the span, the page
and the ordinal. A paraphrase is rejected. Identity therefore never depends on model
wording.

The annotator may not write Lean. Enforced by rejecting any response whose fields contain
tactic syntax.

**Prompt:** `prompts/annotate/chapter/v1.md`
**Output:** `annotations.jsonl`, informal dependency edges (`agent_inferred` — proposals)

## 2. Formalize — model

One annotation in, one `FormalizationProposal` out. **Statements only.**

Four enforcement points, in code rather than in the prompt:

- a theorem-like proposal whose body is not exactly `sorry` is rejected;
- `sorry_kind` must agree with the declaration kind — an unfinished *object* is not an
  unfinished *proof*;
- an unfinished construction always carries a blocking design warning;
- the proposed Lean name is claimed in the registry, which **fails** on collision.

That last one matters: twelve names were defined in more than one chapter of the earlier
corpus because twelve chapter-parallel runs shared no state, and the result was a library
with no aggregator module that could not be written.

Every divergence from the source is recorded as a `SourceLeanMapping` with a mapping type,
a semantic status and a justification. An unrecorded divergence is the failure this stage
exists to prevent.

**Prompt:** `prompts/formalize/declaration/v1.md`
**Output:** `proposals.jsonl`, name claims

## 3. Check — three model, one deterministic

| checker | question | model? |
|---|---|---|
| Lean integrity | does it compile, and what does `#print axioms` say? | no |
| Source fidelity | does the Lean say what the source says? | yes |
| Library context | does this need to exist, in this form? | yes |
| Semantic sanity | is it vacuous or false at a degenerate instantiation? | yes |

Checkers 2–4 are hybrids: a deterministic pre-pass decides what a program can decide
exactly, then a model handles the judgement that remains. The deterministic halves catch
the failures that cost the most — dropped hypotheses, registry collisions, missing
cardinality bounds — without asking anyone.

Findings are typed, severity-ranked, and carry evidence. They are never collapsed into a
summary paragraph.

**Prompts:** `prompts/check-source/`, `check-library/`, `check-semantic/`
**Output:** `findings.jsonl`, `TrustStatus` on each record, Lean dependency edges

## Review — human

A hard stop. `pipeline queue` ranks by risk: checker severity, source-fidelity concerns,
foundational role, reverse-dependency count, trust state. `pipeline review <id> <decision>`
records the decision and reports what it unblocks.

Rule 8: an agent may add findings but may never overwrite a human decision. `agent_status`
and `human_decision` are separate fields, and a standing human decision always wins. If
the artifact changes afterwards the decision is marked **stale** rather than silently kept.

**Output:** `reviews.jsonl`

## 4. Prove — model

Only approved statements. The worker receives an immutable statement and a fingerprint
pinning it; if it becomes convinced the statement is wrong its only legal move is
`STATEMENT_REVIEW_REQUIRED`, not a quiet edit.

Attempts are recorded whether they succeed or fail — especially when they fail. A failed
attempt carries its diagnostics, resulting goals, retrieved declarations and a failure
class, because those traces are the training data for a better prover.

A proof is assembled in `ProofScratch.lean`, never in the canonical module, so a failed
attempt cannot leave the corpus broken.

**Prompt:** `prompts/prove/declaration/v1.md`, repair via `prompts/repair/declaration/v1.md`
**Output:** `proof-attempts.jsonl`, an accepted proof stored on the record

## 5. Verify — deterministic

`lake build`, then `#print axioms` per declaration. The verdict is `TrustStatus`, and it is
Lean's, not a model's. Re-running `pipeline scaffold` re-renders the module with accepted
proofs; `pipeline check <module>` recomputes trust.

**Output:** `TrustStatus`, Lean dependency edges, integrity findings

---

## Running a whole division

```bash
pipeline run start dn-ch1-thm-1.1 --run-id demo --stop-after CHECKED \
    --fixtures examples/demo-corpus/fixtures --fixture-division .
pipeline run status demo --events
pipeline run resume demo --stop-after CHECKED
```

The orchestrator drives stages in dependency order, stops at the configured gate, and
records every transition. `resume` reconstructs from disk: no conversation is carried, and
completed stages do not rerun.
