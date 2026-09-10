"""Artifact store: typed collections persisted as human-inspectable JSON/JSONL.

Design choices and why:

* **JSONL, one artifact per line, sorted keys.** Reviewable in a terminal, diffable in
  git, greppable. The forensic pass itself was only possible because the summer's
  evidence was flat JSONL.
* **Atomic writes** (``.tmp`` then ``os.replace``). Lifted from
  ``tcslib/proofmatch/artifacts.py``, which is the one piece of summer infrastructure
  that never corrupted an artifact.
* **Validation on read, not just on write.** A file edited by hand -- which will happen,
  because these are meant to be inspectable -- must fail loudly rather than load a
  half-valid record.
* **No database.** Milestone 2 explicitly asks for the simplest representation that
  supports the queries. Chapters 1-3 are 86 declarations; the whole book is a few hundred.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pipeline.artifacts.models import (
    AnnotatedDeclaration,
    CheckerFinding,
    ContextPackage,
    DeclarationRecord,
    DependencyEdge,
    FormalizationProposal,
    ProofAttempt,
    ReviewDecision,
    SourceChapter,
    SourceDocument,
    SourceItem,
    StageRun,
)

T = TypeVar("T", bound=BaseModel)

__all__ = ["ArtifactStore", "StoreError", "COLLECTIONS", "content_key"]


class StoreError(RuntimeError):
    """Raised when a stored artifact cannot be read back as its declared type."""


#: collection name -> (model, filename, key attribute)
COLLECTIONS: dict[str, tuple[type[BaseModel], str, str]] = {
    "documents": (SourceDocument, "documents.jsonl", "id"),
    "chapters": (SourceChapter, "chapters.jsonl", "id"),
    "items": (SourceItem, "source-items.jsonl", "id"),
    "annotations": (AnnotatedDeclaration, "annotations.jsonl", "declaration_id"),
    "proposals": (FormalizationProposal, "proposals.jsonl", "id"),
    "declarations": (DeclarationRecord, "declarations.jsonl", "id"),
    "edges": (DependencyEdge, "edges.jsonl", None),  # composite key
    "findings": (CheckerFinding, "findings.jsonl", "id"),
    "reviews": (ReviewDecision, "reviews.jsonl", "id"),
    "context": (ContextPackage, "context-packages.jsonl", "id"),
    "attempts": (ProofAttempt, "proof-attempts.jsonl", "id"),
    "runs": (StageRun, "runs.jsonl", "id"),
}


def _strip_timestamps(value: object) -> object:
    """Recursively drop ``created_at`` so two runs can be compared on content alone."""
    if isinstance(value, dict):
        return {k: _strip_timestamps(v) for k, v in value.items() if k != "created_at"}
    if isinstance(value, list):
        return [_strip_timestamps(v) for v in value]
    return value


def content_key(model: BaseModel) -> str:
    """Identity of an artifact's *content*, ignoring when it was produced.

    A deterministic stage re-run produces identical content with a fresh timestamp. If
    the store rewrote the row anyway, every re-run would show up as a diff and artifact
    review would drown in noise. Comparing on this key makes a no-op run a no-op on disk.
    """
    return json.dumps(
        _strip_timestamps(model.model_dump(mode="json")),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _dump(model: BaseModel) -> str:
    """Serialise one artifact to a single deterministic JSON line."""
    return json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


class ArtifactStore:
    """A directory of artifact collections for one corpus."""

    def __init__(self, root: str | Path, corpus: str = "default") -> None:
        self.root = Path(root)
        self.corpus = corpus
        self.directory = self.root / corpus
        self._cache: dict[str, list[BaseModel]] = {}
        # Content keys captured when a collection was last read or written. Compared
        # against on upsert so that mutating an object obtained from the cache and
        # writing it back is detected -- without this the object would be compared
        # against itself and the write silently skipped.
        self._snapshot: dict[str, dict[int, str]] = {}

    # ------------------------------------------------------------------ paths

    def path(self, collection: str) -> Path:
        if collection not in COLLECTIONS:
            raise StoreError(f"unknown collection {collection!r}")
        return self.directory / COLLECTIONS[collection][1]

    def ensure(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------- read

    def read(self, collection: str, *, use_cache: bool = True) -> list[BaseModel]:
        if use_cache and collection in self._cache:
            return self._cache[collection]
        model_cls, _, _ = COLLECTIONS[collection]
        target = self.path(collection)
        out: list[BaseModel] = []
        if target.exists():
            with target.open(encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(model_cls.model_validate_json(line))
                    except ValidationError as exc:
                        raise StoreError(
                            f"{target}:{lineno} is not a valid {model_cls.__name__}: {exc}"
                        ) from exc
        self._cache[collection] = out
        self._snapshot[collection] = {id(a): content_key(a) for a in out}
        return out

    def iter(self, collection: str) -> Iterator[BaseModel]:
        yield from self.read(collection)

    # ------------------------------------------------------------------ write

    def write_all(self, collection: str, artifacts: Iterable[BaseModel]) -> Path:
        """Replace a collection atomically."""
        model_cls, _, _ = COLLECTIONS[collection]
        items = list(artifacts)
        for a in items:
            if not isinstance(a, model_cls):
                raise StoreError(
                    f"collection {collection!r} holds {model_cls.__name__}, got {type(a).__name__}"
                )
        self.ensure()
        target = self.path(collection)
        tmp = target.with_suffix(target.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for a in items:
                fh.write(_dump(a) + "\n")
        os.replace(tmp, target)
        self._cache[collection] = items
        self._snapshot[collection] = {id(a): content_key(a) for a in items}
        return target

    def upsert(self, collection: str, artifacts: Iterable[BaseModel]) -> Path:
        """Insert or replace by key, preserving the order of existing entries.

        Never a blind append: re-running a stage must converge, not accumulate duplicates.
        Report 00 §B5 is the counter-example -- the summer's extraction skipped existing
        outputs entirely, so a changed prompt silently produced nothing.
        """
        _, _, key_attr = COLLECTIONS[collection]
        incoming = list(artifacts)
        if key_attr is None:
            return self._upsert_edges(incoming)

        existing = list(self.read(collection))
        index = {getattr(a, key_attr): i for i, a in enumerate(existing)}
        changed = False
        for art in incoming:
            key = getattr(art, key_attr)
            if key in index:
                current = existing[index[key]]
                # Compare against the snapshot taken when the collection was loaded, not
                # against the live object: `current` and `art` may be the same object.
                stored = self._snapshot.get(collection, {}).get(id(current))
                if stored is not None and stored == content_key(art):
                    continue  # identical content; keep the original timestamp
                existing[index[key]] = art
                changed = True
            else:
                index[key] = len(existing)
                existing.append(art)
                changed = True
        if not changed and self.path(collection).exists():
            return self.path(collection)
        return self.write_all(collection, existing)

    def _upsert_edges(self, incoming: list[BaseModel]) -> Path:
        existing = list(self.read("edges"))
        index = {e.key: i for i, e in enumerate(existing)}  # type: ignore[attr-defined]
        for edge in incoming:
            k = edge.key  # type: ignore[attr-defined]
            if k in index:
                existing[index[k]] = edge
            else:
                index[k] = len(existing)
                existing.append(edge)
        return self.write_all("edges", existing)

    def append(self, collection: str, artifact: BaseModel) -> Path:
        """Append-only collections: runs, proof attempts, review decisions."""
        return self.upsert(collection, [artifact])

    # --------------------------------------------------------------- lookup

    def get(self, collection: str, key: str) -> BaseModel | None:
        _, _, key_attr = COLLECTIONS[collection]
        if key_attr is None:
            raise StoreError(f"collection {collection!r} has no single-field key")
        for art in self.read(collection):
            if getattr(art, key_attr) == key:
                return art
        return None

    def invalidate(self, collection: str | None = None) -> None:
        if collection is None:
            self._cache.clear()
            self._snapshot.clear()
        else:
            self._cache.pop(collection, None)
            self._snapshot.pop(collection, None)

    def summary(self) -> dict[str, int]:
        return {name: len(self.read(name)) for name in COLLECTIONS if self.path(name).exists()}
