# Architecture

The system is a sequence of typed transformations over persisted artifacts. Its shape is
a response to a forensic study of an earlier textbook-formalization effort; the failures
that study found are cited here because each one is why some specific piece exists.

## The invariant

> Every mathematical declaration has a reproducible, inspectable, provenance-preserving
> path from source text to verified Lean, with bounded context at every agent stage.

Three words carry the weight.

**Reproducible.** Given the same artifacts and the same prompt version, a stage produces
the same result. Stage outputs are content-addressed and idempotent: re-running converges
rather than accumulating.

**Inspectable.** Every intermediate is a validated record on disk, readable in a terminal
and diffable in git. Nothing important lives only in a model's context window.

**Provenance-preserving.** Every artifact records what produced it, from which input, with
which prompt, against which corpus version. Every graph edge records why the system
believes it exists.

## Why stages, not one agent

A single agent given a chapter and asked for Lean will produce Lean that elaborates. That
is the failure mode, not the goal. The forensic study found five theorems formalized
**false** — each missing a hypothesis stated in prose a paragraph earlier — and each one
compiled, elaborated, and passed every automated check that existed.

Splitting the work makes the loss *visible*:

```
SourceItem              what the book says, verbatim, with a span and a page
    ↓  annotate         (model)  — no Lean, ever
AnnotatedDeclaration    stated_hypotheses, conclusion, proof steps, terminology, questions
    ↓  formalize        (model)  — statements only, proof body must be `sorry`
FormalizationProposal   Lean name, statement, and every source↔Lean mapping it made
    ↓  check            (3 model + 1 deterministic)
CheckerFinding[]        typed, severity-ranked, evidence-carrying
    ↓  review           (human)
ReviewDecision          persistent; an agent may add findings but never overwrite this
    ↓  prove            (model)  — statement immutable, pinned by fingerprint
ProofAttempt            recorded whether it succeeds or fails
    ↓  verify           (Lean)
TrustStatus             from `#print axioms`, never from a model's opinion
```

`stated_hypotheses` is a required field of a separate artifact. A dropped hypothesis is
therefore a diff between two persisted records, not an absence nobody can see.

## The eight rules, and where they live

| # | Rule | Enforced by |
|---|---|---|
| 1 | Stages consume artifacts, not conversation | every stage signature takes `(registry, declaration_id)` |
| 2 | One identity from source to verified Lean | `pipeline.corpus.ids` — derived from label/section, never from model wording |
| 3 | Source identity preserved, never replaced | `SourceItem` and `LeanFacet` coexist; `SourceLeanMapping` records every difference |
| 4 | Context comes from the graph, bounded | `ContextPackage`, built by query, budget recorded |
| 5 | Lean is authoritative for Lean facts | `TrustStatus` from `#print axioms`; deterministic checkers report confidence 1.0 |
| 6 | Formalization is not proving | `classify_body` rejects tactic bodies; `sorry_kind` distinguishes unfinished proof from unfinished object |
| 7 | Proof workers cannot change approved statements | `approved_statement_fingerprint`; `STATEMENT_REVIEW_REQUIRED` is a first-class outcome |
| 8 | Human decisions persist | `ReviewState.human_decision` separate from `agent_status` |

### Rule 2 in detail: why identity is source-derived

Identity comes only from what the *source* fixes — corpus slug, division, item kind, and
either the printed label or the section plus an ordinal. Never from model wording,
generated Lean names, timestamps, or content hashes.

The earlier effort joined every stage by string-matching on a human-written Markdown
heading, and its terminal dataset carried no chapter, section, label, page or document
field at all. The chain back to the book was severed and could not be rebuilt.

Content hashes are a *separate* concept. `content_fingerprint` detects that the text
behind an id changed; identity answers "which theorem is this". Conflating them would make
every re-extraction look like a new declaration.

### Rule 5 in detail: why trust is not a text scan

`whitney_inequalities` in the original corpus — and `divides_add_add` in the demo — is a
term-level assembly of two lemmas. It contains no `sorry`, it elaborates cleanly, and it
is **unproved**. Only `#print axioms` sees that it reaches `sorryAx`.

So `TrustStatus` distinguishes:

| status | meaning |
|---|---|
| `FULLY_VERIFIED` | no `sorryAx` in its axiom set |
| `DIRECT_SORRY` | its own body is `sorry` — unproved |
| `TRANSITIVE_SORRY` | no `sorry` of its own; reaches `sorryAx` through a dependency |
| `UNFINISHED_CONSTRUCTION` | an *object* with no body — statements about it are **vacuous**, not merely open |
| `BLOCKED_BY_UNTRUSTED_DEPENDENCY` | quantifies over such an object |
| `COMPILE_FAILURE` / `UNKNOWN` | did not build / not checked |

