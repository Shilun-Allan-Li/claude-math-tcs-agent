"""Small shared helpers: errors, atomic JSON writes, hashing, timestamps passed in."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


class MathTcsError(Exception):
    """A refusal or failure with a process exit code (1 = refused, 2 = error)."""

    def __init__(self, message: str, *, code: int = 1, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def write_json_atomic(path: str | os.PathLike, data: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_text_atomic(path: str | os.PathLike, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: str | os.PathLike) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rel(root: str | os.PathLike, path: str | os.PathLike) -> str:
    """Project-relative path string (posix)."""
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()
