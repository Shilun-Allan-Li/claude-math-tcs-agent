# math-tcs-pipeline

A reproducible pipeline from mathematical source text to verified Lean 4, with
provenance preserved at every stage.

```
source text ─▶ annotated declaration IR ─▶ Lean statement ─▶ checkers ─▶ human review ─▶ proof ─▶ verified Lean
                              │                                                │
                              └──────────────── CorpusGraph ───────────────────┘
```

---

## Motivation

Formalizing a mathematics textbook with LLM agents is not hard because the mathematics is
hard. It is hard because the *bookkeeping* fails silently. This pipeline is a response to a
forensic study of an earlier effort in which:

- five theorems were formalized **false** — each missing a hypothesis stated once in
  surrounding prose and never carried into the Lean statement, so each compiled, elaborated,
  and was wrong in a way no Lean tooling could see;
- twelve declarations were written, proved, then deleted as exact Mathlib duplicates,
  ten of them from the one chapter that skipped the library survey;
- thirteen `def f := sorry` constants made 18+ theorems **vacuous** rather than merely
  unproved, because an unfinished object was recorded the same way as an unfinished proof;
- 176 of 226 declarations were cited only inside another declaration's docstring, so the
  informal dependency graph and the Lean dependency graph never met;
- one commit shipped 29 proved theorems under a message asserting "every proof body is
  `sorry`", and nothing checked.

Every one of those is a *provenance* failure, not a reasoning failure. The design here
follows from that diagnosis.

### Eight load-bearing rules

Each is enforced somewhere in code, not asserted in a prompt.

| # | Rule | Enforced by |
|---|---|---|
| 1 | Stages consume artifacts, not conversation history | every stage signature; `ContextPackage` |
| 2 | One stable identity from source to verified Lean | `pipeline.corpus.ids` — source-derived, never LLM-derived |
| 3 | Source identity is preserved, never replaced | `SourceItem` and `LeanFacet` coexist; `SourceLeanMapping` records every difference |
| 4 | Context comes from the graph, bounded | `ContextPackage`, built by query |
| 5 | Lean is authoritative for Lean facts | `TrustStatus` from `#print axioms`; deterministic checkers report confidence 1.0 |
| 6 | Formalization is not proving | `sorry_kind`; `classify_body` rejects proof bodies |
| 7 | Proof workers cannot change approved statements | `approved_statement_fingerprint`; `STATEMENT_REVIEW_REQUIRED` |
| 8 | Human review decisions are persistent | `ReviewState.human_decision`, separate from `agent_status` |

### Why annotation and formalization are separate

Annotation reads the source and produces a typed IR **in the source's own vocabulary** —
every stated hypothesis, the conclusion, the informal proof steps, the terminology, the
notation, the open questions. It writes no Lean.

Formalization reads that IR and produces a Lean *statement*. It writes no proof.

Fusing them is what loses hypotheses. A single agent asked to read prose and emit Lean
optimises for producing something that elaborates, and a hypothesis stated a paragraph
earlier is exactly what gets dropped — silently, because the result still compiles. Making
`stated_hypotheses` a required field of a separate artifact means a dropped hypothesis is a
diff between two persisted records rather than an absence nobody can see.

### Why statements are checked before proof

A proof of the wrong theorem is worth less than no proof at all, and costs far more to
discover. So the statement is checked — against the source, against the library, against
degenerate cases — and approved by a human *before* any proof effort is spent. The proof
worker then receives an immutable statement and a fingerprint pinning it; if it becomes
convinced the statement is wrong its only legal move is `STATEMENT_REVIEW_REQUIRED`, not a
quiet edit.

Four checkers, each answering one question:

1. **Lean integrity** — deterministic. Does it compile, and what does `#print axioms` say?
2. **Source fidelity** — does the Lean statement say what the source says?
3. **Library context** — does this declaration need to exist, in this form?
4. **Semantic sanity** — is it vacuous or false at a degenerate instantiation?

### Why artifacts replace long conversational context