The fourth row is the expensive one. Thirteen `def f := sorry` constants made 18+ theorems
vacuous in the earlier corpus, and nothing distinguished them from theorems that were
merely unproved.

## CorpusGraph

One persisted, typed graph. Nodes are declarations; edges are typed and carry structured
provenance. No model is involved at any point, and none could help.

```python
provenance = {
    "kind": "agent_inferred",          # decides whether the edge may gate progression
    "producer": "annotate/v1",         # which component asserted it
    "artifact_id": "dn-ch1-thm-1.3",   # the persisted artifact the claim came from
    "evidence": "annotation for dn-ch1-thm-1.3 references 'theorem 1.2'",
}
```

Edge kinds and what they mean for gating:

| provenance kind | source | may gate? |
|---|---|---|
| `source_extracted` | a regex over the source's own citations | yes |
| `lean_extracted` | the elaborated module's constant references | yes |
| `human_confirmed` | a person said so | yes |
| `agent_inferred` | an annotator read it out of prose | **no** — a proposal until confirmed |

The same dependency is often asserted more than once, by different stages, and each
assertion is separate evidence. In the demo, `dn-ch1-thm-1.3 → dn-ch1-thm-1.2` exists
three times: the source cites it, the annotator infers it, and Lean extracts it.

Lean-extracted edges are a *projection* of a built module, so they are **replaced** on
each check rather than merged. Merging was a real bug: a declaration checked before its
dependencies were formalized kept a dangling `lean:<Name>` placeholder forever and could
never become proof-eligible, silently.

Three consumers, one query API:

```python
graph.dependencies(id)              # what this needs
graph.reverse_dependencies(id)      # what needs this — drives review prioritisation
graph.unresolved_dependencies(known)# citations resolving to nothing
graph.graph_stats()                 # shape, by edge type and provenance
graph.eligible_nodes(completed)     # structural scheduling
```

The **context builder** retrieves prerequisites through it, the **proof scheduler**
decides eligibility from it, and a **UI client** renders it. None of them has a private
copy, and none calls a model to answer a graph question.

## Bounded context

Rule 4 exists because the earlier effort's scaffold stage read whole chapters (up to 3,356
lines) and its proof loop read a whole 1,573-line Lean file to emit at most thirty tactic
lines — while the information actually needed across a chapter boundary was four import
edges, about thirty reusable declarations, and a notation table.

A `ContextPackage` is assembled by **query**, records every item with the reason it was
retrieved, and carries a character budget. It is an artifact, so "what did the agent
actually see?" is answerable months later.

Critically, the proof package must **not grow with attempt number**: failed strategies are
carried as capped labels, never as transcripts. A repair worker that receives the whole
history of its own failures is the growth mode the study measured.

## Agents and prompts

Prompts are versioned Markdown under `prompts/`. Agents are code under
`src/pipeline/agents/`. The separation is enforced by shape: a prompt cannot load an
artifact, query the graph, validate a schema or persist a result.

Every agent runs the same sequence, written once in `Agent.run`:

```
load structured input   ← the artifact store, never a caller's memory
build bounded context   ← a deterministic graph query
load prompt             ← a versioned file on disk
invoke model            ← a provider adapter
parse result
validate schema         ← pydantic, extra="forbid"; a bad reply is a failed run
persist artifact
return typed output
```

`Agent.validate` is called by the base class, so no subclass can skip it.

## Orchestration and run state

`PipelineOrchestrator.step` is the only route into a stage. It adds run-state bookkeeping
and scheduling around the stage functions, and it takes a registry, a run, and a
declaration id — there is no conversation parameter, so a stage cannot come to depend on
one.

Two kinds of state are kept strictly apart:

- **Artifact state** — what the pipeline produced — is authoritative. `derive_stage` reads
  a declaration's stage back out of its artifacts alone.
- **Run state** — which declarations this invocation is driving — is bookkeeping.

On resume, every declaration's stage is recomputed from artifacts and only then is run
bookkeeping replayed. A run record that disagrees with the artifacts loses. That ordering
is what makes `pipeline run resume` trustworthy rather than merely convenient.

Failure is structured: a stage that raises is recorded against the declaration with its
error kind, the run continues with the others, and a re-run retries exactly the failure.
`BLOCKED` is distinguished from `FAILED` — a target naming a prose definition that does
not exist yet is pending, not broken.

## What this architecture does not do

- It does not make proofs easier. The proof stage closes short lemmas; anything needing
  real mathematical work escalates to a human, by design.
- It does not remove the human. The review gate is a hard stop, and rule 8 means an agent
  can never clear it.
- It does not scale-test itself. See *Current limitations* in the README.
