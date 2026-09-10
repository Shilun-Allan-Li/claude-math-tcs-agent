"""The corpus registry: the project's addressable state.

Its defining property is that **registering a Lean name can fail.** In the earlier effort
twelve declaration names were each defined in more than one division -- one of them in five
-- because a dozen division-parallel agent runs shared no state. The corpus that resulted
had no module that could import all of its parts at once, and none could be written for it
afterwards. A single write barrier prevents the whole class of collision.

The registry serves the three consumers of the graph -- context retrieval, UI clients, and
proof scheduling -- and is the only thing any stage needs from "everything that came
before". It is deliberately small: notation, conventions, claimed names, and an index
over declarations. Nothing here carries prose.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from pipeline.artifacts.models import (
    THEOREM_LIKE,
    DeclarationRecord,
    DependencyEdge,
    EdgeType,
    NotationEntry,
    ReviewStatus,
    SourceItemKind,
    TrustStatus,
)
import re

from pipeline.graph.corpus_graph import CorpusGraph, is_library_node, is_mathlib_node
from pipeline.artifacts.store import ArtifactStore

__all__ = ["CorpusRegistry", "NameCollisionError", "RegistryError"]


#: A trailing part letter on an otherwise numeric label: "...-2.3.1a" -> "...-2.3.1".
PART_SUFFIX_RE = re.compile(r"(?<=\d)[a-z]$")


class RegistryError(RuntimeError):
    pass


class NameCollisionError(RegistryError):
    """Raised when a Lean name is claimed twice.

    This is the write barrier. It is an error, not a warning, and not a discovery made
    months later by a triage pass.
    """

    def __init__(self, name: str, owner: str, claimant: str) -> None:
        super().__init__(
            f"Lean name {name!r} is already claimed by {owner!r}; {claimant!r} cannot "
            f"claim it. Reuse the existing declaration, or choose a different name."
        )
        self.name = name
        self.owner = owner
        self.claimant = claimant


class CorpusRegistry:
    """Index + graph + name claims over one corpus's artifact store."""

    REGISTRY_FILE = "registry.json"

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        self._records: dict[str, DeclarationRecord] = {}
        self._graph = CorpusGraph()
        self._notation: dict[str, NotationEntry] = {}
        self._conventions: dict[str, str] = {}
        self._name_claims: dict[str, str] = {}  # lean_name -> declaration_id
        self._version = 0
        self._loaded = False

    # --------------------------------------------------------------- lifecycle

    @classmethod
    def load(cls, store: ArtifactStore) -> CorpusRegistry:
        reg = cls(store)
        reg.reload()
        return reg

    def reload(self) -> CorpusRegistry:
        self.store.invalidate()
        self._records = {r.id: r for r in self.store.read("declarations")}  # type: ignore[misc]
        self._graph = CorpusGraph(self.store.read("edges"))  # type: ignore[arg-type]
        self._load_registry_file()
        self._rebuild_name_claims()
        self._loaded = True
        return self

    def _registry_path(self) -> Path:
        return self.store.directory / self.REGISTRY_FILE

    def _load_registry_file(self) -> None:
        path = self._registry_path()
        if not path.exists():
            self._notation, self._conventions, self._version = {}, {}, 0
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self._notation = {
            k: NotationEntry.model_validate(v) for k, v in data.get("notation", {}).items()
        }
        self._conventions = dict(data.get("conventions", {}))
        self._version = int(data.get("version", 0))

    def save(self) -> Path:
        """Persist notation, conventions and the version counter."""
        self.store.ensure()
        payload = {
            "version": self._version,
            "notation": {k: v.model_dump(mode="json") for k, v in sorted(self._notation.items())},
            "conventions": dict(sorted(self._conventions.items())),
        }
        path = self._registry_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return path

    @property
    def version(self) -> int:
        """Bumped on every mutation. Context packages record it to detect staleness."""
        return self._version

    def _bump(self) -> None:
        self._version += 1

    # ------------------------------------------------------------ name claims

    def _rebuild_name_claims(self) -> None:
        self._name_claims = {}
        for record in self._records.values():
            if record.lean.name:
                owner = self._name_claims.get(record.lean.name)
                if owner is not None and owner != record.id:
                    raise NameCollisionError(record.lean.name, owner, record.id)
                self._name_claims[record.lean.name] = record.id

    def claim_lean_name(self, name: str, declaration_id: str) -> None:
        """Claim a fully-qualified Lean name for a declaration.

        Idempotent for the same owner, fatal for a different one.
        """
        owner = self._name_claims.get(name)
        if owner is not None and owner != declaration_id:
            raise NameCollisionError(name, owner, declaration_id)
        self._name_claims[name] = declaration_id
        self._bump()

    def name_owner(self, name: str) -> str | None:
        return self._name_claims.get(name)

    def claimed_names(self) -> dict[str, str]:
        return dict(self._name_claims)

    # ------------------------------------------------------------- mutation

    def upsert_records(self, records: Iterable[DeclarationRecord], *, persist: bool = True) -> int:
        """Add or replace declarations, enforcing the name barrier before writing."""
        incoming = list(records)
        for record in incoming:
            if record.lean.name:
                owner = self._name_claims.get(record.lean.name)
                if owner is not None and owner != record.id:
                    raise NameCollisionError(record.lean.name, owner, record.id)
        for record in incoming:
            self._records[record.id] = record
            if record.lean.name:
                self._name_claims[record.lean.name] = record.id
        if persist:
            self.store.upsert("declarations", incoming)
        self._bump()
        return len(incoming)

    def add_edges(self, edges: Iterable[DependencyEdge], *, persist: bool = True) -> int:
        added = self._graph.add_all(edges)
        if persist and added:
            self.store.upsert("edges", self._graph.edges)
        if added:
            self._bump()
        return added

    def replace_edges(
        self,
        edges: Iterable[DependencyEdge],
        *,
        source_ids: Iterable[str],
        edge_types: Iterable[EdgeType],
        persist: bool = True,
    ) -> tuple[int, int]:
        """Replace a *derived* edge set: drop the old projection, add the new one.

        Use for edges a tool re-derives wholesale (Lean extraction), never for edges that
        accumulate evidence (source cross-references, agent inferences). Returns
        (removed, added).

        Merging instead of replacing is how a declaration checked before its dependencies
        were formalized keeps a permanently dangling ``lean:<Name>`` prerequisite: the
        placeholder is emitted once, the real edge is added later, and nothing ever
        retracts the placeholder.
        """
        incoming = list(edges)
        removed = self._graph.drop(source_ids=source_ids, edge_types=edge_types)
        added = self._graph.add_all(incoming)
        if persist and (removed or added):
            self.store.write_all("edges", self._graph.edges)
        if removed or added:
            self._bump()
        return len(removed), added

    def register_notation(self, entries: Iterable[NotationEntry]) -> None:
        """Promote chapter-local notation into the project registry.

        Report 01 §E.4: 454 notation rows were re-derived across ten chapters, with the
        same symbols recurring in six or more. They belong here once.
        """
        for entry in entries:
            existing = self._notation.get(entry.symbol)
            if existing and existing.lean and entry.lean and existing.lean != entry.lean:
                raise RegistryError(
                    f"notation {entry.symbol!r} is already mapped to {existing.lean!r} "
                    f"(decided in {existing.decided_in}); refusing to remap it to {entry.lean!r}"
                )
            if existing is None or (entry.lean and not existing.lean):
                self._notation[entry.symbol] = entry
        self._bump()

    def set_convention(self, key: str, value: str) -> None:
        self._conventions[key] = value
        self._bump()

    # ---------------------------------------------------------------- queries

    def get(self, declaration_id: str) -> DeclarationRecord | None:
        return self._records.get(declaration_id)

    def require(self, declaration_id: str) -> DeclarationRecord:
        record = self._records.get(declaration_id)
        if record is None:
            raise RegistryError(f"no declaration {declaration_id!r} in corpus {self.store.corpus!r}")
        return record

    def resolve(self, declaration_id: str) -> DeclarationRecord | None:
        """Tolerant lookup that also resolves a reference to a *part* of an item.

        A source may print exercise 2.3.1 as one numbered item containing parts (a) and
        (b), and then cite "exercise 2.3.1(a)" from a later chapter. The citation is
        genuinely more specific than the item, and parts are sometimes formalized
        separately, so the part identity is kept on the *edge*. This resolves it to the
        parent item for retrieval, without rewriting the citation.

        Exact match wins; a trailing part letter is stripped only as a fallback.
        """
        exact = self._records.get(declaration_id)
        if exact is not None:
            return exact
        parent = PART_SUFFIX_RE.sub("", declaration_id)
        return self._records.get(parent) if parent != declaration_id else None

    def by_lean_name(self, lean_name: str) -> DeclarationRecord | None:
        owner = self._name_claims.get(lean_name)
        return self._records.get(owner) if owner else None

    def by_source_label(self, label: str, *, chapter: str | None = None) -> list[DeclarationRecord]:
        """Find by printed label. A label is not unique on its own -- chapter 3 has both
        Corollary 3.2.1 and Exercise 3.2.1 -- so this returns a list."""
        from pipeline.corpus.ids import normalize_label

        want = normalize_label(label)
        return [
            r
            for r in self._records.values()
            if r.source.label
            and normalize_label(r.source.label) == want
            and (chapter is None or r.source.chapter == str(chapter))
        ]

    def declarations_in_chapter(self, chapter: str | int) -> list[DeclarationRecord]:
        ch = str(chapter)
        return sorted(
            (r for r in self._records.values() if r.source.chapter == ch),
            key=lambda r: (r.source.span.start if r.source.span else 0, r.id),
        )

    def definitions_in_chapter(self, chapter: str | int) -> list[DeclarationRecord]:
        """The chapter digest's export list: what later chapters may build on."""
        return [r for r in self.declarations_in_chapter(chapter) if r.is_foundational]

    def theorem_like(self, *, chapter: str | int | None = None) -> list[DeclarationRecord]:
        pool = (
            self.declarations_in_chapter(chapter) if chapter is not None else list(self._records.values())
        )
        return sorted((r for r in pool if r.kind in THEOREM_LIKE), key=lambda r: r.id)

    def notation(self) -> dict[str, NotationEntry]:
        return dict(self._notation)

    def conventions(self) -> dict[str, str]:
        return dict(self._conventions)

    def prerequisites(self, declaration_id: str, **kw) -> list[str]:
        return self._graph.prerequisites(declaration_id, **kw)

    def reverse_dependencies(self, declaration_id: str, **kw) -> list[str]:
        return self._graph.dependents(declaration_id, **kw)

    def dependencies(self, declaration_id: str, **kw) -> list[str]:
        """What this declaration depends on. Delegates to the graph."""
        return self._graph.dependencies(declaration_id, **kw)

    def graph_stats(self) -> dict[str, object]:
        """Shape of the corpus graph. Delegates to the graph."""
        return self._graph.graph_stats()

    def eligible_nodes(self, completed=(), **kw) -> list[str]:
        """Declarations whose dependencies are satisfied. Delegates to the graph.

        The proof scheduler layers trust and approval policy on top of this; the graph
        answers only the structural half.
        """
        kw.setdefault("candidates", list(self._records))
        return self._graph.eligible_nodes(completed, **kw)

    def unresolved_dependencies(self) -> dict[str, list[str]]:
        """Source references that never resolved to a declaration.

        Report 03 §2.2 (checker 7) and issue ``i-063``: a chapter-2 proof plan cites
        exercise 2.1.5, which is not in the file and cannot be. Every such citation is a
        dangling edge that no build would ever flag.
        """
        out: dict[str, list[str]] = {}
        for record in self._records.values():
            missing = list(record.dependencies.unresolved)
            for edge in self._graph.out_edges(record.id):
                if is_mathlib_node(edge.target_id):
                    continue
                if self.resolve(edge.target_id) is None:
                    missing.append(edge.target_id)
            if missing:
                out[record.id] = sorted(set(missing))
        return out

    def dangling_edges(self) -> list[DependencyEdge]:
        return [
            e
            for e in self._graph.edges
            if not is_mathlib_node(e.target_id) and self.resolve(e.target_id) is None
        ]

    # ------------------------------------------------------- derived views

    def refresh_dependency_facets(self, *, persist: bool = True) -> int:
        """Recompute the denormalised dependency view on every record.

        The graph is authoritative; these fields are a projection kept on the record so
        a client can render a declaration without walking the graph.
        """
        for record in self._records.values():
            record.dependencies.lean_local = [
                t
                for t in self._graph.prerequisites(
                    record.id, edge_types=[EdgeType.LEAN_LOCAL_DEPENDENCY]
                )
                if not is_mathlib_node(t)
            ]
            record.dependencies.mathlib = sorted(
                t.removeprefix("mathlib:")
                for t in self._graph.prerequisites(
                    record.id, edge_types=[EdgeType.MATHLIB_DEPENDENCY]
                )
                if is_mathlib_node(t)
            )
            record.dependencies.informal = self._graph.prerequisites(
                record.id, edge_types=[EdgeType.INFORMAL_DEPENDENCY], include_mathlib=False
            )
            record.dependencies.reverse = [
                s for s in self._graph.dependents(record.id) if not is_mathlib_node(s)
            ]
        if persist:
            self.store.write_all("declarations", list(self._records.values()))
        self._bump()
        return len(self._records)

    # --------------------------------------------------------------- summary

    def stats(self) -> dict[str, object]:
        """Corpus overview -- the data behind a client's first screen."""
        records = list(self._records.values())
        by_chapter: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        by_trust: dict[str, int] = {}
        by_review: dict[str, int] = {}
        for r in records:
            by_chapter[r.source.chapter] = by_chapter.get(r.source.chapter, 0) + 1
            by_kind[r.kind.value] = by_kind.get(r.kind.value, 0) + 1
            by_trust[r.trust.status.value] = by_trust.get(r.trust.status.value, 0) + 1
            by_review[r.review.status.value] = by_review.get(r.review.status.value, 0) + 1
        return {
            "corpus": self.store.corpus,
            "version": self._version,
            "declarations": len(records),
            "with_lean": sum(1 for r in records if r.has_lean),
            "edges": len(self._graph),
            "claimed_names": len(self._name_claims),
            "notation_entries": len(self._notation),
            "by_chapter": dict(sorted(by_chapter.items())),
            "by_kind": dict(sorted(by_kind.items())),
            "by_trust": dict(sorted(by_trust.items())),
            "by_review": dict(sorted(by_review.items())),
            "unresolved_dependencies": len(self.unresolved_dependencies()),
        }

    @property
    def graph(self) -> CorpusGraph:
        return self._graph

    def __iter__(self) -> Iterator[DeclarationRecord]:
        return iter(self._records.values())

    def __len__(self) -> int:
        return len(self._records)
