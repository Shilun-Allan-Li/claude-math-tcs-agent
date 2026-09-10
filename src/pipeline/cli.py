"""The ``pipeline`` command-line interface.

One rule governs this module: **it contains no business logic.** Every command resolves
arguments, calls into :mod:`pipeline.api`, and formats the result. Report 04 §B2 is the
cautionary tale -- the summer's checker agent was specified against a feedback channel
(the VS Code InfoView) that existed for exactly one caller, so the pipeline could not run
headless at all. Everything here therefore runs with no UI present, and a UI client is
just another consumer of the same API.

Every command supports ``--json`` for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.corpus.config import REPO_ROOT, available_corpora, load_corpus
from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.store import ArtifactStore

DEFAULT_DATA_DIR = REPO_ROOT / "data"


# --------------------------------------------------------------------- helpers


def _registry(args: argparse.Namespace) -> CorpusRegistry:
    config = load_corpus(args.corpus)
    store = ArtifactStore(Path(args.data_dir), corpus=config.slug)
    return CorpusRegistry.load(store)


def _emit(args: argparse.Namespace, payload: Any, text: str | None = None) -> None:
    if getattr(args, "json", False) or text is None:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(text)


def _rule(title: str) -> str:
    return f"\n\033[1m{title}\033[0m\n" + "-" * max(len(title), 12)


# -------------------------------------------------------------------- commands


def cmd_ingest(args: argparse.Namespace) -> int:
    from pipeline.stages.ingest import ingest_chapter

    registry = _registry(args)
    config = load_corpus(args.corpus)
    chapters = [c.number for c in config.chapters] if args.all else args.chapter
    if not chapters:
        print("nothing to do: pass one or more chapter numbers, or --all", file=sys.stderr)
        return 2

    results = []
    for ch in chapters:
        result = ingest_chapter(registry, ch, corpus_name=args.corpus)
        results.append(result.summary)
    registry.reload()
    registry.refresh_dependency_facets()

    payload = {"ingested": results, "stats": registry.stats()}
    lines = [_rule("Ingested")]
    for r in results:
        lines.append(
            f"  chapter {r['chapter']:>3}  {r['items']:>3} items  "
            f"{r['cross_reference_edges']:>3} cross-refs  {r['with_proof']:>3} with printed proof"
        )
    stats = registry.stats()
    lines.append(f"\n  corpus now holds {stats['declarations']} declarations, {stats['edges']} edges")
    unresolved = stats["unresolved_dependencies"]
    if unresolved:
        lines.append(f"  {unresolved} declarations have unresolved source references")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_ingest_pdf(args: argparse.Namespace) -> int:
    """Stage 0a: PDF -> Markdown, with a manifest."""
    from pipeline.prompts import load_prompt
    from pipeline.providers import provider_for_stage
    from pipeline.stages.pdf_adapter import (
        ExtractionManifest,
        PopplerRenderer,
        extract_pages,
        plan_extraction,
    )

    pdf = Path(args.pdf).expanduser()
    if not pdf.exists():
        print(f"no such PDF: {pdf}", file=sys.stderr)
        return 1
    out_dir = Path(args.out).expanduser()
    pages = list(range(args.first, args.last + 1))
    prompt = load_prompt("ingest", "extract-page", args.prompt_version)
    model = args.model or prompt.model

    if args.plan:
        manifest = ExtractionManifest.load(out_dir / "manifest.jsonl")
        todo, cached = plan_extraction(manifest, pages, prompt, model, args.dpi, force=args.force)
        payload = {
            "pdf": str(pdf), "out": str(out_dir), "pages": [args.first, args.last],
            "prompt_version": prompt.id, "model": model, "dpi": args.dpi,
            "to_extract": len(todo), "cached": len(cached), "first_todo": todo[:10],
        }
        _emit(args, payload, f"{_rule('Extraction plan')}\n"
              f"  {len(todo)} pages to extract, {len(cached)} cached\n"
              f"  prompt {prompt.id}  model {model}  dpi {args.dpi}")
        return 0

    def progress(row):
        if not args.json:
            mark = "ok " if row.status == "ok" else "FAIL"
            print(f"  p.{row.pdf_page:>3} {mark} {row.wall_ms or 0:>6}ms "
                  f"{(row.output_tokens or 0):>5} out-tok {row.error or ''}", flush=True)

    manifest = extract_pages(
        pdf, out_dir, pages,
        provider=provider_for_stage("ingest", provider=args.provider, model=args.model),
        renderer=PopplerRenderer(),
        source_title=args.title,
        model=model, prompt=prompt, dpi=args.dpi,
        printed_page_offset=args.printed_page_offset,
        force=args.force,
        on_progress=progress,
    )
    totals = manifest.totals()
    _emit(args, totals, f"{_rule('Extraction totals')}\n  " +
          "\n  ".join(f"{k:<18} {v}" for k, v in totals.items()))
    return 0 if totals["failed"] == 0 else 1


def cmd_prompts(args: argparse.Namespace) -> int:
    from pipeline.prompts import available_prompts, load_prompt

    payload = []
    for pid in available_prompts():
        stage, name, version = pid.split("/")
        pr = load_prompt(stage, name, version)
        payload.append({"id": pr.id, "model": pr.model, "max_tokens": pr.max_tokens,
                        "description": pr.description, "path": str(pr.path)})
    _emit(args, payload)
    return 0


def cmd_annotate(args: argparse.Namespace) -> int:
    """Stage 1: chapter Markdown -> annotated Markdown + Annotated Declaration IR."""
    from pipeline.providers import SectionFixtureProvider, provider_for_stage
    from pipeline.stages.annotate import annotate_chapter

    registry = _registry(args)
    provider = (
        SectionFixtureProvider(args.fixtures)
        if args.fixtures
        else provider_for_stage("annotate", provider=args.provider, model=args.model)
    )
    result = annotate_chapter(
        registry, args.chapter, provider=provider,
        corpus_name=args.corpus, model=args.model, sections=args.section or None,
    )
    if args.write_markdown:
        out = Path(args.write_markdown)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.markdown, encoding="utf-8")

    payload = {
        "summary": result.summary,
        "digest": result.digest.model_dump(mode="json"),
        "warnings": result.warnings,
    }
    s = result.summary
    lines = [_rule(f"Annotated chapter {result.chapter}")]
    lines.append(f"  {s['annotated']} declarations annotated")
    lines.append(f"  {s['definitions_discovered']} definitions found in prose")
    lines.append(f"  {s['informal_edges']} informal dependency edges")
    lines.append(f"  {s['notation']} notation entries promoted to the registry")
    lines.append(f"  {s['context_packages']} context packages, {s['context_chars']:,} chars total")
    lines.append(f"  digest: {result.digest.size_estimate_chars:,} chars, "
                 f"{len(result.digest.definitions)} definitions, {len(result.digest.results)} results")
    if result.warnings:
        lines.append("\n  warnings:")
        lines += [f"    - {w}" for w in result.warnings]
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    import json as _json

    registry = _registry(args)
    path = registry.store.directory / f"digest-{registry.store.corpus}-ch{args.chapter}.json"
    if not path.exists():
        print(f"no digest for chapter {args.chapter}; run `pipeline annotate {args.chapter}` first",
              file=sys.stderr)
        return 1
    _emit(args, _json.loads(path.read_text(encoding="utf-8")))
    return 0


def cmd_formalize(args: argparse.Namespace) -> int:
    """Stage 2: annotated declaration -> proposed Lean statement."""
    from pipeline.providers import DeclarationFixtureProvider, provider_for_stage
    from pipeline.stages.formalize import formalize_declaration

    from pipeline.stages.formalize import formalizable

    registry = _registry(args)
    targets = list(args.declaration_id)
    if not targets:
        if args.chapter is None:
            print("pass declaration ids, or --chapter N to formalize a whole chapter",
                  file=sys.stderr)
            return 2
        targets = formalizable(
            registry, chapter=args.chapter, include_done=args.force,
            kinds=set(args.kind) if args.kind else None,
        )
        if args.limit:
            targets = targets[: args.limit]
    if not targets:
        _emit(args, [], "nothing to formalize: every annotated declaration already has a proposal")
        return 0

    provider = (
        DeclarationFixtureProvider(args.fixtures)
        if args.fixtures
        else provider_for_stage("formalize", provider=args.provider, model=args.model)
    )
    # A chapter-wide run keeps going when one declaration fails. A rate limit, a malformed
    # response or a missing fixture on item three should not discard the other twenty-nine;
    # the failures are collected and reported at the end.
    results, failures = [], []
    for did in targets:
        try:
            results.append(
                formalize_declaration(registry, did, provider=provider, model=args.model)
            )
        except Exception as exc:  # noqa: BLE001 - reported per declaration, not swallowed
            failures.append((did, f"{type(exc).__name__}: {exc}"))
            if args.stop_on_error:
                break

    payload = {
        "formalized": [r.summary for r in results],
        "failed": [{"declaration_id": d, "error": e} for d, e in failures],
    }
    lines = [_rule("Formalized")]
    for r in results:
        s_ = r.summary
        lines.append(
            f"  {s_['declaration_id']:22} {s_['status']:12} {s_['lean_name'] or '-':50} "
            f"{s_['sorry_kind']}"
        )
        for w in r.warnings:
            lines.append(f"      ! {w}")
    if failures:
        lines.append("")
        lines.append(f"  {len(failures)} failed:")
        for did, error in failures:
            lines.append(f"    {did:22} {error[:110]}")
    _emit(args, payload, "\n".join(lines))
    return 1 if failures and not results else 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    """Assemble accepted proposals into a compilable Lean module."""
    from pipeline.corpus.config import load_corpus
    from pipeline.stages.scaffold import plan_scaffold, render_scaffold

    registry = _registry(args)
    chapter = load_corpus(args.corpus).chapter(args.chapter)
    plan = plan_scaffold(registry, args.chapter, module=args.module)
    source = render_scaffold(registry, plan, chapter_title=chapter.title)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source, encoding="utf-8")
    payload = plan.summary | {"path": str(out), "order": [r.lean.name for r in plan.records]}
    lines = [_rule(f"Scaffold {plan.module}")]
    lines.append(f"  {len(plan.records)} declarations -> {out}")
    for r in plan.records:
        lines.append(f"    {r.id:22} {r.lean.name}")
    for decl_id, reason in plan.excluded:
        lines.append(f"    excluded: {decl_id} ({reason})")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Stage 3: run the Lean integrity checker over a module."""
    from pipeline.checkers.lean_integrity import check_lean_integrity

    registry = _registry(args)
    result = check_lean_integrity(registry, args.module, cwd=args.lean_root or REPO_ROOT)
    payload = {
        "summary": result.summary,
        "trust": {k: v.value for k, v in sorted(result.trust.items())},
        "findings": [f.model_dump(mode="json") for f in result.findings],
    }
    lines = [_rule(f"Lean integrity: {args.module}")]
    lines.append(f"  build {'ok' if result.build.ok else 'FAILED'} in {result.build.wall_ms} ms")
    lines.append(f"  {len(result.trust)} declarations, {len(result.edges)} Lean edges")
    lines.append("")
    for did, status in sorted(result.trust.items()):
        record = registry.get(did)
        name = record.lean.name if record and record.lean.name else did
        lines.append(f"    {did:22} {status.value:34} {name}")
    problems = [f for f in result.findings if f.status.value != "pass"]
    if problems:
        lines.append("")
        lines.append("  findings:")
        for f in sorted(problems, key=lambda f: f.severity.value):
            lines.append(f"    [{f.severity.value:8}] {f.category.value:26} {f.declaration_id}")
            lines.append(f"               {f.message}")
    _emit(args, payload, "\n".join(lines))
    return 0 if result.build.ok else 1


