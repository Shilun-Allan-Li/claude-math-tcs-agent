"""Verb: index-source — extract text from a source and chunk it for downstream use.

Supported kinds:
    pdf  — uses `pdftotext` (poppler-utils) if installed, else returns error
    tex  — read as text, strip simple LaTeX comments
    tar  — extract via tarfile module, concatenate .tex/.md/.txt files
    repo — git clone (local file:// or remote URL), walk for source files

URLs are accepted only for `kind=repo` (treated as a git remote). For
PDF/TeX/tar, pass a local path.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
from pathlib import Path

from audit import ARTIFACTS, ROOT

CHUNK_CHARS = 3500  # ~1000 tokens at 3.5 chars/token

CODE_EXT = {".py", ".cpp", ".c", ".h", ".hpp", ".rs", ".go", ".tex", ".md", ".txt"}


def run(args: dict, request_id: str) -> dict:
    """args: {"path": str | "url": str, "kind": "pdf"|"tex"|"tar"|"repo"}"""
    kind = args.get("kind")
    path = args.get("path")
    url = args.get("url")
    if kind not in ("pdf", "tex", "tar", "repo"):
        raise ValueError(f"unknown kind: {kind}")
    if not path and not url:
        raise ValueError("must provide either 'path' or 'url'")

    artifact_dir = ARTIFACTS / request_id
    files_out = artifact_dir / "files_out"
    files_out.mkdir(exist_ok=True)

    if kind == "pdf":
        text = _extract_pdf(_resolve_path(path))
    elif kind == "tex":
        text = _strip_tex(_resolve_path(path).read_text(errors="replace"))
    elif kind == "tar":
        text = _extract_tar(_resolve_path(path), artifact_dir)
    elif kind == "repo":
        text = _extract_repo(url or path, artifact_dir)

    chunks = _chunk(text, CHUNK_CHARS)
    for i, chunk in enumerate(chunks, 1):
        (files_out / f"chunk_{i:03d}.txt").write_text(chunk)

    return {
        "kind": kind,
        "n_chunks": len(chunks),
        "char_count": len(text),
        "summary": _summary(text),
    }


def _resolve_path(p: str | None) -> Path:
    if not p:
        raise ValueError("missing required field: path")
    path = Path(p)
    if not path.is_absolute():
        path = (ROOT / p).resolve()
    if not path.is_file() and not path.is_dir():
        raise FileNotFoundError(f"not found: {path}")
    return path


def _extract_pdf(path: Path) -> str:
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext not installed (brew install poppler / apt install poppler-utils)")
    proc = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {proc.stderr.strip()}")
    return proc.stdout


def _strip_tex(text: str) -> str:
    # Strip line-leading comments only; leave inline % alone (might be escaped).
    return re.sub(r"^\s*%.*$", "", text, flags=re.MULTILINE)


def _extract_tar(path: Path, artifact_dir: Path) -> str:
    extract_dir = artifact_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)
    with tarfile.open(path) as tf:
        tf.extractall(extract_dir, filter="data")
    return _concat_source_files(extract_dir)


def _extract_repo(url: str, artifact_dir: Path) -> str:
    if not shutil.which("git"):
        raise RuntimeError("git not installed")
    clone_dir = artifact_dir / "repo"
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(clone_dir)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {proc.stderr.strip()}")
    return _concat_source_files(clone_dir)


def _concat_source_files(root: Path) -> str:
    parts = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix in CODE_EXT:
            try:
                parts.append(f"# === {f.relative_to(root)} ===\n{f.read_text(errors='replace')}\n")
            except Exception:
                pass
    return "\n".join(parts)


def _chunk(text: str, n: int) -> list[str]:
    if not text:
        return []
    return [text[i:i + n] for i in range(0, len(text), n)]


def _summary(text: str) -> str:
    # First non-empty 2-3 lines, truncated.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = " ".join(lines[:3])
    return (head[:300] + "...") if len(head) > 300 else head
