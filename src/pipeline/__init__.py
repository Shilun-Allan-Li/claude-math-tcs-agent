"""A reproducible pipeline from mathematical source text to verified Lean.

The public surface is :class:`pipeline.api.Pipeline`. Everything else is an
implementation detail that may move; import from here or from ``pipeline.api``.

    from pipeline import Pipeline
    api = Pipeline("data", corpus=...)          # any configured corpus
    api.dependencies(...)                       # a declaration id from that corpus

Subpackages, in the order the pipeline uses them:

``pipeline.corpus``       corpus config, stable declaration identity, the registry
``pipeline.artifacts``    typed schemas and the JSONL artifact store
``pipeline.graph``        CorpusGraph: typed edges, provenance, deterministic queries
``pipeline.stages``       ingest, annotate, formalize, scaffold, prove
``pipeline.context``      bounded context builders (graph queries, never transcripts)
``pipeline.agents``       executable workers; prompts live in ``prompts/``
``pipeline.checkers``     Lean integrity, source fidelity, library context, sanity
``pipeline.lean``         lake build, ``#print axioms``, ``.ilean`` reading
``pipeline.orchestrator`` stage runner and run state
``pipeline.providers``    model provider adapters
"""

from pipeline.api import Pipeline, list_corpora

__all__ = ["Pipeline", "list_corpora", "__version__"]
__version__ = "0.1.0"
