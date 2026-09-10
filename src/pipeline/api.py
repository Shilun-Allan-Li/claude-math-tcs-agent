"""The stable programmatic interface.

Everything a client needs, and nothing about how a client should look. The CLI in
:mod:`pipeline.cli` is written against this and adds only formatting. A UI is expected
to be another consumer of exactly these methods, not a privileged one.

The rule that makes that credible is the one report 04 §B2 records the cost of breaking:
the summer's checker was specified against the VS Code InfoView, a feedback channel that
existed for one caller, and the pipeline could not run headless at all. So nothing here
imports a UI, returns HTML, or assumes a display. Every method returns plain JSON-safe
data structures built from persisted artifacts.

    >>> from pipeline.api import Pipeline
    >>> api = Pipeline("data", corpus=...)                  # any configured corpus
    >>> api.graph_stats()["edges"]                          # doctest: +SKIP
    8
    >>> api.dependencies(...)                               # doctest: +SKIP
    ['<a prerequisite declaration id>', '...']

Every read is a query against the artifact store. Nothing is cached across calls beyond
one registry load, so a second process sees the same answers — which is what makes the
CLI, a UI and a batch job interchangeable views of one state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.artifacts.store import COLLECTIONS, ArtifactStore
from pipeline.corpus import CorpusRegistry
from pipeline.corpus.config import available_corpora, corpus_for_slug, load_corpus
from pipeline.graph.corpus_graph import is_library_node

__all__ = ["Pipeline", "list_corpora"]


def list_corpora() -> list[dict[str, Any]]:
    """Every configured corpus. Does not need a data directory."""
    out = []
    for name in available_corpora():
        config = load_corpus(name)
        out.append({
            "corpus_id": config.corpus,
            "slug": config.slug,
            "title": config.title,
            "authors": list(config.authors),
            "source_type": config.source_type,
            "divisions": len(config.divisions),
            "config_path": str(config.path),
        })
    return out


class Pipeline:
    """A read/write handle on one corpus's persisted state."""

    def __init__(self, data_dir: str | Path, corpus: str | None = None) -> None:
        config = load_corpus(corpus)
        self.config = config
        self.corpus_id = config.corpus
        self.store = ArtifactStore(Path(data_dir), corpus=config.slug)
        self.registry = CorpusRegistry.load(self.store)

    def reload(self) -> Pipeline:
        """Re-read the artifact store. Cheap, and the only way to see another writer."""
        self.registry.reload()
        return self

    # ------------------------------------------------------------------- corpus

    def inspect_corpus(self) -> dict[str, Any]:
        config = self.config
        return {
            "corpus_id": config.corpus,
            "slug": config.slug,
            "title": config.title,
            "authors": list(config.authors),
            "source_type": config.source_type,
            "divisions": [
                {"number": d.number, "type": d.type, "title": d.title,
                 "markdown": str(d.markdown),
                 "pdf_pages": [d.pdf_page_start, d.pdf_page_end],
                 "printed_pages": [d.printed_page_start, d.printed_page_end]}
                for d in config.divisions
            ],
            "stats": self.corpus_stats(),
        }

    def corpus_stats(self) -> dict[str, Any]:
        return self.registry.stats()

    def list_divisions(self) -> list[dict[str, Any]]:
        """Source divisions, from the config, annotated with what has been ingested."""
        counts: dict[str, int] = {}
        for record in self.registry:
            counts[record.source.chapter] = counts.get(record.source.chapter, 0) + 1
        return [
            {"number": d.number, "type": d.type, "title": d.title,
             "declarations": counts.get(d.number, 0)}
            for d in self.config.divisions
        ]

    def list_declarations(
        self, *, division: str | None = None, kind: str | None = None
    ) -> list[dict[str, Any]]:
        """Compact rows. Use :meth:`get_declaration` for one in full."""
        out = []
        for record in sorted(self.registry, key=lambda r: r.id):
            if division is not None and record.source.chapter != str(division):
                continue
            if kind is not None and record.kind.value != kind:
                continue
            out.append({
                "id": record.id,
                "kind": record.kind.value,
                "label": record.source.label,
                "name": record.source.name,
                "division": record.source.chapter,
                "section": record.source.section,
                "lean_name": record.lean.name,
                "trust": record.trust.status.value,
                "review": record.review.status.value,
                "findings": len(record.finding_ids),
                "stage": self.stage_of(record.id),
            })
        return out

    # -------------------------------------------------------------- declarations

    def get_declaration(self, declaration_id: str) -> dict[str, Any] | None:
        """One declaration, every facet. ``None`` when the corpus does not hold it."""
        record = self.registry.get(declaration_id)
        if record is None:
            return None
        return {
            "id": record.id,
            "kind": record.kind.value,
            "is_foundational": record.is_foundational,
            "stage": self.stage_of(declaration_id),
            "source": self.get_source(declaration_id),
            "annotation": self.get_annotation(declaration_id),
            "proposal": self.get_proposal(declaration_id),
            "lean": record.lean.model_dump(mode="json"),
            "mappings": [m.model_dump(mode="json") for m in record.mappings],
            "trust": record.trust.model_dump(mode="json"),
            "review": self.get_review(declaration_id),
            "findings": self.findings(declaration_id),
            "dependencies": self.dependencies(declaration_id),
            "reverse_dependencies": self.reverse_dependencies(declaration_id),
        }

    def get_source(self, declaration_id: str) -> dict[str, Any] | None:
        record = self.registry.get(declaration_id)
        if record is None:
            return None
        source = record.source
        return {
            "document_id": source.document_id,
            "division": source.chapter,
            "section": source.section,
            "label": source.label,
            "name": source.name,
            "kind": source.kind.value,
            "statement": source.statement,
            "proof": source.proof,
            "printed_page": source.span.printed_page if source.span else None,
            "pdf_page": source.span.pdf_page if source.span else None,
            "fingerprint": source.fingerprint,
            "provenance": source.provenance.model_dump(mode="json"),
        }

    def get_annotation(self, declaration_id: str) -> dict[str, Any] | None:
        record = self.registry.get(declaration_id)
        if record is None or record.annotation is None:
            return None
        return record.annotation.model_dump(mode="json")

    def get_proposal(self, declaration_id: str) -> dict[str, Any] | None:
        for proposal in self.store.read("proposals"):
            if proposal.declaration_id == declaration_id:  # type: ignore[attr-defined]
                return proposal.model_dump(mode="json")
        return None

    def get_trust(self, declaration_id: str) -> dict[str, Any] | None:
        record = self.registry.get(declaration_id)
        return record.trust.model_dump(mode="json") if record else None

    def stage_of(self, declaration_id: str) -> str | None:
        """How far this declaration has travelled, derived from its artifacts."""
        from pipeline.orchestrator.state import derive_stage

        record = self.registry.get(declaration_id)
        return derive_stage(record).value if record else None

    # -------------------------------------------------------------------- graph

    def dependencies(self, declaration_id: str, **kw) -> list[str]:
        return self.registry.graph.dependencies(declaration_id, **kw)

    def reverse_dependencies(self, declaration_id: str, **kw) -> list[str]:
        return self.registry.graph.reverse_dependencies(declaration_id, **kw)

    def unresolved_dependencies(self) -> dict[str, list[str]]:
        return self.registry.unresolved_dependencies()

    def graph_stats(self) -> dict[str, Any]:
        return self.registry.graph.graph_stats()

    def eligible_nodes(self, completed: list[str] | None = None) -> list[str]:
        """Structural scheduling: nodes whose dependencies are all satisfied.

        Trust and approval policy are *not* applied here — see :meth:`proof_queue` for
        the scheduler that layers them on.
        """
        return self.registry.eligible_nodes(completed or [])

    def proof_queue(self) -> dict[str, Any]:
        """What may be proved now, and why the rest may not."""
        from pipeline.stages.prove import proof_eligibility, ready_declarations

        ready = [r.id for r in ready_declarations(self.registry)]
        blocked = []
        for record in self.registry:
            if record.id in ready or not record.has_lean:
                continue
            e = proof_eligibility(self.registry, record.id)
            blocked.append({"id": record.id, "reason": e.reason,
                            "blockers": list(e.blockers)})
        return {"ready": ready, "blocked": blocked}

    def edges(self, declaration_id: str | None = None) -> list[dict[str, Any]]:
        """Edges with full provenance: kind, producer, artifact, evidence."""
        graph = self.registry.graph
        if declaration_id is None:
            rows = graph.edges
        else:
            rows = graph.out_edges(declaration_id) + graph.in_edges(declaration_id)
        return [e.model_dump(mode="json") for e in rows]

    def edge_provenance(self, source_id: str, target_id: str) -> list[dict[str, Any]]:
        """Why the pipeline believes ``source_id`` depends on ``target_id``.

        A list, not a single answer: the same dependency is often asserted by more than
        one stage — the source cites it, the annotator infers it, and Lean extracts it —
        and each assertion is separate evidence with its own producer.
        """
        return [
            e.model_dump(mode="json")
            for e in self.registry.graph.out_edges(source_id)
            if e.target_id == target_id
        ]

    # ----------------------------------------------------------------- checkers

    def findings(self, declaration_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.store.read("findings")
        return [
            f.model_dump(mode="json") for f in rows
            if declaration_id is None or f.declaration_id == declaration_id  # type: ignore[attr-defined]
        ]

    def checker_status(self, declaration_id: str) -> dict[str, Any]:
        """Per-checker verdict for one declaration, and what it means for progression."""
        findings = [f for f in self.store.read("findings")
                    if f.declaration_id == declaration_id]  # type: ignore[attr-defined]
        by_checker: dict[str, dict[str, Any]] = {}
        for f in findings:
            row = by_checker.setdefault(f.checker.value, {
                "findings": 0, "worst_severity": None, "blocking": 0, "requires_human": 0,
            })
            row["findings"] += 1
            row["blocking"] += int(f.blocks_progression)
            row["requires_human"] += int(f.requires_human)
            from pipeline.artifacts.models import SEVERITY_RANK

            if (row["worst_severity"] is None
                    or SEVERITY_RANK[f.severity] > SEVERITY_RANK[row["worst_severity"]]):
                row["worst_severity"] = f.severity
        for row in by_checker.values():
            row["worst_severity"] = row["worst_severity"].value if row["worst_severity"] else None
        return {
            "declaration_id": declaration_id,
            "checkers": by_checker,
            "ran": sorted(by_checker),
            "not_run": sorted({"lean_integrity", "source_fidelity",
                               "library_context", "semantic_sanity"} - set(by_checker)),
        }

    # ------------------------------------------------------------------- review

    def get_review(self, declaration_id: str) -> dict[str, Any] | None:
        from pipeline.artifacts.records import record_fingerprint

        record = self.registry.get(declaration_id)
        if record is None:
            return None
        review = record.review
        return {
            "status": review.status.value,
            "agent_status": review.agent_status.value,
            "is_human_decided": review.is_human_decided,
            "risk_score": review.risk_score,
            "risk_factors": review.risk_factors,
            "human_decision": (review.human_decision.model_dump(mode="json")
                               if review.human_decision else None),
            "notes": [n.model_dump(mode="json") for n in review.notes],
            "stale": review.stale_against(record_fingerprint(record)),
        }

    def apply_review(
        self, declaration_id: str, decision: str, *, reviewer: str, rationale: str
    ) -> dict[str, Any]:
        """Record a human decision. Persistent; an agent may not overwrite it (rule 8)."""
        from pipeline.artifacts.models import ReviewStatus
        from pipeline.review import record_decision

        out = record_decision(
            self.registry, declaration_id, ReviewStatus(decision),
            reviewer=reviewer, rationale=rationale,
        )
        self.reload()
        return out.model_dump(mode="json")

    def add_note(self, declaration_id: str, *, author: str, text: str) -> None:
        from pipeline.review import add_note

        add_note(self.registry, declaration_id, author=author, text=text)
        self.reload()

    def review_queue(self, **filters: Any) -> list[dict[str, Any]]:
        from pipeline.review import recompute_review_states, review_queue

        entries = recompute_review_states(self.registry, persist=False)
        return [e.as_dict() for e in review_queue(entries, **filters)]

    # -------------------------------------------------------------------- proof

    def proof_attempts(self, declaration_id: str | None = None) -> list[dict[str, Any]]:
        return [
            a.model_dump(mode="json") for a in self.store.read("attempts")
            if declaration_id is None or a.declaration_id == declaration_id  # type: ignore[attr-defined]
        ]

    def verification_result(self, declaration_id: str) -> dict[str, Any] | None:
        """What Lean decided, and nothing an LLM decided (rule 5)."""
        record = self.registry.get(declaration_id)
        if record is None:
            return None
        trust = record.trust
        return {
            "declaration_id": declaration_id,
            "lean_name": record.lean.name,
            "compile_status": trust.compile_status.value,
            "trust": trust.status.value,
            "direct_sorry": trust.direct_sorry,
            "transitive_sorry": trust.transitive_sorry,
            "unfinished_construction": trust.unfinished_construction,
            "axioms": list(trust.axioms),
            "blocked_by": list(trust.blocked_by),
            "checked_at_fingerprint": trust.checked_at_fingerprint,
        }

    # --------------------------------------------------------------------- runs

    def list_runs(self) -> list[dict[str, Any]]:
        from pipeline.orchestrator.state import RunStore

        return [
            {"id": r.id, "status": r.status.value, "targets": len(r.targets),
             "by_stage": r.counts(), "failed": r.failed,
             "updated_at": r.updated_at.isoformat()}
            for r in RunStore(self.store.directory).list_runs()
        ]

    def run_status(self, run_id: str) -> dict[str, Any]:
        from pipeline.orchestrator.state import RunStore

        run = RunStore(self.store.directory).load(run_id)
        return {
            "id": run.id, "corpus": run.corpus, "status": run.status.value,
            "targets": list(run.targets), "by_stage": run.counts(),
            "failed": run.failed,
            "stop_after": run.stop_after.value if run.stop_after else None,
            "declarations": {k: v.model_dump(mode="json")
                             for k, v in run.declarations.items()},
        }

    def stage_events(self, run_id: str) -> list[dict[str, Any]]:
        from pipeline.orchestrator.state import RunStore

        run = RunStore(self.store.directory).load(run_id)
        return [e.model_dump(mode="json") for e in run.events]

    def stage_runs(self, declaration_id: str | None = None) -> list[dict[str, Any]]:
        """Worker executions: provider, model, prompt version, tokens, cost, outcome."""
        out = []
        for run in self.store.read("runs"):
            target = run.target_id or ""  # type: ignore[attr-defined]
            if declaration_id and not (target == declaration_id
                                       or target.startswith(f"{declaration_id}/")):
                continue
            out.append(run.model_dump(mode="json"))
        return out

    def artifacts_for(self, declaration_id: str) -> dict[str, list[dict[str, Any]]]:
        """Every persisted record belonging to one declaration, by collection.

        The pipeline pretty-renders elsewhere; it never hides the artifact.
        """
        out: dict[str, list[dict[str, Any]]] = {}
        for collection in COLLECTIONS:
            rows = []
            for row in self.store.read(collection):
                owner = (getattr(row, "declaration_id", None)
                         or getattr(row, "target_id", None)
                         or getattr(row, "id", None))
                if owner == declaration_id:
                    rows.append(row.model_dump(mode="json"))
            if rows:
                out[collection] = rows
        edges = [e.model_dump(mode="json") for e in self.registry.graph.edges
                 if declaration_id in (e.source_id, e.target_id)]
        if edges:
            out["edges"] = edges
        return out

    def context_package(self, package_id: str) -> dict[str, Any] | None:
        """What an agent was actually given, and why each item was retrieved."""
        for package in self.store.read("context"):
            if package.id != package_id:  # type: ignore[attr-defined]
                continue
            by_role: dict[str, list[dict[str, Any]]] = {}
            for item in package.items:
                by_role.setdefault(item.role, []).append({
                    "ref": item.ref, "reason": item.reason,
                    "chars": item.char_count, "content": item.content,
                })
            return {
                "id": package.id, "stage": package.stage.value,
                "target_id": package.target_id,
                "total_chars": package.total_chars,
                "estimated_tokens": package.estimated_tokens,
                "budget_chars": package.budget_chars,
                "within_budget": package.within_budget,
                "items": len(package.items), "by_role": by_role,
            }
        return None
