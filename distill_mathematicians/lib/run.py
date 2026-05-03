"""Queue manager for the distillation pipeline.

Reads distill_mathematicians/manifest.json and reports what's pending.
The user invokes /distill in claude to dispatch the next item.

Two queues:
  pending_distill — sources in manifest with no corresponding distilled/<id>.md
  pending_skill   — distilled files with no skill citing their id

Usage:
    python3 -m distill_mathematicians.lib.run         # show queue
    python3 -m distill_mathematicians.lib.run --next  # print next pending item only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
DISTILLED = ROOT / "distilled"
SKILLS = ROOT.parent / "skills"


def _load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    data = json.loads(MANIFEST.read_text())
    return data.get("entries", [])


def _distilled_ids() -> set[str]:
    if not DISTILLED.exists():
        return set()
    # Distilled files live under distilled/<area>/<vertical>/<id>.md.
    # rglob picks them up regardless of depth (also tolerates legacy flat layout).
    return {p.stem for p in DISTILLED.rglob("*.md")}


def _skilled_source_ids() -> set[str]:
    """Return source ids that already have a skill citing them via `Source: <id>`."""
    if not SKILLS.exists():
        return set()
    ids: set[str] = set()
    for p in SKILLS.rglob("*.md"):
        try:
            for line in p.read_text(errors="replace").splitlines():
                line = line.strip()
                if line.lower().startswith("source:"):
                    rest = line.split(":", 1)[1].strip()
                    sid = rest.split()[0] if rest else ""
                    if sid:
                        ids.add(sid)
        except Exception:
            continue
    return ids


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--next", action="store_true", help="print only the next pending item")
    args = p.parse_args(argv)

    entries = _load_manifest()
    distilled = _distilled_ids()
    skilled = _skilled_source_ids()

    pending_distill = [e for e in entries if e["id"] not in distilled]
    pending_skill = sorted(distilled - skilled)

    if args.next:
        if pending_distill:
            print(f"distill {pending_distill[0]['id']}")
        elif pending_skill:
            print(f"skill {pending_skill[0]}")
        else:
            print("none")
        return 0

    print(f"Sources in manifest:        {len(entries)}")
    print(f"Distilled:                  {len(distilled)}")
    print(f"Skills referencing sources: {len(skilled)}")
    print()
    print(f"Pending distillation: {len(pending_distill)}")
    for e in pending_distill[:5]:
        print(f"  - {e['id']}  ({e['kind']}, tags={','.join(e.get('tags', []))})")
    if len(pending_distill) > 5:
        print(f"  ... +{len(pending_distill) - 5} more")
    print()
    print(f"Pending skill creation: {len(pending_skill)}")
    for sid in pending_skill[:5]:
        print(f"  - {sid}")
    if len(pending_skill) > 5:
        print(f"  ... +{len(pending_skill) - 5} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
