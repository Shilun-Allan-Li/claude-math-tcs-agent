"""CorpusGraph: the executable dependency subsystem.

Nodes, typed edges, structured provenance, persistence and a deterministic query API.
Nothing here calls a model, and nothing here could benefit from one — it is ordinary
graph code over persisted edges, which is the point.
"""

from pipeline.graph.corpus_graph import (
    LIBRARY_PREFIX,
    MATHLIB_PREFIX,
    CorpusGraph,
    DependencyGraph,
    is_library_node,
    is_mathlib_node,
)

__all__ = ["CorpusGraph", "DependencyGraph", "MATHLIB_PREFIX", "LIBRARY_PREFIX",
           "is_mathlib_node", "is_library_node"]
