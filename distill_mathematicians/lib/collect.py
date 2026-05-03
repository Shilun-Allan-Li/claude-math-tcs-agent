"""Collect sources for distillation.

Two source kinds, both written to distill_mathematicians/manifest.json:

  arxiv:  pull recent papers in a given arxiv category (math.* or cs.*)
  great:  list canonical URLs for a great mathematician's corpus

Usage:
    python3 -m distill_mathematicians.lib.collect arxiv math.NA --n 10
    python3 -m distill_mathematicians.lib.collect great euler
    python3 -m distill_mathematicians.lib.collect list-categories

Manifest format (JSON):
    {"entries": [{"kind": "arxiv"|"great", "id": str, "tags": [arxiv-cat...], ...}]}

Idempotent on (kind, id): re-running merges instead of duplicating.
Zero external deps — stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"

# Minimal registry of historical mathematicians.
# Each source uses arxiv-style category tags so historical and modern sources share one taxonomy.
REGISTRY = {
    "euler": [
        {"title": "Opera Omnia (Euler Archive)",
         "url": "https://eulerarchive.maa.org/",
         "kind_detail": "collected_works",
         "tags": ["math.HO", "math.NT", "math.CA"]},
    ],
    "gauss": [
        {"title": "Werke (archive.org Gesammelte Werke vol. 1)",
         "url": "https://archive.org/details/werkecarlf01gausrich",
         "kind_detail": "collected_works",
         "tags": ["math.HO", "math.NT", "math.AG"]},
        {"title": "Disquisitiones Arithmeticae (English translation)",
         "url": "https://archive.org/details/disquisitionesar0000carl",
         "kind_detail": "book",
         "tags": ["math.NT"]},
    ],
    "riemann": [
        {"title": "Gesammelte Mathematische Werke",
         "url": "https://archive.org/details/gesammeltemathem0000bern",
         "kind_detail": "collected_works",
         "tags": ["math.HO", "math.CV", "math.DG"]},
    ],
    "erdos": [
        {"title": "Erdős papers (Rényi Institute archive)",
         "url": "https://users.renyi.hu/~p_erdos/",
         "kind_detail": "papers",
         "tags": ["math.CO", "math.NT"]},
    ],
    "grothendieck": [
        {"title": "Grothendieck publications (numdam)",
         "url": "https://www.numdam.org/",
         "kind_detail": "papers",
         "tags": ["math.AG", "math.CT"]},
    ],
    # --- Math greats covering remaining MSC verticals ---
    "hilbert": [
        {"title": "Gesammelte Abhandlungen (vol. 1, archive.org)",
         "url": "https://archive.org/details/gesammelteabhand01hilb",
         "kind_detail": "collected_works",
         "tags": ["math.NT", "math.AG", "math.AC", "math.LO", "math.AP"]},
    ],
    "hardy": [
        {"title": "Collected Papers of G. H. Hardy",
         "url": "https://archive.org/details/collectedpapersh0000hard",
         "kind_detail": "collected_works",
         "tags": ["math.NT", "math.CA"]},
    ],
    "kolmogorov": [
        {"title": "Selected Works of A. N. Kolmogorov",
         "url": "https://archive.org/details/selectedworksofa0000kolm",
         "kind_detail": "selected_works",
         "tags": ["math.PR", "math.LO"]},
    ],
    "noether": [
        {"title": "Gesammelte Abhandlungen (Emmy Noether)",
         "url": "https://archive.org/details/gesammelteabhand0000emmy",
         "kind_detail": "collected_works",
         "tags": ["math.RA", "math.AC"]},
    ],
    "poincare": [
        {"title": "OEuvres de Henri Poincare (vol. 1)",
         "url": "https://archive.org/details/oeuvresdehenripo01poin",
         "kind_detail": "collected_works",
         "tags": ["math.AT", "math.DG", "math.DS"]},
    ],
    # --- TCS greats covering the 9 cs.* verticals ---
    "turing": [
        {"title": "On Computable Numbers, with an Application to the Entscheidungsproblem (1936)",
         "url": "https://www.cs.virginia.edu/~robins/Turing_Paper_1936.pdf",
         "kind_detail": "paper",
         "tags": ["cs.LO", "cs.FL", "cs.CC"]},
    ],
    "shannon": [
        {"title": "A Mathematical Theory of Communication (1948)",
         "url": "https://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf",
         "kind_detail": "paper",
         "tags": ["cs.IT", "cs.CR"]},
    ],
    "knuth": [
        {"title": "The Art of Computer Programming (Knuth's TAOCP page)",
         "url": "https://cs.stanford.edu/~knuth/taocp.html",
         "kind_detail": "book_series",
         "tags": ["cs.DS"]},
    ],
    "hoare": [
        {"title": "An Axiomatic Basis for Computer Programming (1969)",
         "url": "https://www.cs.cmu.edu/~crary/819-f09/Hoare69.pdf",
         "kind_detail": "paper",
         "tags": ["cs.LO", "cs.DS"]},
    ],
    "karp": [
        {"title": "Reducibility Among Combinatorial Problems (1972)",
         "url": "https://www.cs.berkeley.edu/~luca/cs172/karp.pdf",
         "kind_detail": "paper",
         "tags": ["cs.CC", "cs.DS"]},
    ],
    "cook": [
        {"title": "The Complexity of Theorem-Proving Procedures (1971)",
         "url": "https://www.cs.toronto.edu/~sacook/homepage/1971.pdf",
         "kind_detail": "paper",
         "tags": ["cs.CC"]},
    ],
    "rabin": [
        {"title": "Probabilistic Algorithms (Rabin 1976)",
         "url": "https://www.wisdom.weizmann.ac.il/~oded/PSBookFrag/rabin76.pdf",
         "kind_detail": "paper",
         "tags": ["cs.DS", "cs.CC"]},
    ],
    "valiant": [
        {"title": "A Theory of the Learnable (1984)",
         "url": "https://web.mit.edu/6.435/www/Valiant84.pdf",
         "kind_detail": "paper",
         "tags": ["cs.LG"]},
    ],
    "yao": [
        {"title": "Probabilistic Computations: Toward a Unified Measure of Complexity (1977)",
         "url": "https://www.cs.princeton.edu/courses/archive/spring01/cs598a/papers/Yao77.pdf",
         "kind_detail": "paper",
         "tags": ["cs.DS", "cs.CC"]},
    ],
}


def cmd_arxiv(args: argparse.Namespace) -> int:
    cat = args.category
    n = args.n
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query=cat:{cat}&start=0&max_results={n}"
        "&sortBy=submittedDate&sortOrder=descending"
    )
    print(f"Fetching {n} from arxiv:{cat} ...", file=sys.stderr)
    with urllib.request.urlopen(url) as r:
        xml_bytes = r.read()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_bytes)
    entries = []
    for e in root.findall("a:entry", ns):
        link = (e.findtext("a:id", "", ns) or "").strip()
        arxiv_id = link.rsplit("/", 1)[-1] if link else ""
        if not arxiv_id:
            continue
        title = (e.findtext("a:title", "", ns) or "").strip().replace("\n", " ")
        summary = (e.findtext("a:summary", "", ns) or "").strip().replace("\n", " ")
        entries.append({
            "kind": "arxiv",
            "id": arxiv_id,
            "title": title,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            "summary": summary[:400],
            "tags": [cat],
        })
    n_added = _merge_into_manifest(entries)
    print(f"Wrote {len(entries)} entries ({n_added} new) to {MANIFEST}", file=sys.stderr)
    return 0


def cmd_great(args: argparse.Namespace) -> int:
    surname = args.surname.lower()
    if surname not in REGISTRY:
        print(f"Unknown surname: {surname}. Known: {sorted(REGISTRY)}", file=sys.stderr)
        return 1
    entries = []
    for src in REGISTRY[surname]:
        entries.append({
            "kind": "great",
            "id": f"{surname}-{src['kind_detail']}",
            "surname": surname,
            "title": src["title"],
            "url": src["url"],
            "kind_detail": src["kind_detail"],
            "tags": src["tags"],
        })
    n_added = _merge_into_manifest(entries)
    print(f"Wrote {len(entries)} entries ({n_added} new) for {surname} to {MANIFEST}", file=sys.stderr)
    return 0


def cmd_list_categories(args: argparse.Namespace) -> int:
    print("# arxiv math categories (subset)")
    print("math.AG math.AT math.CA math.CO math.CV math.DG math.DS math.FA math.GM "
          "math.GN math.GT math.HO math.IT math.LO math.MG math.MP math.NA math.NT "
          "math.OA math.OC math.PR math.QA math.RA math.RT math.SG math.SP math.ST")
    print("# arxiv tcs categories (subset)")
    print("cs.CC cs.CR cs.DS cs.DM cs.FL cs.GT cs.IT cs.LG cs.LO cs.PL")
    print("# registered great mathematicians")
    for s in sorted(REGISTRY):
        print(s)
    return 0


def _merge_into_manifest(new_entries: list[dict]) -> int:
    existing: dict[tuple[str, str], dict] = {}
    if MANIFEST.exists():
        data = json.loads(MANIFEST.read_text())
        for e in data.get("entries", []):
            existing[(e["kind"], e["id"])] = e
    n_added = 0
    for e in new_entries:
        key = (e["kind"], e["id"])
        if key not in existing:
            n_added += 1
        existing[key] = e
    out = {"entries": sorted(existing.values(), key=lambda e: (e["kind"], e["id"]))}
    MANIFEST.write_text(json.dumps(out, indent=2) + "\n")
    return n_added


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="collect", description="Collect sources for distillation.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("arxiv", help="Pull recent arxiv papers in a category.")
    pa.add_argument("category", help="arxiv category, e.g. math.NA, cs.CC")
    pa.add_argument("--n", type=int, default=10, help="number of papers (default 10)")
    pa.set_defaults(func=cmd_arxiv)

    pg = sub.add_parser("great", help="List a historical mathematician's corpus.")
    pg.add_argument("surname", help="lowercase surname, e.g. euler, gauss, riemann")
    pg.set_defaults(func=cmd_great)

    pc = sub.add_parser("list-categories", help="Show arxiv categories and registered surnames.")
    pc.set_defaults(func=cmd_list_categories)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
