"""Retired stage CLI, retained for regression tests, not exposed by mathtcs.py.

Exit codes: 0 ok · 1 refused (a rule said no; the JSON says why) · 2 error (bad input,
missing tool, unexpected exception).
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from . import annotated_md, args as args_mod, context as context_mod, ids as ids_mod
from . import manifest as mf
from . import probe as probe_mod
from . import project as project_mod
from . import promote as promote_mod
from . import report as report_mod
from . import runs as runs_mod
from . import scaffold as scaffold_mod
from . import source_items
from .lean_check import check_module
from .util import MathTcsError, sha256_text, write_text_atomic

USAGE = """mathtcs.py <command> [args]
  check-file F --decl Qualified.name [--decl Other.name] [--root D] [--timeout S]
  task begin|propose|review|attempt|apply|status|abort --help
  args <stage> [tokens...]                     parse skill arguments (stage: translate|scaffold|verify|prove|run|ping)
  project detect [--root D] | init --lib L --module-prefix P [--src-dir D] [--namespace N] [--slug S] [--force]
  ids make --slug S --chapter C --kind K (--label L | --section X --ordinal N)
  source extract <file> [--slug S] [--chapter C] | ingest-text --slug S --text-file F
  annotated validate <md> [--source F] [--assign-ids] [--write] | register <md> | section <md> --id ID | skeleton --items <json> --out <md>
  manifest get ID | list [--status S] [--slug S] [--ids a,b] | set-status ID S [--note T] | set ID key.path <json>
           | lock ID --stage S [--ttl-min N] | unlock ID [--stale-min N] | stale ID... | touch ID | approve ID --by NAME
  scaffold apply <proposals.json> [--module M] [--force] [--no-check] | extract ID | module-path M | module-name --title T
  check --file F [--tag T] [--substitute ID --proof-file P] [--no-axioms] [--timeout S]
  snapshot ID [--no-check]
  probe check NAME... [--imports M,N] [--opens A,B] | tactic --file F --id ID --tactic "exact?"
  report combine ID [--rev N] | prove ID --result <json>
  promote ID (--attempt <file> | --proof <file>) [--force]
  scratch prepare ID [--from FILE]             copy the module to math-tcs/scratch/<ID>/work.lean for a prover
  context <stage> ID [--annotated <md>]
  runs record --payload <json> --started-at TS [--run-id ID]
  workflow stage [--name run.js]