Every stage boundary is a validated artifact on disk. No stage receives a transcript, and
no stage *can*: the signatures take a registry and a declaration id.

This buys three things a conversation cannot. Runs are **resumable** — a fresh process
reconstructs state from artifacts alone. Context is **bounded and auditable** — each agent
input is a `ContextPackage` recording what was retrieved and why, so "what did the agent
actually see?" is answerable months later. And stages are **independently replayable** —
re-running one stage against recorded provider responses is how the test suite runs offline.

The measured problem: the earlier effort's scaffold stage read whole chapters (up to 3,356
lines) and its proof loop read a whole 1,573-line Lean file to emit at most thirty tactic
lines. A formalization package here is ~12,000 characters, assembled by graph query.

### What CorpusGraph does

One persisted, typed, deterministic dependency graph — no model involved, and none could
help. Nodes are declarations; edges carry a type and **structured provenance**: which kind
of evidence, which component asserted it, which artifact it came from.

That last part matters. In the demo corpus, `dn-ch1-thm-1.3` depends on `dn-ch1-thm-1.2`
three times over, and the graph says why each:

```
→ dn-ch1-thm-1.2   [source_cross_reference]  source_extracted / cross_references/v1
                   evidence: dn-ch1-thm-1.3 proof: 'theorem 1.2'
→ dn-ch1-thm-1.2   [informal_dependency]     agent_inferred   / annotate/v1
                   evidence: annotation for dn-ch1-thm-1.3 references 'theorem 1.2'
→ dn-ch1-thm-1.2   [lean_local_dependency]   lean_extracted   / lean_integrity/v1
                   evidence: DemoNaturals.ilean: DemoNaturals.divides_add_add
                             references DemoNaturals.divides_add
```

Only source-extracted, Lean-extracted and human-confirmed edges may gate progression; an
agent-inferred edge is a proposal until confirmed.

Three consumers share it: the **context builder** retrieves prerequisites through it, the
**proof scheduler** decides eligibility from it, and a **UI client** renders it. All three
call the same query API.

---

## Installation

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

