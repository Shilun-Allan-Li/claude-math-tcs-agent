"""claude_prover CLI — minimal file-ops for slash commands.

Usage: python3 -m claude_prover.lib.cli <verb> [args...]

Verbs:
  archive               Move proof/* (except archive/) into proof/archive/<ts>/.
  paper-extract <path>  Prep a PDF / .tar(.gz|.bz2) / .zip / .tex paper for the formatter.

Everything else (status, outline state, marking steps done, assembly) is now
done by the agent itself with Read/Write/Glob — a separate subprocess hop
added more tokens than it saved.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROOF_DIR = Path("proof")
PAPERS_DIR = Path("papers")


def _utc_ts() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _which(*names: str) -> str | None:
    for n in names:
        path = shutil.which(n)
        if path:
            return path
    return None


def _safe_basename(path: Path) -> str:
    name = path.stem
    while True:
        new = Path(name).stem
        if new == name:
            break
        name = new
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._-") or "paper"


def cmd_archive(args: list[str]) -> int:
    if args:
        print("Usage: archive (no args)", file=sys.stderr)
        return 2
    if not PROOF_DIR.exists():
        print("No proof/ directory to archive.")
        return 0
    archive_root = PROOF_DIR / "archive"
    ts = _utc_ts()
    dest = archive_root / ts
    if dest.exists():
        print(f"Archive dest already exists: {dest}", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for entry in PROOF_DIR.iterdir():
        if entry.name == "archive":
            continue
        shutil.move(str(entry), str(dest / entry.name))
        moved += 1
    if moved == 0:
        dest.rmdir()
        print("proof/ was already empty. Nothing archived.")
        return 0
    print(f"Archived {moved} entries → {dest}")
    return 0


def cmd_paper_extract(args: list[str]) -> int:
    if len(args) != 1:
        print("Usage: paper-extract <path>", file=sys.stderr)
        return 2
    src = Path(args[0]).expanduser()
    if not src.exists():
        print(f"Path not found: {src}", file=sys.stderr)
        return 1
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    base = _safe_basename(src)
    output_md = PAPERS_DIR / f"{base}.md"
    workdir = Path(tempfile.mkdtemp(prefix="paper_extract_"))
    manifest = {
        "source": str(src),
        "temp_workdir": str(workdir),
        "output_md": str(output_md),
    }
    name_lower = src.name.lower()

    try:
        if name_lower.endswith(".pdf"):
            tool = _which("pdftotext")
            raw_path = workdir / f"{base}.txt"
            if tool:
                rc = subprocess.run(
                    [tool, "-layout", str(src), str(raw_path)],
                    capture_output=True, text=True
                ).returncode
                if rc != 0:
                    raise RuntimeError("pdftotext failed")
            else:
                tool2 = _which("pandoc")
                if not tool2:
                    print("Neither pdftotext nor pandoc found on PATH. Install poppler-utils or pandoc.", file=sys.stderr)
                    return 3
                raw_path = workdir / f"{base}.md"
                rc = subprocess.run(
                    [tool2, str(src), "-o", str(raw_path), "--wrap=none"],
                    capture_output=True, text=True
                ).returncode
                if rc != 0:
                    raise RuntimeError("pandoc failed")
            manifest["raw_text_path"] = str(raw_path)
            manifest["kind"] = "pdf"
        elif name_lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")) or name_lower.endswith(".zip"):
            if name_lower.endswith(".zip"):
                rc = subprocess.run(
                    ["unzip", "-q", str(src), "-d", str(workdir)],
                    capture_output=True, text=True
                ).returncode
            else:
                flags = "xzf" if name_lower.endswith((".tar.gz", ".tgz")) else (
                        "xjf" if name_lower.endswith(".tar.bz2") else "xf")
                rc = subprocess.run(
                    ["tar", flags, str(src), "-C", str(workdir)],
                    capture_output=True, text=True
                ).returncode
            if rc != 0:
                raise RuntimeError("archive extraction failed")
            tex_files = sorted(str(p) for p in workdir.rglob("*.tex"))
            if not tex_files:
                print(f"No .tex files found in archive. Workdir: {workdir}", file=sys.stderr)
                return 1
            main = None
            for t in tex_files:
                try:
                    head = Path(t).read_text(encoding="utf-8", errors="replace")[:4000]
                except Exception:
                    continue
                if r"\documentclass" in head:
                    main = t
                    break
            if main is None:
                for t in tex_files:
                    bn = Path(t).name.lower()
                    if bn in ("main.tex", "paper.tex", f"{base}.tex"):
                        main = t
                        break
            manifest["tex_files"] = tex_files
            manifest["main_tex"] = main
            manifest["kind"] = "archive"
        elif name_lower.endswith(".tex"):
            manifest["main_tex"] = str(src)
            manifest["tex_files"] = [str(src)]
            manifest["kind"] = "tex"
        else:
            print(f"Unsupported format. Supported: .pdf .tex .tar(.gz|.bz2) .tgz .zip", file=sys.stderr)
            return 2
    except RuntimeError as e:
        print(f"Extraction failed: {e}", file=sys.stderr)
        return 3

    print(json.dumps(manifest, indent=2))
    return 0


VERBS = {
    "archive": cmd_archive,
    "paper-extract": cmd_paper_extract,
}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]
    fn = VERBS.get(verb)
    if not fn:
        print(f"Unknown verb: {verb}. Verbs: {', '.join(sorted(VERBS))}", file=sys.stderr)
        return 2
    return fn(rest) or 0


if __name__ == "__main__":
    sys.exit(main())