Common: --at TS (ISO timestamp for history), --root D (target project root, default: detected from cwd)."""


def _flag(argv: list[str], name: str, *, default=None, boolean: bool = False):
    if name in argv:
        i = argv.index(name)
        if boolean:
            del argv[i]
            return True
        if i + 1 >= len(argv):
            raise MathTcsError(f"{name} needs a value", code=2)
        v = argv[i + 1]
        del argv[i:i + 2]
        return v
    return False if boolean else default


def _root_cfg(argv: list[str]) -> tuple[Path, dict]:
    root_arg = _flag(argv, "--root")
    root = project_mod.find_root(root_arg) if root_arg else project_mod.find_root()
    if root is None:
        raise MathTcsError("no Lean project found upward from cwd (need lean-toolchain or a lakefile)", code=2)
    return root, project_mod.load_config(root)


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=None, sort_keys=False, default=str))


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0
    cmd, rest = argv[0], list(argv[1:])
    at = _flag(rest, "--at")
    try:
        if cmd in {"check-file", "task"}:
            from .task_cli import main as task_main
            return task_main([cmd, *rest])
        if cmd == "args":
            if not rest:
                raise MathTcsError("args needs a stage", code=2)
            _out(args_mod.parse(rest[0], rest[1:]))
            return 0
        if cmd == "project":
            sub = rest.pop(0) if rest else "detect"
            if sub == "detect":
                root_arg = _flag(rest, "--root")
                _out(project_mod.detect(root_arg))
                return 0
            if sub == "init":
                root_arg = _flag(rest, "--root")
                root = project_mod.find_root(root_arg)
                if root is None:
                    raise MathTcsError("no Lean project found", code=2)
                lib = _flag(rest, "--lib")
                prefix = _flag(rest, "--module-prefix")
                if not lib or prefix is None:
                    raise MathTcsError("init needs --lib and --module-prefix", code=2)
                res = project_mod.init(root, lib=lib, module_prefix=prefix, src_dir=_flag(rest, "--src-dir", default="."),
                                       namespace=_flag(rest, "--namespace"), slug=_flag(rest, "--slug"),
                                       force=_flag(rest, "--force", boolean=True))
                _out(res)
                return 0
            raise MathTcsError(f"unknown project subcommand {sub}", code=2)
        if cmd == "ids":
            sub = rest.pop(0) if rest else "make"
            if sub == "make":
                slug, ch, kind = _flag(rest, "--slug"), _flag(rest, "--chapter"), _flag(rest, "--kind")
                label, sec, ordn = _flag(rest, "--label"), _flag(rest, "--section"), _flag(rest, "--ordinal")
                did = ids_mod.declaration_id(slug, ch, kind, label=label, section=sec, ordinal=int(ordn) if ordn else None)
                _out({"id": did, **ids_mod.parse_declaration_id(did)})
                return 0
            raise MathTcsError(f"unknown ids subcommand {sub}", code=2)
        if cmd == "source":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "extract":
                slug, ch = _flag(rest, "--slug"), _flag(rest, "--chapter")
                if not rest:
                    raise MathTcsError("source extract needs a file", code=2)
                res = source_items.extract_file(rest[0], slug=slug, chapter=ch, configured_slug=cfg["ids"].get("slug"),
                                                configured_chapter=cfg["ids"].get("chapter"))
                res["path_relative"] = os.path.relpath(res["path"], root)
                _out(res)
                return 0
            if sub == "ingest-text":
                slug = _flag(rest, "--slug")
                tf = _flag(rest, "--text-file")
                if not tf:
                    raise MathTcsError("ingest-text needs --text-file", code=2)
                text = Path(tf).read_text(encoding="utf-8")
                sha = sha256_text(text)
                name = f"{slug or 'excerpt'}-{sha[:8]}.md"
                out = root / cfg["paths"]["sources"] / name
                write_text_atomic(out, text if text.endswith("\n") else text + "\n")
                _out({"path": str(out), "relative": str(out.relative_to(root)), "sha256": sha})
                return 0
            raise MathTcsError(f"unknown source subcommand {sub}", code=2)
        if cmd == "annotated":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "validate":
                src = _flag(rest, "--source")
                assign = _flag(rest, "--assign-ids", boolean=True)
                write = _flag(rest, "--write", boolean=True)
                slug, ch = _flag(rest, "--slug"), _flag(rest, "--chapter")
                if not rest:
                    raise MathTcsError("validate needs the annotated md path", code=2)
                mdp = Path(rest[0])
                text = mdp.read_text(encoding="utf-8")
                fm, _ = annotated_md._front_matter(text)
                src_path = src or fm.get("source_path")
                src_text = Path(src_path).read_text(encoding="utf-8") if src_path and Path(src_path).exists() else None
                assignments: list[dict] = []
                if assign:
                    if src_text is None:
                        raise MathTcsError("--assign-ids needs a readable source (--source or front matter source_path)", code=2)
                    text2, assignments, errs = annotated_md.assign_ids(text, source_text=src_text, slug=slug or fm.get("slug"),
                                                                       chapter=ch or fm.get("chapter"))
                    if write and text2 != text:
                        annotated_md.write(mdp, text2)
                    text = text2
                    if errs:
                        res = annotated_md.validate(text, source_text=src_text, slug=slug, chapter=ch)
                        res["errors"] = errs + res["errors"]
                        res["ok"] = False
                        res.pop("_doc", None)
                        res["assignments"] = assignments
                        _out(res)
                        return 1
                res = annotated_md.validate(text, source_text=src_text, slug=slug, chapter=ch)
                res.pop("_doc", None)
                res["assignments"] = assignments
                res["path"] = str(mdp)
                _out(res)
                return 0 if res["ok"] else 1
            if sub == "register":
                src_override = _flag(rest, "--source")
                if not rest:
                    raise MathTcsError("register needs the annotated md path", code=2)
                mdp = Path(rest[0]).resolve()
                text = mdp.read_text(encoding="utf-8")
                fm, _ = annotated_md._front_matter(text)
                if src_override:
                    fm["source_path"] = str(Path(src_override).resolve())
                res = annotated_md.validate(text, source_text=None, slug=None, chapter=None)
                if not res["ok"]:
                    res.pop("_doc", None)
                    _out({"registered": False, "errors": res["errors"]})
                    return 1
                doc = res.pop("_doc")
                src_path = fm.get("source_path")
                src_text = Path(src_path).read_text(encoding="utf-8") if src_path and Path(src_path).exists() else None
                items = {}
                if src_text is not None:
                    for it in source_items.extract(src_text, slug=fm.get("slug"), chapter=fm.get("chapter")):
                        items[it["id"]] = it
                data = mf.load(root, cfg)
                registered = []
                for d in doc["declarations"]:
                    meta = d["meta"]
                    e = mf.ensure(data, d["id"], meta, slug=fm.get("slug"), chapter=fm.get("chapter"))
                    e["kind"] = meta.get("kind") or e.get("kind")
                    e["label"] = meta.get("label") or e.get("label")
                    it = items.get(d["id"], {})
                    loc = None
                    if src_text is not None and d["source_statement"]:
                        loc = annotated_md._locate(src_text.splitlines(), d["source_statement"])
                    e["source"] = {"path": src_path, "sha256": (sha256_text(src_text) if src_text is not None else fm.get("source_sha256")),
                                   "section": meta.get("section") or it.get("section") or (annotated_md._section_at(src_text.splitlines(), loc[0]) if loc else None),
                                   "page": meta.get("page") or it.get("page"),
                                   "lines": it.get("lines") or (list(loc) if loc else None),
                                   "statement": d["source_statement"], "proof": d["source_proof"],
                                   "excerpt_sha256": ids_mod.content_fingerprint(d["source_statement"], d["source_proof"])}
                    e["annotated"] = {"path": str(mdp.relative_to(root)) if str(mdp).startswith(str(root)) else str(mdp),
                                      "rev": int(fm.get("rev") or 1), "section_sha256": d["section_sha256"],
                                      "blocking_questions": [q.get("text") for q in (meta.get("questions") or []) if isinstance(q, dict) and q.get("blocks_formalization")]}
                    if e.get("status") in (None, "translated") or not (e.get("lean") or {}).get("path"):
                        e["status"] = "translated"
                    mf.history(e, "translated", at=at, annotated=e["annotated"]["path"])
                    registered.append({"id": d["id"], "kind": e["kind"], "label": e["label"], "status": e["status"]})
                mf.save(root, cfg, data)
                _out({"registered": registered, "count": len(registered), "annotated": str(mdp)})
                return 0
            if sub == "section":
                did = _flag(rest, "--id")
                text = Path(rest[0]).read_text(encoding="utf-8")
                sec = annotated_md.section_for(text, did)
                if sec is None:
                    raise MathTcsError(f"no section for {did}", code=1)
                _out(sec)
                return 0
            if sub == "skeleton":
                items_path, out = _flag(rest, "--items"), _flag(rest, "--out")
                ext = json.loads(Path(items_path).read_text(encoding="utf-8"))
                text = annotated_md.render_skeleton(slug=ext["slug"], chapter=ext["chapter"], title=ext["title"],
                                                    source_path=ext["path"], source_sha256=ext["sha256"], items=ext["items"])
                if out:
                    annotated_md.write(Path(out), text)
                    _out({"path": out, "items": len(ext["items"])})
                else:
                    print(text)
                return 0
            raise MathTcsError(f"unknown annotated subcommand {sub}", code=2)
        if cmd == "manifest":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "get":
                _out({"id": rest[0], **mf.get(root, cfg, rest[0])}); return 0
            if sub == "list":
                ids_f = _flag(rest, "--ids")
                _out({"declarations": mf.entries(root, cfg, status=_flag(rest, "--status"), slug=_flag(rest, "--slug"),
                                                 module=_flag(rest, "--module"), ids=ids_f.split(",") if ids_f else None)})
                return 0
            if sub == "set-status":
                _out(mf.set_status(root, cfg, rest[0], rest[1], note=_flag(rest, "--note"), at=at)); return 0
            if sub == "set":
                _out(mf.set_field(root, cfg, rest[0], rest[1], json.loads(rest[2]))); return 0
            if sub == "lock":
                ttl = _flag(rest, "--ttl-min", default="60")
                _out(mf.lock(root, cfg, rest[0], stage=_flag(rest, "--stage", default="prove"), ttl_min=int(ttl), at=at,
                             owner=_flag(rest, "--owner")))
                return 0
            if sub == "unlock":
                stale_min = _flag(rest, "--stale-min")
                _out(mf.unlock(root, cfg, rest[0], stale_min=int(stale_min) if stale_min else None)); return 0
            if sub == "stale":
                _out({"results": [mf.stale(root, cfg, d) for d in rest]}); return 0
            if sub == "touch":
                _out(mf.touch(root, cfg, rest[0], at=at)); return 0
            if sub == "approve":
                by = _flag(rest, "--by", default="human")
                rev = _flag(rest, "--rev")
                _out(mf.approve(root, cfg, rest[0], by=by, at=at, rev=int(rev) if rev else None)); return 0
            raise MathTcsError(f"unknown manifest subcommand {sub}", code=2)
        if cmd == "scaffold":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "apply":
                module = _flag(rest, "--module")
                force = _flag(rest, "--force", boolean=True)
                nocheck = _flag(rest, "--no-check", boolean=True)
                timeout = _flag(rest, "--timeout")
                res = scaffold_mod.apply(root, cfg, Path(rest[0]), module_short=module, force=force, at=at,
                                         timeout=float(timeout) if timeout else None, check=not nocheck)
                _out(res)
                return 0 if not res["failed"] else 1
            if sub == "extract":
                _out(scaffold_mod.extract(root, cfg, rest[0])); return 0
            if sub == "module-name":
                title = _flag(rest, "--title", default=(rest[0] if rest else "Module"))
                short = scaffold_mod.default_module_short(title)
                _out({"module_short": short, "module": scaffold_mod.module_name(cfg, short),
                      "path": str(scaffold_mod.module_path(root, cfg, short).relative_to(root))})
                return 0
            if sub == "module-path":
                short = rest[0]
                _out({"module": scaffold_mod.module_name(cfg, short), "path": str(scaffold_mod.module_path(root, cfg, short).relative_to(root)),
                      "namespace": cfg["lean"].get("namespace") or short})
                return 0
            raise MathTcsError(f"unknown scaffold subcommand {sub}", code=2)
        if cmd == "check":
            root, cfg = _root_cfg(rest)
            file = _flag(rest, "--file")
            if not file:
                raise MathTcsError("check needs --file", code=2)
            sub_id = _flag(rest, "--substitute")
            proof_file = _flag(rest, "--proof-file")
            substitute = None
            if sub_id:
                if not proof_file:
                    raise MathTcsError("--substitute needs --proof-file", code=2)
                substitute = {"id": sub_id, "proof": Path(proof_file).read_text(encoding="utf-8")}
            timeout = _flag(rest, "--timeout")
            tag = _flag(rest, "--tag", default=(f"check/{sub_id}" if sub_id else f"check/{Path(file).stem}"))
            kinds = {}
            for e in mf.entries(root, cfg):
                kinds[e["id"]] = e.get("kind") or "theorem"
            res = check_module(root, cfg, Path(file).resolve(), tag=tag, substitute=substitute,
                               axioms=not _flag(rest, "--no-axioms", boolean=True),
                               timeout=float(timeout) if timeout else None, kinds=kinds)
            if _flag(rest, "--brief", boolean=True):
                res = {k: res[k] for k in ("ok", "exit", "timeout", "wall_ms", "scratch", "summary", "blocks", "unattributed_errors")}
                res["blocks"] = {k: {"trust": v.get("trust"), "errors": v.get("errors"), "main": v.get("main"),
                                     "diagnostics": [{"severity": d["severity"], "line": d.get("line"), "message": d["message"][:400]} for d in v.get("diagnostics", [])]}
                                 for k, v in res["blocks"].items()}
            _out(res)
            return 0 if res["ok"] else 1
        if cmd == "snapshot":
            root, cfg = _root_cfg(rest)
            timeout = _flag(rest, "--timeout")
            _out(report_mod.snapshot(root, cfg, rest[0], at=at, timeout=float(timeout) if timeout else None,
                                     check=not _flag(rest, "--no-check", boolean=True)))
            return 0
        if cmd == "probe":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "check":
                imports = _flag(rest, "--imports")
                opens = _flag(rest, "--opens")
                timeout = _flag(rest, "--timeout")
                _out(probe_mod.check_names(root, cfg, rest, imports=imports.split(",") if imports else None,
                                           opens=opens.split(",") if opens else None, timeout=float(timeout) if timeout else None))
                return 0
            if sub == "tactic":
                file, did, tactic = _flag(rest, "--file"), _flag(rest, "--id"), _flag(rest, "--tactic")
                timeout = _flag(rest, "--timeout")
                if not (file and did and tactic):
                    raise MathTcsError("probe tactic needs --file --id --tactic", code=2)
                res = probe_mod.try_tactic(root, cfg, Path(file).resolve(), did, tactic, timeout=float(timeout) if timeout else None)
                _out(res)
                return 0 if res["ok"] else 1
            raise MathTcsError(f"unknown probe subcommand {sub}", code=2)
        if cmd == "report":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "combine":
                rev = _flag(rest, "--rev")
                _out(report_mod.combine(root, cfg, rest[0], rev=int(rev) if rev else None, at=at)); return 0
            if sub == "prove":
                result = _flag(rest, "--result")
                _out(report_mod.prove_report(root, cfg, rest[0], Path(result), at=at)); return 0
            raise MathTcsError(f"unknown report subcommand {sub}", code=2)
        if cmd == "promote":
            root, cfg = _root_cfg(rest)
            attempt, proof = _flag(rest, "--attempt"), _flag(rest, "--proof")
            timeout = _flag(rest, "--timeout")
            res = promote_mod.promote(root, cfg, rest[0], attempt_file=Path(attempt) if attempt else None,
                                      proof_file=Path(proof) if proof else None, at=at,
                                      timeout=float(timeout) if timeout else None, force=_flag(rest, "--force", boolean=True))
            _out(res)
            return 0 if res.get("promoted") else 1
        if cmd == "scratch":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "prepare":
                did = rest[0]
                entry = mf.get(root, cfg, did)
                src = _flag(rest, "--from") or (entry.get("lean") or {}).get("path")
                if not src:
                    raise MathTcsError(f"{did} has no Lean module to copy", code=1)
                srcp = Path(src) if Path(src).is_absolute() else root / src
                out = root / cfg["paths"]["scratch"] / did / "work.lean"
                write_text_atomic(out, srcp.read_text(encoding="utf-8"))
                _out({"id": did, "work": str(out), "relative": str(out.relative_to(root)), "from": str(srcp)})
                return 0
            raise MathTcsError(f"unknown scratch subcommand {sub}", code=2)
        if cmd == "context":
            root, cfg = _root_cfg(rest)
            ann = _flag(rest, "--annotated")
            stage = rest[0]
            _out({"packages": [context_mod.build(root, cfg, stage, d, annotated_path=ann) for d in rest[1:]]})
            return 0
        if cmd == "runs":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "record":
                payload = _flag(rest, "--payload")
                started = _flag(rest, "--started-at")
                if not (payload and started):
                    raise MathTcsError("runs record needs --payload and --started-at", code=2)
                _out(runs_mod.record(root, cfg, Path(payload), started_at=started, run_id=_flag(rest, "--run-id"))); return 0
            raise MathTcsError(f"unknown runs subcommand {sub}", code=2)
        if cmd == "workflow":
            sub = rest.pop(0) if rest else ""
            root, cfg = _root_cfg(rest)
            if sub == "stage":
                plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])
                _out(runs_mod.stage_workflow(root, cfg, plugin_root, name=_flag(rest, "--name", default="run.js"))); return 0
            raise MathTcsError(f"unknown workflow subcommand {sub}", code=2)
        raise MathTcsError(f"unknown command {cmd!r}\n{USAGE}", code=2)
    except MathTcsError as exc:
        _out({"error": str(exc), "code": exc.code, **({"detail": exc.detail} if exc.detail else {})})
        return exc.code
    except (IndexError, KeyError) as exc:
        _out({"error": f"missing argument ({type(exc).__name__}: {exc})", "code": 2, "usage": USAGE.splitlines()[0]})
        return 2
    except Exception as exc:  # noqa: BLE001 - report, never hide
        _out({"error": f"{type(exc).__name__}: {exc}", "code": 2, "trace": traceback.format_exc()[-2000:]})
        return 2
