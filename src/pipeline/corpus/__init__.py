"""Corpus configuration, stable identity, and the registry.

The registry is the project's addressable state: an index over declarations, the corpus
graph, the notation table, and the Lean-name write barrier that makes registering a name
able to *fail*.
"""

from pipeline.corpus.registry import CorpusRegistry, NameCollisionError, RegistryError

__all__ = ["CorpusRegistry", "NameCollisionError", "RegistryError"]
