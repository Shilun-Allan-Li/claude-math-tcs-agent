"""The corpus dependency graph.

Report 06 §E specifies it. Three consumers, one structure: context retrieval, UI clients
rendering, and proof scheduling.

Representation is a pair of adjacency dicts over an edge list. Milestone 2 explicitly
asks for the simplest thing that supports the queries, and the numbers justify it --
chapters 1-3 hold 86 declarations and the whole book a few hundred. A graph database
would be infrastructure without a problem.

The one non-obvious design point is :attr:`DependencyEdge.provenance`. Only
source-extracted, Lean-extracted and human-confirmed edges may gate progression; an
agent-inferred edge is a proposal. :meth:`DependencyGraph.prerequisites` therefore takes
a ``gating_only`` flag, and the proof scheduler uses it while the context builder does not.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator

from pipeline.artifacts.models import DependencyEdge, EdgeType

__all__ = [
    "CorpusGraph", "DependencyGraph", "MATHLIB_PREFIX", "LIBRARY_PREFIX",
    "is_mathlib_node", "is_library_node",
]

MATHLIB_PREFIX = "mathlib:"
#: Nodes that are not declarations of this corpus but of a library it builds on. The
#: Lean checker also emits ``lean:<Name>`` for a name it could not map to a declaration.
LIBRARY_PREFIXES = ("mathlib:", "lean:", "library:")
LIBRARY_PREFIX = "library:"


def is_mathlib_node(node_id: str) -> bool:
    return node_id.startswith(MATHLIB_PREFIX)


def is_library_node(node_id: str) -> bool:
    """Any node that is not a declaration of this corpus."""
    return node_id.startswith(LIBRARY_PREFIXES)


class CorpusGraph:
    """Directed multigraph over declaration ids, typed by :class:`EdgeType`.

    Edge direction is *dependent -> dependency*: an edge ``A -> B`` means "A needs B".
    So :meth:`prerequisites` follows edges forwards and :meth:`dependents` follows them
    backwards.
    """

    def __init__(self, edges: Iterable[DependencyEdge] = ()) -> None:
        self._edges: list[DependencyEdge] = []
        self._out: dict[str, list[DependencyEdge]] = defaultdict(list)
        self._in: dict[str, list[DependencyEdge]] = defaultdict(list)
        self._seen: set[tuple[str, str, str]] = set()
        self.add_all(edges)

    # ------------------------------------------------------------------ build

    def add(self, edge: DependencyEdge) -> bool:
        """Add an edge. Returns False if an identical triple was already present."""
        if edge.key in self._seen:
            return False
        self._seen.add(edge.key)
        self._edges.append(edge)
        self._out[edge.source_id].append(edge)
        self._in[edge.target_id].append(edge)
        return True

    def add_all(self, edges: Iterable[DependencyEdge]) -> int:
        return sum(1 for e in edges if self.add(e))

    def drop(
        self, *, source_ids: Iterable[str], edge_types: Iterable[EdgeType]
    ) -> list[DependencyEdge]:
        """Remove every edge out of ``source_ids`` with one of ``edge_types``.

        Needed because Lean-extracted edges are a *projection* of a built module, not an
        accumulation of observations: re-checking a module must be able to retract an
        edge the previous check inferred. Rebuilds the adjacency maps rather than mutating
        them, which is cheap at this corpus size and cannot leave them inconsistent.
        """
        sources, types = set(source_ids), set(edge_types)
        removed = [
            e for e in self._edges if e.source_id in sources and e.edge_type in types
        ]
        if not removed:
            return []
        keep = [e for e in self._edges if not (e.source_id in sources and e.edge_type in types)]
        self._edges, self._seen = [], set()
        self._out, self._in = defaultdict(list), defaultdict(list)
        self.add_all(keep)
        return removed

    # ------------------------------------------------------------------ query

    def __len__(self) -> int:
        return len(self._edges)

    @property
    def edges(self) -> list[DependencyEdge]:
        return list(self._edges)

    def nodes(self) -> set[str]:
        return set(self._out) | set(self._in)

    def out_edges(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
        gating_only: bool = False,
    ) -> list[DependencyEdge]:
        wanted = set(edge_types) if edge_types is not None else None
        return [
            e
            for e in self._out.get(node_id, ())
            if (wanted is None or e.edge_type in wanted) and (not gating_only or e.may_gate)
        ]

    def in_edges(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
        gating_only: bool = False,
    ) -> list[DependencyEdge]:
        wanted = set(edge_types) if edge_types is not None else None
        return [
            e
            for e in self._in.get(node_id, ())
            if (wanted is None or e.edge_type in wanted) and (not gating_only or e.may_gate)
        ]

    def prerequisites(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
        transitive: bool = False,
        gating_only: bool = False,
        include_mathlib: bool = True,
    ) -> list[str]:
        """What this declaration depends on."""
        if not transitive:
            out = [
                e.target_id
                for e in self.out_edges(node_id, edge_types=edge_types, gating_only=gating_only)
            ]
        else:
            out = list(
                self._reach(
                    node_id, forward=True, edge_types=edge_types, gating_only=gating_only
                )
            )
        if not include_mathlib:
            out = [n for n in out if not is_mathlib_node(n)]
        return sorted(set(out))

    def dependents(
        self,
        node_id: str,
        *,
        edge_types: Iterable[EdgeType] | None = None,
        transitive: bool = False,
        gating_only: bool = False,
    ) -> list[str]:
        """What depends on this declaration -- the reverse-dependency count that drives
        review prioritisation (report 03 §4)."""
        if not transitive:
            return sorted(
                {
                    e.source_id
                    for e in self.in_edges(
                        node_id, edge_types=edge_types, gating_only=gating_only
                    )
                }
            )
        return sorted(
            self._reach(node_id, forward=False, edge_types=edge_types, gating_only=gating_only)
        )

    def _reach(
        self,
        start: str,
        *,
        forward: bool,
        edge_types: Iterable[EdgeType] | None,
        gating_only: bool,
    ) -> set[str]:
        """Breadth-first closure. Cycle-safe: the corpus graph is a DAG by intent but a
        mis-inferred informal edge can create a cycle, and a checker should report that
        rather than a traversal hanging on it."""
        seen: set[str] = set()
        queue: deque[str] = deque([start])
        step = self.out_edges if forward else self.in_edges
        while queue:
            current = queue.popleft()
            for edge in step(current, edge_types=edge_types, gating_only=gating_only):
                nxt = edge.target_id if forward else edge.source_id
                if nxt not in seen and nxt != start:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def find_cycles(self, *, edge_types: Iterable[EdgeType] | None = None) -> list[list[str]]:
        """Cycles in the dependency structure, which are always a defect."""
        wanted = set(edge_types) if edge_types is not None else None
        colour: dict[str, int] = {}
        cycles: list[list[str]] = []
        stack: list[str] = []

        def visit(node: str) -> None:
            colour[node] = 1
            stack.append(node)
            for edge in self._out.get(node, ()):
                if wanted is not None and edge.edge_type not in wanted:
                    continue
                nxt = edge.target_id
                if colour.get(nxt, 0) == 0:
                    visit(nxt)
                elif colour.get(nxt) == 1:
                    cycles.append(stack[stack.index(nxt) :] + [nxt])
            stack.pop()
            colour[node] = 2

        for node in sorted(self.nodes()):
            if colour.get(node, 0) == 0:
                visit(node)
        return cycles

    def topological_order(
        self, *, edge_types: Iterable[EdgeType] | None = None
    ) -> list[str] | None:
        """Dependency-first order, or None if a cycle blocks it.

        This is the proof scheduler's backbone: report 06 §E.3 -- schedule by dependency
        structure, not by table of contents.
        """
        wanted = set(edge_types) if edge_types is not None else None
        indegree: dict[str, int] = {n: 0 for n in self.nodes()}
        for edge in self._edges:
            if wanted is not None and edge.edge_type not in wanted:
                continue
            indegree[edge.source_id] = indegree.get(edge.source_id, 0) + 1
        ready = deque(sorted(n for n, d in indegree.items() if d == 0))
        order: list[str] = []
        while ready:
            node = ready.popleft()
            order.append(node)
            for edge in sorted(self._in.get(node, ()), key=lambda e: e.source_id):
                if wanted is not None and edge.edge_type not in wanted:
                    continue
                indegree[edge.source_id] -= 1
                if indegree[edge.source_id] == 0:
                    ready.append(edge.source_id)
        return order if len(order) == len(indegree) else None

    # ------------------------------------------------- the named query surface
    #
    # These five are the deterministic API the rest of the system is written against:
    # the context builder, a UI client, and the proof scheduler all call *these*, and none of
    # them calls a model to do it. Everything above is the machinery they are built from.

    def dependencies(self, node_id: str, **kw) -> list[str]:
        """What ``node_id`` depends on. Alias of :meth:`prerequisites`."""
        return self.prerequisites(node_id, **kw)

    def reverse_dependencies(self, node_id: str, **kw) -> list[str]:
        """What depends on ``node_id``. Alias of :meth:`dependents`."""
        return self.dependents(node_id, **kw)

    def unresolved_dependencies(self, known: Iterable[str]) -> dict[str, list[str]]:
        """Edges pointing at ids that are not declarations and not library nodes.

        ``known`` is the set of declaration ids the corpus holds. Kept a parameter rather
        than a graph field because the graph is deliberately ignorant of the registry:
        it stores edges, not records.
        """
        have = set(known)
        out: dict[str, list[str]] = {}
        for edge in self._edges:
            if is_library_node(edge.target_id) or edge.target_id in have:
                continue
            out.setdefault(edge.source_id, []).append(edge.target_id)
        return {k: sorted(set(v)) for k, v in sorted(out.items())}

    def graph_stats(self) -> dict[str, object]:
        """Shape of the graph. No model is consulted, and none could help."""
        by_type: dict[str, int] = {}
        by_provenance: dict[str, int] = {}
        for edge in self._edges:
            by_type[edge.edge_type.value] = by_type.get(edge.edge_type.value, 0) + 1
            kind = edge.provenance.kind.value
            by_provenance[kind] = by_provenance.get(kind, 0) + 1
        nodes = self.nodes()
        library = {n for n in nodes if is_library_node(n)}
        cycles = self.find_cycles()
        return {
            "nodes": len(nodes),
            "declaration_nodes": len(nodes - library),
            "library_nodes": len(library),
            "edges": len(self._edges),
            "by_edge_type": dict(sorted(by_type.items())),
            "by_provenance": dict(sorted(by_provenance.items())),
            "gating_edges": sum(1 for e in self._edges if e.may_gate),
            "cycles": len(cycles),
            "roots": len([n for n in nodes if not self._out.get(n)]),
            "leaves": len([n for n in nodes if not self._in.get(n)]),
        }

    def eligible_nodes(
        self,
        completed: Iterable[str] = (),
        *,
        candidates: Iterable[str] | None = None,
        edge_types: Iterable[EdgeType] | None = None,
        gating_only: bool = False,
        ignore_library: bool = True,
    ) -> list[str]:
        """Nodes whose dependencies are all satisfied, and which are not themselves done.

        This is the scheduler's primitive, and it is ordinary graph code: a node is
        eligible when every prerequisite is in ``completed``. Library nodes are not work
        items, so by default they neither appear in the result nor block anything.

        With no edges at all every candidate is eligible, which is the correct answer for
        an independent node and the reason ``D`` in the standard fixture never waits.
        """
        done = set(completed)
        pool = set(candidates) if candidates is not None else self.nodes()
        out = []
        for node in sorted(pool):
            if node in done:
                continue
            if ignore_library and is_library_node(node):
                continue
            deps = self.prerequisites(
                node, edge_types=edge_types, gating_only=gating_only,
                include_mathlib=not ignore_library,
            )
            if all(d in done for d in deps if not (ignore_library and is_library_node(d))):
                out.append(node)
        return out

    def __iter__(self) -> Iterator[DependencyEdge]:
        return iter(self._edges)


#: The graph was called this before it grew the named query surface.
DependencyGraph = CorpusGraph
