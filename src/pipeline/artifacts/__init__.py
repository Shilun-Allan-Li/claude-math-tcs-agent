"""Typed artifacts and their storage.

``models`` holds the schemas — pydantic, ``extra="forbid"``, validated on read as well as
on write. ``store`` persists them as JSONL, one artifact per line, sorted keys, atomic
replace. Both halves exist so that an artifact on disk is reviewable in a terminal and
diffable in git.
"""

from pipeline.artifacts.store import COLLECTIONS, ArtifactStore, StoreError

__all__ = ["ArtifactStore", "StoreError", "COLLECTIONS"]