Pure Python, no native dependencies. Lean and poppler are optional and needed only for
specific stages — see [Current limitations](#current-limitations).

## Configuration

`pipeline.toml` is optional. With no file, the pipeline uses the first agent CLI it finds
on `PATH`, authenticating against a subscription you already have:

```bash
pipeline providers        # what is available here, and what each option needs
```

| you have | install | adapter |
|---|---|---|
| a Claude subscription | [Claude Code](https://claude.com/claude-code), then `claude` once | `claude-cli` |
| a ChatGPT subscription | the Codex CLI, then `codex login` | `codex-cli` |
| an Anthropic API key | `uv pip install -e '.[anthropic]'`, `export ANTHROPIC_API_KEY=…` | `anthropic` |

Environment overrides the file: `PIPELINE_PROVIDER`, `PIPELINE_MODEL`, and per-stage
`PIPELINE_PROVIDER_ANNOTATE`, `PIPELINE_MODEL_PROVE`, …

## Quick demo

**No model call, no network, no Lean.** Committed artifacts from a real pipeline run:

```bash
pipeline demo
```

```
  corpus      demo-naturals   6 declarations
  artifacts   /tmp/pipeline-demo
  graph       6 nodes, 8 edges, 7 gating

  declaration           kind        lean name                       trust             review
  dn-ch1-def-1.1-1      definition  DemoNaturals.Divides            FULLY_VERIFIED    NEEDS_HUMAN
  dn-ch1-ex-1.2.1       exercise    -                               UNKNOWN           UNREVIEWED
  dn-ch1-ex-1.2.2       exercise    -                               UNKNOWN           UNREVIEWED
  dn-ch1-thm-1.1        theorem     DemoNaturals.divides_trans      FULLY_VERIFIED    APPROVED
  dn-ch1-thm-1.2        theorem     DemoNaturals.divides_add        DIRECT_SORRY      NEEDS_HUMAN
  dn-ch1-thm-1.3        theorem     DemoNaturals.divides_add_add    TRANSITIVE_SORRY  NEEDS_HUMAN
```

`divides_add_add` is the case worth looking at: its body contains no `sorry`, it elaborates
cleanly, and it is **not proved** — it reaches `sorryAx` through a dependency. Only
`#print axioms` sees that, which is why it and not a text scan decides trust.

Then investigate:

`pipeline demo` materialises the artifacts into their own store, so the follow-ups have to
be pointed at it — the command prints these with the flag already filled in:

```bash
D=/tmp/pipeline-demo
pipeline --data-dir $D inspect dn-ch1-thm-1.3     # source, annotation, Lean, mappings, findings
pipeline --data-dir $D graph deps dn-ch1-thm-1.3  # what it depends on
pipeline --data-dir $D graph node dn-ch1-thm-1.3  # every edge, with provenance and evidence
pipeline --data-dir $D graph stats                # node/edge counts by type and provenance
pipeline --data-dir $D graph unresolved           # citations that resolve to nothing
pipeline --data-dir $D review dn-ch1-thm-1.2 APPROVED --reviewer you --rationale "…"
```

To execute the pipeline for real, replaying recorded provider responses so it costs nothing:

```bash
pipeline --corpus demo-naturals ingest 1
pipeline --corpus demo-naturals annotate 1 --fixtures examples/demo-corpus/fixtures/annotate
pipeline --corpus demo-naturals formalize dn-ch1-thm-1.1 --fixtures examples/demo-corpus/fixtures/formalize
```

Drop `--fixtures` to call a real provider.

## Pipeline stages

| # | stage | in → out | model? |
|---|---|---|---|
| 0 | **ingest** | Markdown → `SourceItem` + cross-reference edges | no |
| 1 | **annotate** | `SourceItem` + context → `AnnotatedDeclaration` | yes |
| 2 | **formalize** | `AnnotatedDeclaration` + context → `FormalizationProposal` | yes |
| 2b | **scaffold** | proposals → a compilable Lean module | no |
| 3 | **check** | source + annotation + proposal → `CheckerFinding[]` | 3 of 4 |
| — | **review** | findings + risk → `ReviewDecision` | human |
| 4 | **prove** | approved statement + context → `ProofAttempt` | yes |
| 5 | **verify** | Lean build + `#print axioms` → `TrustStatus` | no |

Details in [docs/pipeline-stages.md](docs/pipeline-stages.md); the reasoning behind the
shape is in [docs/architecture.md](docs/architecture.md).

## Repository layout

```
src/pipeline/
  api.py            the stable programmatic interface — a UI is just another consumer
  cli.py            argument parsing and formatting only; no business logic
  corpus/           corpus config, stable declaration identity, the registry
  artifacts/        typed schemas (models/) + the JSONL artifact store
  graph/            CorpusGraph: typed edges, provenance, deterministic queries
  stages/           ingest, annotate, formalize, scaffold, prove
  context/          bounded context builders — graph queries, never transcripts
  agents/           executable workers (code)
  checkers/         the four checkers and their orchestrator
  lean/             lake build, #print axioms, .ilean reading
  orchestrator/     stage runner, run state, resume
  providers/        model provider adapters and offline test doubles
prompts/            versioned prompts, <stage>/<name>/v<N>.md — resources, never code
corpora/            one config per corpus
examples/demo-corpus/
  source/           the demo Markdown
  fixtures/         recorded provider responses
  artifacts/        committed pipeline output — what `pipeline demo` opens
  lean/             the Lean module the demo scaffolds into
schemas/            JSON Schema generated from the pydantic models
tests/unit/         fast, isolated
tests/integration/  several stages end to end; test_corpus_agnostic.py mounts a
                    second corpus from outside the repo and re-checks the engine on it
```

**Agents are code; prompts are resources.** An agent receives typed input, builds context
by graph query, loads a versioned prompt file, invokes a provider, parses, validates
against a schema, persists, and returns a typed artifact. No instruction text lives in
`src/`, and no prompt can load an artifact or write one. `pipeline agents` prints the table.

## How to add a corpus

One JSON file in `corpora/`. See [docs/adding-a-corpus.md](docs/adding-a-corpus.md).

```json
{
  "corpus": "your-book", "slug": "yb",
  "title": "…", "authors": ["…"],
  "source_type": "book",
  "divisions": [
    {"number": "1", "type": "chapter", "title": "…",
     "markdown": "sources/your-book/01.md",
     "pdf_page_start": 9, "pdf_page_end": 32, "printed_page_offset": 8}
  ]
}
```

Nothing in `src/` should need to change. `tests/integration/test_corpus_agnostic.py` is
the acceptance test: it builds a corpus in a temporary directory, mounts it from outside
the repository, and asserts that identity, extraction, scheduling and the graph all work on
it — and that no module under `src/pipeline/` names a corpus or uses one domain's
vocabulary.

Real corpora are usually copyrighted, so keep them out of the tree entirely:

```bash
export PIPELINE_CORPORA_PATH=~/research/my-corpus     # config + sources live here
pipeline --corpus my-corpus --data-dir ~/research/my-data ingest --all
```

Paths inside a config resolve against the config's own directory first, so a mounted corpus
travels as one self-contained folder. `corpora/` is still searched first and a mounted
config can never shadow one in the repo; `sources/`, `corpora/*` (except the demo) and
`data/` are git-ignored for corpora you do keep in the tree.

## Testing

```bash
pytest                      # everything
pytest tests/unit           # fast
pytest tests/integration    # several stages end to end
pytest -m "not lean"        # skip anything needing a built Mathlib
```

Everything runs offline. Providers and the PDF renderer are injectable, and the demo
fixtures are recorded provider responses.

The three tests marked `lean` are the only ones that shell out to Lean: they run
`lake build` and `#print axioms` against the demo module and check that Lean's own verdict
matches what the committed artifacts record. They skip unless `lake` is on `PATH` **and**
Mathlib is built under `.lake/packages`, since a build failing for want of a library is not
a verdict about the corpus. Tests that only read a recorded verification artifact are
deliberately *not* marked `lean` — marking them so would claim coverage the suite does not
have.

## Current limitations

Stated plainly, because they are the honest boundary of what has been demonstrated.

- **Scale.** The demo corpus is 6 declarations. The largest real run so far is a single
  textbook chapter, ~30 declarations. Nothing here has been run over a whole book.
- **Proof capability is not the contribution.** The proof stage closes short lemmas.
  Anything needing real mathematical work escalates to a human, by design — but that means
  the end-to-end "verified Lean" claim currently holds only for easy targets.
- **The orchestrator has no scaffold stage.** `FORMALIZED → CHECKED` assumes a Lean module
  exists; it is produced out-of-band by `pipeline scaffold`.
- **Scheduling is serial.** `eligible_nodes` returns a dependency-ordered set, but the
  runner takes one at a time. The graph supports parallelism; the executor does not use it.
- **Extraction reads conventions, not arbitrary Markdown.** Labelled declarations, proof
  openers and tombstones are matched by pattern. The common spellings are covered and
  tested (`*Proof*`, `**Proof.**`, `_Proof._`, `□`, `∎`, `\square`), but a source that
  numbers or marks things in a shape the extractor does not know needs a case added to
  `stages/source_items.py` — the one place a new corpus legitimately touches engine code.
- **Annotation's unit of work is a division, not a declaration.** A definition stated in
  running prose has no identity until an annotator quotes it, so annotating one declaration
  annotates its whole section.
- **Lean and poppler are optional but load-bearing where used.** Trust states require a
  built Mathlib (~7 GB). PDF ingestion requires poppler; if you already have Markdown you
  never need it.
- **No network API.** The interface is Python plus a CLI. A UI client would consume
  `pipeline.api.Pipeline` directly or over a thin server yet to be written.
