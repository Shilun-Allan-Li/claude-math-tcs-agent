#!/usr/bin/env python3
"""Stop hook: compress oldest archive dirs when proof/archive/ grows large.

Looks for proof/archive/ in the current working directory. If more than
KEEP timestamped subdirectories exist, tars+gzips the oldest down to KEEP.
Original dirs are removed only after the tarball is created.

Best-effort: any error swallowed (exit 0) so session shutdown is never
blocked by a hook bug.
"""

import re
import shutil
import sys
import tarfile
from pathlib import Path

KEEP = 10
TS_DIR = re.compile(r"^\d{8}T\d{6}Z$")


def run() -> None:
    archive = Path.cwd() / "proof" / "archive"
    if not archive.is_dir():
        return
    # Only consider timestamped archive dirs — leave subdirs like reviews/ alone.
    dirs = sorted(d for d in archive.iterdir() if d.is_dir() and TS_DIR.match(d.name))
    if len(dirs) <= KEEP:
        return
    to_compress = dirs[: len(dirs) - KEEP]
    for d in to_compress:
        tarball = archive / f"{d.name}.tar.gz"
        if tarball.exists():
            continue
        with tarfile.open(tarball, "w:gz") as tf:
            tf.add(d, arcname=d.name)
        shutil.rmtree(d)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        pass
    sys.exit(0)