def _checker_providers(args: argparse.Namespace) -> dict:
    """One provider per checker, so each can be configured independently.

    Pointing two checkers at different model families is a real use: a second opinion from
    a different lineage is worth more than a second sample from the same one.
    """
    from pipeline.providers import DeclarationFixtureProvider, provider_for_stage

    if args.fixtures:
        root = Path(args.fixtures)
        return {
            "fidelity_provider": DeclarationFixtureProvider(root / "source", missing_ok=True),
            "library_provider": DeclarationFixtureProvider(root / "library", missing_ok=True),
            "semantic_provider": DeclarationFixtureProvider(root / "semantic", missing_ok=True),
        }
    if args.deterministic_only:
        return {}
    return {
        "fidelity_provider": provider_for_stage(
            "check-source", provider=args.provider, model=args.model),
        "library_provider": provider_for_stage(
            "check-library", provider=args.provider, model=args.model),
        "semantic_provider": provider_for_stage(
            "check-semantic", provider=args.provider, model=args.model),
    }


def cmd_check_all(args: argparse.Namespace) -> int:
    """Stage 3: run all four checkers, then recompute the review queue."""
    from pipeline.review import recompute_review_states, review_queue
    from pipeline.checkers.orchestrator import run_checkers

    registry = _registry(args)
    report = run_checkers(
        registry, module=args.module,
        declaration_ids=args.declaration or None,
        lean_root=args.lean_root or REPO_ROOT,
        verify_mathlib_names=args.verify_names,
        **_checker_providers(args),
    )
    registry.reload()
    entries = recompute_review_states(registry)
    queued = review_queue(entries, queues=["BLOCKED", "REVIEW-NOW"])

    payload = {
        "summary": report.summary,
        "warnings": report.warnings,
        "queue": [e.as_dict() for e in queued],
    }
    s_ = report.summary
    lines = [_rule("Checker run")]
    lines.append(f"  {s_['declarations']} declarations, {s_['findings']} findings, "
                 f"{s_['blocking']} blocking, {s_['requires_human']} need a human")
    lines.append(f"  by checker  {s_['by_checker']}")
    lines.append(f"  by severity {s_['by_severity']}")
    if s_["usd"]:
        lines.append(f"  cost        ${s_['usd']}")
    if queued:
        lines.append("")
        lines.append("  needs attention:")
        for e in queued[:12]:
            lines.append(f"    {e.queue:11} {e.score:5.1f}  {e.record.id:22} {e.record.trust.status.value}")
    for w in report.warnings:
        lines.append(f"    ! {w}")
    _emit(args, payload, "\n".join(lines))
    return 0




