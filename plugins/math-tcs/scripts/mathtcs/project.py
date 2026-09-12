"""Target-project detection and ``math-tcs/config.json``.

The plugin never modifies the target's Lean environment: it reads ``lean-toolchain``,
the lakefile and ``lake-manifest.json``, and it only ever runs ``lake lean`` /
``lake env lean`` on files it wrote itself. ``lake update`` and ``lake build`` of the
whole project are never issued.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import util

__all__ = ["find_root", "detect", "load_config", "default_config", "init", "CONFIG_VERSION"]

CONFIG_VERSION = "config/v1"
ARTIFACT_DIR = "math-tcs"

_TOML_LIB_RE = re.compile(r"^\[\[lean_lib\]\]\s*$", re.M)
_LEAN_LIB_RE = re.compile(
    r"lean_lib\s+(?:«(?P<n1>[^»]+)»|(?P<n2>[A-Za-z_][A-Za-z0-9_.]*))\s*(?:(?:where|:=)?\s*\{(?P<body>[^}]*)\})?",
    re.S,
)
_SRCDIR_RE = re.compile(r"srcDir\s*:?=\s*\"([^\"]*)\"")
_ROOTS_RE = re.compile(r"roots\s*:?=\s*#\[([^\]]*)\]")


def find_root(start: str | os.PathLike | None = None) -> Path | None:
    """Walk up from ``start`` (default cwd) to the first directory holding ``lean-toolchain``
    or a lakefile. Returns ``None`` if there is none."""
    p = Path(start or os.getcwd()).resolve()
    for candidate in (p, *p.parents):
        if (candidate / "lean-toolchain").exists() or (candidate / "lakefile.toml").exists() or (candidate / "lakefile.lean").exists():
            return candidate
    return None


def _libs_from_toml(text: str) -> list[dict]:
    try:
        import tomllib
        data = tomllib.loads(text)
    except Exception:
        return []
    libs = []
    for entry in data.get("lean_lib", []) or []:
        libs.append({
            "name": entry.get("name"),
            "src_dir": entry.get("srcDir", "."),
            "roots": list(entry.get("roots", []) or []),
            "globs": list(entry.get("globs", []) or []),
        })
    return libs


def _libs_from_lean(text: str) -> list[dict]:
    libs = []
    for m in _LEAN_LIB_RE.finditer(text):
        name = m.group("n1") or m.group("n2")
        body = m.group("body") or ""
        src = _SRCDIR_RE.search(body)
        roots = _ROOTS_RE.search(body)
        libs.append({
            "name": name,
            "src_dir": src.group(1) if src else ".",
            "roots": [r.strip().strip("`«»") for r in roots.group(1).split(",") if r.strip()] if roots else [],
            "globs": [],
        })
    return libs


def _module_prefix_guess(root: Path, lib: dict) -> str:
    """``TCSlib`` when ``<src_dir>/TCSlib.lean`` or ``<src_dir>/TCSlib/`` exists, else ``""``
    (flat modules under ``src_dir``)."""
    name = lib.get("name") or ""
    src = root / (lib.get("src_dir") or ".")
    if name and ((src / f"{name}.lean").exists() or (src / name).is_dir()):
        return name
    return ""


def detect(root: str | os.PathLike | None = None) -> dict:
    r = find_root(root)
    if r is None:
        return {"ok": False, "error": "no Lean project found (no lean-toolchain / lakefile upward from cwd)",
                "cwd": os.getcwd()}
    lakefile = "lakefile.toml" if (r / "lakefile.toml").exists() else ("lakefile.lean" if (r / "lakefile.lean").exists() else None)
    libs: list[dict] = []
    if lakefile == "lakefile.toml":
        libs = _libs_from_toml((r / lakefile).read_text(encoding="utf-8"))
    elif lakefile == "lakefile.lean":
        libs = _libs_from_lean((r / lakefile).read_text(encoding="utf-8"))
    for lib in libs:
        lib["module_prefix_guess"] = _module_prefix_guess(r, lib)
        lib["root_file"] = f"{lib['name']}.lean" if (r / (lib.get("src_dir") or ".") / f"{lib['name']}.lean").exists() else None
    toolchain = (r / "lean-toolchain").read_text(encoding="utf-8").strip() if (r / "lean-toolchain").exists() else None
    packages: list[dict] = []
    manifest = r / "lake-manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for pkg in data.get("packages", []):
                packages.append({"name": pkg.get("name"), "rev": (pkg.get("rev") or "")[:12], "inputRev": pkg.get("inputRev")})
        except Exception:
            pass
    mathlib_built = any((r / p).exists() for p in (
        ".lake/packages/mathlib/.lake/build/lib/lean/Mathlib.olean",
        ".lake/packages/mathlib/.lake/build/lib/Mathlib.olean",
    ))
    config_path = r / ARTIFACT_DIR / "config.json"
    cfg = load_config(r) if config_path.exists() else None
    return {
        "ok": True,
        "root": str(r),
        "lakefile": lakefile,
        "toolchain": toolchain,
        "libs": libs,
        "packages": packages,
        "mathlib_built": mathlib_built,
        "config_exists": config_path.exists(),
        "config_path": str(config_path),
        "config": cfg,
    }


def default_config(*, lib: str, module_prefix: str, src_dir: str = ".", namespace: str | None = None,
                   slug: str | None = None, root_file: str | None = None, toolchain: str | None = None) -> dict:
    prefix = module_prefix.strip(".")
    return {
        "math-tcs": CONFIG_VERSION,
        "lean": {
            "lib": lib,
            "src_dir": src_dir,
            "module_prefix": prefix,
            "namespace": namespace or (prefix.split(".")[-1] if prefix else "MathTcs"),
            "check": "lake lean",
            "timeout_s": 600,
            "register_in_root": False,
            "root_file": root_file,
            "toolchain": toolchain,
        },
        "axioms": {"allow": ["propext", "Classical.choice", "Quot.sound"]},
        "prove": {"budget": 4, "max_helpers": 3, "parallel": 1},
        "ids": {"slug": slug, "chapter": None},
        "paths": {
            "dir": ARTIFACT_DIR,
            "annotated": f"{ARTIFACT_DIR}/annotated",
            "reports": f"{ARTIFACT_DIR}/reports",
            "scratch": f"{ARTIFACT_DIR}/scratch",
            "sources": f"{ARTIFACT_DIR}/sources",
            "context": f"{ARTIFACT_DIR}/context",
            "locks": f"{ARTIFACT_DIR}/locks",
            "runs": f"{ARTIFACT_DIR}/runs",
        },
    }


def load_config(root: str | os.PathLike) -> dict:
    path = Path(root) / ARTIFACT_DIR / "config.json"
    if not path.exists():
        raise util.MathTcsError(f"no config at {path}; run `mathtcs.py project init` first", code=2)
    return json.loads(path.read_text(encoding="utf-8"))


def init(root: str | os.PathLike, *, lib: str, module_prefix: str, src_dir: str = ".",
         namespace: str | None = None, slug: str | None = None, force: bool = False) -> dict:
    r = Path(root)
    det = detect(r)
    if not det.get("ok"):
        raise util.MathTcsError(det["error"], code=2)
    art = r / ARTIFACT_DIR
    cfg_path = art / "config.json"
    if cfg_path.exists() and not force:
        return {"ok": True, "created": False, "config_path": str(cfg_path), "config": load_config(r)}
    root_file = None
    for l in det["libs"]:
        if l["name"] == lib and l.get("root_file"):
            root_file = l["root_file"]
    cfg = default_config(lib=lib, module_prefix=module_prefix, src_dir=src_dir, namespace=namespace,
                         slug=slug, root_file=root_file, toolchain=det.get("toolchain"))
    for sub in cfg["paths"].values():
        (r / sub).mkdir(parents=True, exist_ok=True)
    util.write_json_atomic(cfg_path, cfg)
    manifest_path = art / "manifest.json"
    if not manifest_path.exists():
        util.write_json_atomic(manifest_path, {"math-tcs": "manifest/v1", "declarations": {}})
    gi = art / ".gitignore"
    if not gi.exists():
        gi.write_text("scratch/\nlocks/\ncontext/\n", encoding="utf-8")
    return {"ok": True, "created": True, "config_path": str(cfg_path), "config": cfg}