def cmd_note(args: argparse.Namespace) -> int:
    from pipeline.review import add_note

    registry = _registry(args)
    add_note(registry, args.declaration_id, author=args.author, text=args.text)
    _emit(args, {"declaration_id": args.declaration_id, "note": args.text}, "note added")
    return 0


def cmd_prove(args: argparse.Namespace) -> int:
    """Stage 4: prove approved statements."""
    from pipeline.providers import TextFixtureProvider, provider_for_stage
    from pipeline.stages.prove import prove_declaration, ready_declarations

    registry = _registry(args)
    provider = (
        TextFixtureProvider(args.fixtures)
        if args.fixtures
        else provider_for_stage("prove", provider=args.provider, model=args.model)
    )
    targets = args.declaration_id or [
        r.id for r in ready_declarations(registry, chapter=args.chapter)
    ]
    if not targets:
        _emit(args, {"ready": []}, "nothing is ready to prove")
        return 0

    results = []
    for declaration_id in targets:
        result = prove_declaration(
            registry, declaration_id, provider=provider,
            lean_root=args.lean_root or REPO_ROOT, model=args.model,
            max_attempts=args.max_attempts,
            require_approval=not args.allow_unapproved,
        )
        results.append(result)
        registry.reload()

    payload = [r.summary for r in results]
    lines = [_rule("Proof attempts")]
    for r in results:
        s_ = r.summary
        lines.append(f"  {s_['declaration_id']:22} {s_['outcome']:26} "
                     f"{s_['attempts']} attempt(s), context {s_['context_chars']} chars")
        for a in r.attempts:
            if a.review_reason:
                lines.append(f"      statement review: {a.review_reason.splitlines()[0][:90]}")
            elif a.failure_class:
                lines.append(f"      attempt {a.attempt}: {a.failure_class}")
        if not r.attempts and r.runs:
            lines.append(f"      skipped: {r.runs[-1].error}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_ready(args: argparse.Namespace) -> int:
    """Which declarations may enter the proof queue, and why the rest may not."""
    from pipeline.stages.prove import proof_eligibility, ready_declarations

    registry = _registry(args)
    ready = ready_declarations(registry, chapter=args.chapter)
    ready_ids = {r.id for r in ready}
    blocked = []
    for record in registry:
        if record.id in ready_ids or not record.has_lean:
            continue
        if args.chapter and record.source.chapter != str(args.chapter):
            continue
        e = proof_eligibility(registry, record.id)
        blocked.append({"declaration_id": record.id, "reason": e.reason,
                        "blockers": list(e.blockers)})
    payload = {"ready": [r.id for r in ready], "blocked": blocked}
    lines = [_rule("Proof queue")]
    lines.append(f"  ready ({len(ready)}), in dependency order:")
    for r in ready:
        lines.append(f"    {r.id:22} {r.lean.name}")
    lines.append(f"\n  not ready ({len(blocked)}):")
    for b in blocked:
        extra = f"  [{', '.join(b['blockers'])}]" if b["blockers"] else ""
        lines.append(f"    {b['declaration_id']:22} {b['reason']}{extra}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_blueprint(args: argparse.Namespace) -> int:
    """Stage 5: project approved declarations into Blueprint artifacts."""
    from pipeline.corpus.config import load_corpus
    from pipeline.integrations.blueprint import write_blueprint

    registry = _registry(args)
    chapter = load_corpus(args.corpus).chapter(args.chapter)
    summary = write_blueprint(
        registry, args.chapter, out_dir=args.out, chapter_title=chapter.title,
        require_approval=not args.include_unapproved,
    )
    lines = [_rule(f"Blueprint chapter {args.chapter}")]
    lines.append(f"  {summary['records']} records -> {summary['tex']}")
    lines.append(f"  {summary['leanok']} statements formalized, {summary['proved']} proved, "
                 f"{summary['notready']} not ready")
    if summary["skipped_unapproved"]:
        lines.append(f"  {summary['skipped_unapproved']} formalized declarations skipped "
                     f"(not APPROVED); use --include-unapproved to preview them")
    _emit(args, summary, "\n".join(lines))
    return 0



def cmd_status(args: argparse.Namespace) -> int:
    registry = _registry(args)
    stats = registry.stats()
    lines = [_rule(f"Corpus {stats['corpus']}  (registry v{stats['version']})")]
    lines.append(f"  declarations   {stats['declarations']}")
    lines.append(f"  with Lean      {stats['with_lean']}")
    lines.append(f"  edges          {stats['edges']}")
    lines.append(f"  claimed names  {stats['claimed_names']}")
    lines.append(f"  notation       {stats['notation_entries']}")
    for label, key in (("by chapter", "by_chapter"), ("by kind", "by_kind"),
                       ("by trust", "by_trust"), ("by review", "by_review")):
        if stats[key]:
            body = "  ".join(f"{k}={v}" for k, v in stats[key].items())
            lines.append(f"  {label:<13} {body}")
    _emit(args, stats, "\n".join(lines))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    registry = _registry(args)
    record = registry.get(args.declaration_id)
    if record is None:
        print(f"no declaration {args.declaration_id!r}", file=sys.stderr)
        return 1
    payload = record.model_dump(mode="json")
    payload["derived"] = {
        "is_theorem_like": record.is_theorem_like,
        "is_foundational": record.is_foundational,
        "reverse_dependency_count": record.reverse_dependency_count,
        "prerequisites": registry.prerequisites(record.id),
        "reverse_dependencies": registry.reverse_dependencies(record.id),
    }

    src = record.source
    lines = [_rule(f"{record.id}")]
    lines.append(f"  kind      {record.kind.value}")
    lines.append(f"  source    {src.chapter_id} §{src.section or '-'} label {src.label or '-'}"
                 + (f"  printed p.{src.span.printed_page}" if src.span and src.span.printed_page else ""))
    lines.append(f"  statement {src.statement[:200]}")
    if src.proof:
        lines.append(f"  proof     {src.proof[:160]}...")
    lines.append(f"  lean      {record.lean.name or '(none)'}"
                 + (f"  [{record.lean.sorry_kind.value}]" if record.lean.name else ""))
    lines.append(f"  trust     {record.trust.status.value}")
    lines.append(f"  review    {record.review.status.value}")
    if payload["derived"]["prerequisites"]:
        lines.append(f"  needs     {', '.join(payload['derived']['prerequisites'])}")
    if payload["derived"]["reverse_dependencies"]:
        lines.append(f"  used by   {', '.join(payload['derived']['reverse_dependencies'])}")
    if record.mappings:
        lines.append("  mappings:")
        for m in record.mappings:
            lines.append(f"    {m.mapping_type.value:<18} {m.semantic_status.value:<18} {m.aspect}")
    _emit(args, payload, "\n".join(lines))
    return 0



def cmd_providers(args: argparse.Namespace) -> int:
    """What the pipeline can talk to on this machine, and what each option needs."""
    from pipeline.providers import available_providers, resolve_auto, stage_plan
    from pipeline.settings import load_settings

    infos = available_providers()
    settings = load_settings()
    try:
        auto = resolve_auto()
    except Exception as exc:  # noqa: BLE001 - reported, not raised, so the table still prints
        auto = None
        auto_error = str(exc)
    else:
        auto_error = None

    payload = {
        "auto": auto,
        "settings_file": str(settings.path) if settings.path else None,
        "default_provider": settings.default_provider,
        "providers": [
            {"name": i.name, "kind": i.kind, "available": i.available,
             "reason": i.reason, "note": i.note}
            for i in infos
        ],
        "stages": {
            plan.stage: {"provider": plan.provider, "model": plan.model}
            for stage in ("ingest", "annotate", "formalize", "check-source",
                          "check-library", "check-semantic", "prove", "repair")
            for plan in [stage_plan(stage, resolve=auto is not None)]
        },
    }

    lines = [_rule("Providers")]
    for i in infos:
        mark = "\033[32m ok \033[0m" if i.available else "\033[90m -- \033[0m"
        lines.append(f"  [{mark}] {i.name:14} {i.kind:17} {i.reason or i.note}")
    lines.append("")
    if auto:
        lines.append(f"  auto resolves to: {auto}")
    else:
        lines.append(f"  auto cannot resolve: {auto_error}")
    if settings.path:
        lines.append(f"  settings: {settings.path}")
    lines.append("")
    lines.append("  per stage:")
    for stage, cfg in payload["stages"].items():
        lines.append(f"    {stage:16} {cfg['provider']:12} {cfg['model'] or '(provider default)'}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_corpus_list(args: argparse.Namespace) -> int:
    from pipeline.api import list_corpora

    payload = list_corpora()
    lines = [_rule(f"Corpora ({len(payload)})")]
    for c in payload:
        lines.append(f"  {c['corpus_id']:<20} {c['slug']:<6} {c['source_type']:<8} "
                     f"{c['divisions']:>3} divisions  {c['title']}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_corpus_show(args: argparse.Namespace) -> int:
    from pipeline.api import Pipeline

    api = Pipeline(args.data_dir, corpus=args.corpus_id or args.corpus)
    payload = api.inspect_corpus()
    s = payload["stats"]
    lines = [_rule(f"{payload['corpus_id']}  ({payload['slug']})")]
    lines.append(f"  title        {payload['title']}")
    lines.append(f"  authors      {', '.join(payload['authors']) or '-'}")
    lines.append(f"  source type  {payload['source_type']}")
    lines.append(f"  declarations {s['declarations']}  ({s['with_lean']} with Lean)")
    lines.append("")
    lines.append(f"  {'division':<26}{'declarations':>12}")
    for d in api.list_divisions():
        lines.append(f"  {d['type'] + ' ' + d['number'] + ' · ' + (d['title'] or ''):<26}"
                     f"{d['declarations']:>12}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_corpus_declarations(args: argparse.Namespace) -> int:
    from pipeline.api import Pipeline

    api = Pipeline(args.data_dir, corpus=args.corpus)
    payload = api.list_declarations(division=args.division, kind=args.kind)
    lines = [_rule(f"Declarations ({len(payload)})")]
    lines.append(f"  {'id':<24}{'kind':<12}{'stage':<12}{'trust':<20}{'review':<14}lean")
    for d in payload:
        lines.append(f"  {d['id']:<24}{d['kind']:<12}{(d['stage'] or '-'):<12}"
                     f"{d['trust']:<20}{d['review']:<14}{d['lean_name'] or '-'}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_corpora(args: argparse.Namespace) -> int:
    payload = []
    for name in available_corpora():
        cfg = load_corpus(name)
        payload.append(
            {
                "corpus": cfg.corpus,
                "slug": cfg.slug,
                "title": cfg.title,
                "chapters": [
                    {"number": c.number, "title": c.title,
                     "pdf_pages": [c.pdf_page_start, c.pdf_page_end],
                     "printed_pages": [c.printed_page_start, c.printed_page_end]}
                    for c in cfg.chapters
                ],
            }
        )
    _emit(args, payload)
    return 0


def _pipeline_providers(args: argparse.Namespace) -> tuple[dict, dict]:
    """Build the per-stage provider map and stage options for the orchestrator.

    Fixtures and live providers are chosen the same way the individual stage commands
    choose them, so `pipeline run` exercises the same adapters as `pipeline annotate`.
    """
    from pipeline.providers import (
        DeclarationFixtureProvider,
        SectionFixtureProvider,
        TextFixtureProvider,
        provider_for_stage,
    )

    providers: dict = {}
    options: dict = {"check": {}}
    root = Path(args.fixtures) if args.fixtures else None
    if root:
        providers["annotate"] = SectionFixtureProvider(root / "annotate" / args.fixture_division)
        providers["formalize"] = DeclarationFixtureProvider(root / "formalize" / args.fixture_division)
        if (root / "prove").exists():
            providers["prove"] = TextFixtureProvider(root / "prove")
        options["check"]["checker_providers"] = {
            "fidelity_provider": DeclarationFixtureProvider(root / "check/source", missing_ok=True),
            "library_provider": DeclarationFixtureProvider(root / "check/library", missing_ok=True),
            "semantic_provider": DeclarationFixtureProvider(root / "check/semantic", missing_ok=True),
        }
    else:
        for stage in ("annotate", "formalize", "prove"):
            providers[stage] = provider_for_stage(stage, provider=args.provider, model=args.model)
        options["check"]["checker_providers"] = {
            "fidelity_provider": provider_for_stage("check-source", provider=args.provider),
            "library_provider": provider_for_stage("check-library", provider=args.provider),
            "semantic_provider": provider_for_stage("check-semantic", provider=args.provider),
        }
    if args.module:
        options["check"]["module"] = args.module
        options.setdefault("prove", {})["lean_root"] = args.lean_root or str(REPO_ROOT)
    options["check"]["lean_root"] = args.lean_root or str(REPO_ROOT)
    return providers, options


def _run_lines(orch) -> list[str]:
    s = orch.summary()
    lines = [_rule(f"Run {s['run_id']}  [{s['status']}]")]
    lines.append(f"  corpus      {s['corpus']}")
    lines.append(f"  targets     {s['targets']}   gate: stop after {s['stop_after']}")
    lines.append(f"  by stage    " + ("  ".join(f"{k}={v}" for k, v in s["by_stage"].items()) or "-"))
    if s["failed"]:
        lines.append(f"  failed      {', '.join(s['failed'])}")
    lines.append("")
    lines.append("  declarations:")
    for did in orch.run.targets:
        st = orch.run.state_for(did)
        extra = f"  {st.error}" if st.error else (f"  {st.blocked_reason}" if st.blocked_reason else "")
        lines.append(f"    {did:24} {st.stage.value:<12} {st.status.value:<8}{extra}")
    return lines


def cmd_run_start(args: argparse.Namespace) -> int:
    """Drive declarations through the pipeline to the configured gate."""
    from pipeline.orchestrator import DeclarationStage, PipelineOrchestrator

    registry = _registry(args)
    targets = list(args.declaration_id)
    if not targets:
        print("pass one or more declaration ids", file=sys.stderr)
        return 2
    providers, options = _pipeline_providers(args)
    run_id = args.run_id or f"run-{int(time.time())}"
    orch = PipelineOrchestrator.start(
        registry, run_id=run_id, targets=targets,
        stop_after=DeclarationStage(args.stop_after),
        providers=providers, stage_options=options,
    )
    results = orch.run_until_gate()
    payload = {"summary": orch.summary(), "steps": [r.as_dict() for r in results]}
    lines = [_rule("Pipeline steps")]
    for r in results:
        mark = "ok " if r.ok else r.status.value
        lines.append(f"  {mark:<8} {r.stage.value:<10} {r.declaration_id:24} "
                     f"{r.from_stage.value} -> {r.to_stage.value}  {r.wall_ms}ms")
        if r.error:
            lines.append(f"           ! {r.error[:120]}")
    lines += _run_lines(orch)
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_run_status(args: argparse.Namespace) -> int:
    from pipeline.orchestrator import PipelineOrchestrator, RunStore

    registry = _registry(args)
    store = RunStore(registry.store.directory)
    if args.run_id:
        run = store.load(args.run_id)
    else:
        run = store.latest()
        if run is None:
            _emit(args, {"runs": []}, "no pipeline runs recorded")
            return 0
    orch = PipelineOrchestrator(registry, run, store)
    orch.sync_from_artifacts()
    payload = {"summary": orch.summary(),
               "events": [e.model_dump(mode="json") for e in run.events]}
    lines = _run_lines(orch)
    if args.events:
        lines.append("")
        lines.append("  events:")
        for e in run.events:
            lines.append(f"    {e.at.isoformat()[11:19]}  {e.kind:<13} "
                         f"{(e.declaration_id or '-'):24} {e.message[:90]}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_run_resume(args: argparse.Namespace) -> int:
    """Resume a run in this process from persisted state alone."""
    from pipeline.orchestrator import PipelineOrchestrator

    providers, options = _pipeline_providers(args)
    config = load_corpus(args.corpus)
    orch = PipelineOrchestrator.resume(
        Path(args.data_dir), config.slug, args.run_id,
        providers=providers, stage_options=options,
    )
    if args.stop_after:
        from pipeline.orchestrator import DeclarationStage

        orch.run.stop_after = DeclarationStage(args.stop_after)
    results = orch.run_until_gate()
    payload = {"summary": orch.summary(), "steps": [r.as_dict() for r in results]}
    lines = [_rule(f"Resumed {args.run_id}")]
    lines.append(f"  reconstructed from {orch.run_store.path(args.run_id)}")
    lines.append(f"  {len(results)} further step(s) executed")
    for r in results:
        lines.append(f"    {r.stage.value:<10} {r.declaration_id:24} "
                     f"{r.from_stage.value} -> {r.to_stage.value}")
    lines += _run_lines(orch)
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_run_list(args: argparse.Namespace) -> int:
    from pipeline.orchestrator import RunStore

    registry = _registry(args)
    runs = RunStore(registry.store.directory).list_runs()
    payload = [{"id": r.id, "status": r.status.value, "targets": len(r.targets),
                "by_stage": r.counts(), "updated_at": r.updated_at.isoformat()} for r in runs]
    lines = [_rule(f"Pipeline runs ({len(runs)})")]
    for r in runs:
        lines.append(f"  {r.id:26} {r.status.value:<26} {len(r.targets):>3} targets  "
                     f"{r.updated_at.isoformat()[:19]}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_workers(args: argparse.Namespace) -> int:
    """The worker table: input, output, prompt and context builder for each stage."""
    from pipeline.orchestrator import describe_workers

    payload = describe_workers()
    lines = [_rule("Workers")]
    for w in payload:
        lines.append(f"  {w['worker']:<22} stage={w['stage']:<10} -> {w['produces']}")
        lines.append(f"      input    {', '.join(w['input'])}")
        lines.append(f"      output   {w['output']}")
        lines.append(f"      prompt   {w['prompt'] or '(none — deterministic or multi-prompt)'}")
        lines.append(f"      context  {w['context_builder'] or '(none — reads the record)'}")
    _emit(args, payload, "\n".join(lines))
    return 0


DEMO_CORPUS = "demo-naturals"
DEMO_SLUG = "dn"
DEMO_ARTIFACTS = REPO_ROOT / "examples" / "demo-corpus" / "artifacts"
DEFAULT_DEMO_DIR = "/tmp/pipeline-demo"


def cmd_demo(args: argparse.Namespace) -> int:
    """Materialise the committed demo artifacts and report what is in them.

    The artifacts under ``examples/demo-corpus/artifacts/`` are a committed regression
    fixture, produced once by a real pipeline run and checked in. They are not regenerated
    here: a demo that rebuilt itself would be a different demo on every machine, and could
    not be a fixture.
    """
    import shutil

    if not DEMO_ARTIFACTS.exists():
        print(f"no demo artifacts at {DEMO_ARTIFACTS}", file=sys.stderr)
        return 1

    data_dir = Path(args.data_dir) if args.data_dir_given else Path(args.into or DEFAULT_DEMO_DIR)
    if args.fresh and data_dir.exists():
        shutil.rmtree(data_dir)
    # Check for the corpus, not just the directory: a stale path from some other run
    # would otherwise present as an empty demo.
    if not (data_dir / DEMO_SLUG).exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(DEMO_ARTIFACTS, data_dir, dirs_exist_ok=True)

    from pipeline.api import Pipeline

    api = Pipeline(data_dir, corpus=DEMO_CORPUS)
    stats = api.corpus_stats()
    graph = api.graph_stats()
    payload = {"corpus": DEMO_CORPUS, "data_dir": str(data_dir),
               "corpus_stats": stats, "graph_stats": graph,
               "declarations": api.list_declarations()}

    lines = [_rule("Demo corpus — committed artifacts, no model call")]
    lines.append(f"  corpus      {DEMO_CORPUS}   {stats['declarations']} declarations")
    lines.append(f"  artifacts   {data_dir}")
    lines.append(f"  graph       {graph['nodes']} nodes, {graph['edges']} edges, "
                 f"{graph['gating_edges']} gating")
    lines.append("")
    lines.append(f"  {'declaration':<22}{'kind':<12}{'lean name':<32}{'trust':<18}review")
    for d in api.list_declarations():
        lines.append(f"  {d['id']:<22}{d['kind']:<12}{(d['lean_name'] or '-'):<32}"
                     f"{d['trust']:<18}{d['review']}")
    lines.append("")
    # The demo materialises into its own directory, so every follow-up has to be pointed
    # at it. Printing the hints without --data-dir sends the reader to an empty store.
    where = "" if data_dir == Path(DEFAULT_DATA_DIR) else f" --data-dir {data_dir}"
    lines.append(f"  inspect one:      pipeline{where} inspect dn-ch1-thm-1.3")
    lines.append(f"  its dependencies: pipeline{where} graph deps dn-ch1-thm-1.3")
    lines.append(f"  why an edge:      pipeline{where} graph node dn-ch1-thm-1.3")
    lines.append(f"  its trust state:  pipeline{where} graph stats")
    lines.append("  run it for real:  pipeline run demo-naturals --fixtures examples/demo-corpus/fixtures")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    """The executable agents: typed input/output, prompt file, context builder."""
    from pipeline.agents import describe_agents

    payload = describe_agents()
    lines = [_rule("Agents  (src/pipeline/agents — executable; prompts/ — instructions)")]
    for a in payload:
        lines.append(f"  {a['agent']:<22} stage={a['stage']}")
        lines.append(f"      input    {', '.join(a['input'])}")
        lines.append(f"      output   {a['output']}")
        lines.append(f"      prompt   {a['prompt'] or '(none — deterministic or multi-prompt)'}")
        lines.append(f"      context  {'agent.build_context (graph query)' if a['context_builder'] else '(reads the record)'}")
        lines.append(f"      {a['description']}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_graph_stats(args: argparse.Namespace) -> int:
    registry = _registry(args)
    payload = registry.graph_stats()
    lines = [_rule("Corpus graph")]
    for k, v in payload.items():
        body = "  ".join(f"{a}={b}" for a, b in v.items()) if isinstance(v, dict) else v
        lines.append(f"  {k:<20} {body}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_graph_node(args: argparse.Namespace) -> int:
    """One node: its edges, both directions, with provenance on each."""
    registry = _registry(args)
    did = args.declaration_id
    graph = registry.graph
    out_e, in_e = graph.out_edges(did), graph.in_edges(did)
    payload = {
        "id": did,
        "dependencies": graph.dependencies(did),
        "reverse_dependencies": graph.reverse_dependencies(did),
        "out_edges": [e.model_dump(mode="json") for e in out_e],
        "in_edges": [e.model_dump(mode="json") for e in in_e],
    }
    lines = [_rule(f"Node {did}")]
    lines.append(f"  dependencies       {len(out_e)}")
    for e in out_e:
        p = e.provenance
        lines.append(f"    → {e.target_id:<26} [{e.edge_type.value}]")
        lines.append(f"        provenance {p.kind.value} · producer={p.producer} "
                     f"· artifact={p.artifact_id}")
        if p.evidence:
            lines.append(f"        evidence   {p.evidence}")
    lines.append(f"  reverse dependencies {len(in_e)}")
    for e in in_e:
        p = e.provenance
        lines.append(f"    ← {e.source_id:<26} [{e.edge_type.value}]  {p.kind.value}/{p.producer}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_graph_eligible(args: argparse.Namespace) -> int:
    """Structural scheduling: which nodes have all their dependencies satisfied."""
    registry = _registry(args)
    completed = set(args.completed or [])
    eligible = registry.eligible_nodes(completed)
    payload = {"completed": sorted(completed), "eligible": eligible}
    lines = [_rule("Eligible nodes")]
    lines.append(f"  completed  {sorted(completed) or '(none)'}")
    lines.append(f"  eligible   {eligible}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_graph_unresolved(args: argparse.Namespace) -> int:
    registry = _registry(args)
    payload = registry.unresolved_dependencies()
    lines = [_rule(f"Unresolved dependencies ({len(payload)})")]
    for src, targets in payload.items():
        lines.append(f"  {src}")
        for t in targets:
            lines.append(f"      → {t}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_graph_deps(args: argparse.Namespace) -> int:
    from pipeline.api import Pipeline

    api = Pipeline(args.data_dir, corpus=args.corpus)
    did = args.declaration_id
    deps = api.dependencies(did)
    payload = {"declaration_id": did, "dependencies": deps,
               "transitive": api.registry.graph.dependencies(did, transitive=True)}
    lines = [_rule(f"Dependencies of {did} ({len(deps)})")]
    for d in deps:
        for e in api.edge_provenance(did, d):
            prov = e["provenance"]
            lines.append(f"  → {d:<26} [{e['edge_type']}]  {prov['kind']}/{prov['producer']}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_graph_reverse(args: argparse.Namespace) -> int:
    from pipeline.api import Pipeline

    api = Pipeline(args.data_dir, corpus=args.corpus)
    did = args.declaration_id
    rev = api.reverse_dependencies(did)
    payload = {"declaration_id": did, "reverse_dependencies": rev}
    lines = [_rule(f"Dependents of {did} ({len(rev)})")]
    for r in rev:
        lines.append(f"  ← {r}")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_graph_export(args: argparse.Namespace) -> int:
    from pipeline.api import Pipeline

    api = Pipeline(args.data_dir, corpus=args.corpus)
    _emit(args, {"stats": api.graph_stats(), "edges": api.edges()})
    return 0


def cmd_review_decide(args: argparse.Namespace) -> int:
    """Record a human decision, then say what it unblocks."""
    from pipeline.api import Pipeline

    api = Pipeline(args.data_dir, corpus=args.corpus)
    decision = api.apply_review(args.declaration_id, args.decision,
                                reviewer=args.reviewer, rationale=args.rationale)
    queue = api.proof_queue()
    blocked = next((b for b in queue["blocked"] if b["id"] == args.declaration_id), None)
    payload = {"decision": decision, "proof_queue": queue}
    lines = [_rule(f"{decision['status']}  {args.declaration_id}")]
    lines.append(f"  by {decision['reviewer']} · {decision['id']}")
    lines.append("")
    if args.declaration_id in queue["ready"]:
        lines.append("  Next: proof job eligible")
    elif blocked:
        lines.append(f"  Next: blocked — {blocked['reason']}")
        for b in blocked["blockers"]:
            lines.append(f"    {b}")
    else:
        lines.append("  Next: nothing further (not formalized, or already proved)")
    _emit(args, payload, "\n".join(lines))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    from pipeline.api import Pipeline

    api = Pipeline(args.data_dir, corpus=args.corpus)
    filters: dict = {}
    if args.queue:
        filters["queues"] = args.queue
    if args.limit:
        filters["limit"] = args.limit
    payload = api.review_queue(**filters)
    lines = [_rule(f"Review queue ({len(payload)})")]
    for e in payload:
        lines.append(f"  {e['queue']:<13}{e['score']:>6.1f}  {e['declaration_id']:<24}"
                     f"{e.get('trust', ''):<20}{e.get('review', '')}")
    _emit(args, payload, "\n".join(lines))
    return 0


# ---------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Reproducible textbook-to-Lean pipeline with an audit layer.",
    )
    parser.add_argument(
        "--corpus", default=None,
        help="corpus to operate on (default: the sole configured one, or pipeline.toml)",
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="artifact store root")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="ingest chapter markdown into the corpus")
    p.add_argument("chapter", nargs="*", help="chapter numbers, e.g. 3")
    p.add_argument("--all", action="store_true", help="ingest every configured chapter")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ingest-pdf", help="stage 0a: extract a PDF page range to Markdown")
    p.add_argument("pdf")
    p.add_argument("--out", required=True, help="output directory for pages and manifest")
    p.add_argument("--first", type=int, required=True)
    p.add_argument("--last", type=int, required=True)
    p.add_argument("--title", default="", help="source title, passed to the prompt")
    p.add_argument("--provider", default=None,
                   help="override the provider for this run (default: pipeline.toml)")
    p.add_argument("--model", default=None, help="overrides the prompt's default model")
    p.add_argument("--prompt-version", default=None, dest="prompt_version")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--printed-page-offset", type=int, default=None, dest="printed_page_offset")
    p.add_argument("--force", action="store_true", help="re-extract even if cached")
    p.add_argument("--plan", action="store_true", help="show what would run; call nothing")
    p.set_defaults(func=cmd_ingest_pdf)

    p = sub.add_parser("annotate", help="stage 1: annotate one chapter")
    p.add_argument("chapter")
    p.add_argument("--section", action="append", help="restrict to these sections")
    p.add_argument("--provider", default=None,
                   help="override the provider for this run (default: pipeline.toml)")
    p.add_argument("--model", default=None)
    p.add_argument("--fixtures", default=None,
                   help="answer from recorded section fixtures instead of a provider")
    p.add_argument("--write-markdown", default=None, dest="write_markdown",
                   help="also write the human-readable annotated chapter here")
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("formalize", help="stage 2: propose Lean statements")
    p.add_argument("declaration_id", nargs="*",
                   help="specific declarations; omit and pass --chapter for a whole chapter")
    p.add_argument("--chapter", default=None,
                   help="formalize every annotated declaration in this chapter")
    p.add_argument("--kind", action="append",
                   help="restrict to these source kinds (definition, theorem, ...)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true",
                   help="re-formalize declarations that already have a proposal")
    p.add_argument("--stop-on-error", action="store_true", dest="stop_on_error",
                   help="abort the run on the first failure instead of continuing")
    p.add_argument("--provider", default=None,
                   help="override the provider for this run (default: pipeline.toml)")
    p.add_argument("--model", default=None)
    p.add_argument("--fixtures", default=None, help="answer from recorded fixtures")
    p.set_defaults(func=cmd_formalize)

    p = sub.add_parser("scaffold", help="assemble proposals into a Lean module")
    p.add_argument("chapter")
    p.add_argument("--module", default=None)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_scaffold)

    p = sub.add_parser("check", help="stage 3: Lean integrity checker")
    p.add_argument("module")
    p.add_argument("--lean-root", default=None, dest="lean_root")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("check-all", help="stage 3: run all four checkers")
    p.add_argument("--module", default=None, help="Lean module for the integrity checker")
    p.add_argument("--declaration", action="append", help="restrict checkers 2-4 to these")
    p.add_argument("--lean-root", default=None, dest="lean_root")
    p.add_argument("--provider", default=None,
                   help="override the provider for this run (default: pipeline.toml)")
    p.add_argument("--model", default=None, help="override the model for this run")
    p.add_argument("--fixtures", default=None, help="directory of recorded checker fixtures")
    p.add_argument("--deterministic-only", action="store_true", dest="deterministic_only",
                   help="skip every model-backed half")
    p.add_argument("--verify-names", action="store_true", dest="verify_names",
                   help="resolve Mathlib candidate names with Lean")
    p.set_defaults(func=cmd_check_all)

    p = sub.add_parser("note", help="attach a note to a declaration")
    p.add_argument("declaration_id")
    p.add_argument("text")
    p.add_argument("--author", required=True)
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("digest", help="show a chapter digest")
    p.add_argument("chapter")
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("prompts", help="list version-controlled prompts")
    p.set_defaults(func=cmd_prompts)

    p = sub.add_parser("status", help="corpus overview")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("inspect", help="show one declaration end to end")
    p.add_argument("declaration_id")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("prove", help="stage 4: prove approved statements")
    p.add_argument("declaration_id", nargs="*")
    p.add_argument("--chapter", default=None)
    p.add_argument("--provider", default=None,
                   help="override the provider for this run (default: pipeline.toml)")
    p.add_argument("--model", default=None)
    p.add_argument("--fixtures", default=None, help="directory of recorded proofs")
    p.add_argument("--lean-root", default=None, dest="lean_root")
    p.add_argument("--max-attempts", type=int, default=3, dest="max_attempts")
    p.add_argument("--allow-unapproved", action="store_true", dest="allow_unapproved",
                   help="bypass the approval gate (development only)")
    p.set_defaults(func=cmd_prove)

    p = sub.add_parser("ready", help="show the proof queue and why declarations are blocked")
    p.add_argument("--chapter", default=None)
    p.set_defaults(func=cmd_ready)

    p = sub.add_parser("blueprint", help="stage 5: project into Blueprint artifacts")
    p.add_argument("chapter")
    p.add_argument("--out", default="data/blueprint")
    p.add_argument("--include-unapproved", action="store_true", dest="include_unapproved")
    p.set_defaults(func=cmd_blueprint)

    p = sub.add_parser("providers", help="what the pipeline can talk to on this machine")
    p.set_defaults(func=cmd_providers)

    p = sub.add_parser("corpora", help="list configured corpora (alias of `corpus list`)")
    p.set_defaults(func=cmd_corpora)

    p = sub.add_parser("corpus", help="corpus configuration and contents")
    cs = p.add_subparsers(dest="corpus_command", required=True)
    sp = cs.add_parser("list", help="every configured corpus")
    sp.set_defaults(func=cmd_corpus_list)
    sp = cs.add_parser("show", help="one corpus: metadata, divisions, counts")
    sp.add_argument("corpus_id", nargs="?", default=None)
    sp.set_defaults(func=cmd_corpus_show)
    sp = cs.add_parser("declarations", help="declarations, with stage and trust")
    sp.add_argument("--division", default=None)
    sp.add_argument("--kind", default=None)
    sp.set_defaults(func=cmd_corpus_declarations)

    p = sub.add_parser("graph", help="CorpusGraph queries (no model involved)")
    gs = p.add_subparsers(dest="graph_command", required=True)
    sp = gs.add_parser("deps", help="what a declaration depends on")
    sp.add_argument("declaration_id")
    sp.set_defaults(func=cmd_graph_deps)
    sp = gs.add_parser("reverse", help="what depends on a declaration")
    sp.add_argument("declaration_id")
    sp.set_defaults(func=cmd_graph_reverse)
    sp = gs.add_parser("node", help="one node's edges, with provenance and evidence")
    sp.add_argument("declaration_id")
    sp.set_defaults(func=cmd_graph_node)
    sp = gs.add_parser("unresolved", help="citations that resolve to no declaration")
    sp.set_defaults(func=cmd_graph_unresolved)
    sp = gs.add_parser("stats", help="graph shape, by edge type and provenance")
    sp.set_defaults(func=cmd_graph_stats)
    sp = gs.add_parser("eligible", help="nodes whose dependencies are satisfied")
    sp.add_argument("--completed", action="append")
    sp.set_defaults(func=cmd_graph_eligible)
    sp = gs.add_parser("export", help="the whole graph as JSON")
    sp.set_defaults(func=cmd_graph_export)

    p = sub.add_parser("review", help="record a human review decision")
    p.add_argument("declaration_id")
    p.add_argument("decision", choices=["APPROVED", "REJECTED", "NEEDS_REVISION"])
    p.add_argument("--reviewer", required=True)
    p.add_argument("--rationale", required=True)
    p.set_defaults(func=cmd_review_decide)

    p = sub.add_parser("queue", help="risk-prioritised review queue")
    p.add_argument("--queue", action="append",
                   choices=["BLOCKED", "REVIEW-NOW", "REVIEW-BATCH", "FYI", "DONE"])
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=cmd_queue)

    p = sub.add_parser("run", help="drive declarations through the pipeline")
    runsub = p.add_subparsers(dest="run_command", required=True)

    def _common(sp):
        sp.add_argument("--fixtures", default=None,
                        help="fixture root holding annotate/, formalize/, and optionally "
                             "check/ and prove/ — replays recorded responses offline")
        sp.add_argument("--fixture-division", default=".", dest="fixture_division",
                        help="subdirectory under <root>/annotate and <root>/formalize, "
                             "when fixtures are split per division (default: flat)")
        sp.add_argument("--provider", default=None)
        sp.add_argument("--model", default=None)
        sp.add_argument("--module", default=None, help="Lean module for the integrity checker")
        sp.add_argument("--lean-root", default=None, dest="lean_root")
        sp.add_argument("--stop-after", default="CHECKED", dest="stop_after",
                        choices=["ANNOTATED", "FORMALIZED", "CHECKED", "APPROVED", "PROVED"])

    sp = runsub.add_parser("start", help="start a new run")
    sp.add_argument("declaration_id", nargs="*")
    sp.add_argument("--run-id", default=None, dest="run_id")
    _common(sp)
    sp.set_defaults(func=cmd_run_start)

    sp = runsub.add_parser("resume", help="resume a run from persisted state")
    sp.add_argument("run_id")
    _common(sp)
    sp.set_defaults(func=cmd_run_resume)

    sp = runsub.add_parser("status", help="show a run's state and transitions")
    sp.add_argument("run_id", nargs="?")
    sp.add_argument("--events", action="store_true", help="include the event log")
    sp.set_defaults(func=cmd_run_status)

    sp = runsub.add_parser("list", help="list pipeline runs")
    sp.set_defaults(func=cmd_run_list)

    p = sub.add_parser("workers", help="the worker table: typed input/output per stage")
    p.set_defaults(func=cmd_workers)

    p = sub.add_parser("demo", help="show the committed demo artifacts (no model call)")
    p.add_argument("--into", default=None,
                   help=f"where to materialise them (default {DEFAULT_DEMO_DIR})")
    p.add_argument("--fresh", action="store_true", help="discard and re-copy the artifacts")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("agents", help="the executable agents and the prompts they load")
    p.set_defaults(func=cmd_agents)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # `pipeline demo` materialises artifacts somewhere of its own unless told otherwise, so
    # it has to distinguish "the user chose a data dir" from "the default applied".
    args.data_dir_given = args.data_dir != str(DEFAULT_DATA_DIR)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
