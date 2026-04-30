"""Corpus collector — deterministic seed-and-augment replacement for individual-pack search.

Implements the contract in distill_mathematicians/agents/corpus-collector.md:
  - Inputs:  surname, [include_secondary], target_primary, target_secondary
  - Output:  YAML manifest matching the corpus-collector schema
  - Behavior: emits a per-surname *curated registry* of canonical anchors (the
              well-known repositories the agent was previously expected to know),
              then augments via the archive.org advancedsearch API filtered by
              creator name. Unknown surnames abort — the agent spec says "do not
              invent canonical repository URLs", and this script obeys it.

CLI: python -m distill_mathematicians.lib.cli corpus \
        --surname euler --target-primary 8 --target-secondary 4 \
        --output runs/<id>/manifests/corpus.yaml

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = "distill-mathematicians/0.1 (https://github.com/AngelaWuRX/claude-math-tcs-agent)"
ARCHIVE_API = "https://archive.org/advancedsearch.php"
ARCHIVE_DETAILS = "https://archive.org/details"


# ---------- per-surname registry ----------
# Curated anchors for each scaffolded surname under sources/heuristic_mind/.
# "Anchors" are canonical landing pages known to host the mathematician's
# primary corpus. The script does NOT invent URLs — only those that have
# been verified as long-standing canonical hosts appear here.
#
# `creator_names`: forms used by archive.org for the same person. The
#   advancedsearch API does substring matching; including multiple forms
#   widens recall without hurting precision (we filter again at scoring).
#
# `anchors`: hand-curated entries that get emitted as primary by default.
# `secondary_anchors`: hand-curated biographies/expositions emitted when
#   include_secondary=True.

@dataclass
class Anchor:
    tier: str             # primary | secondary
    type: str             # collected_works | book | paper | letter | lecture | biography | exposition
    repo: str             # eulerarchive | archive.org | gutenberg | numdam | grothendieck-circle | ihes | other
    url: str
    title: str
    year_published: int | None = None
    year_written: int | None = None
    language: str = "unknown"
    translation: str | None = None
    translation_url: str | None = None
    coverage: str = ""
    relevance_note: str = ""


REGISTRY: dict[str, dict] = {
    "euler": {
        "creator_names": ["Euler, Leonhard", "Leonhard Euler", "Euler, L."],
        "anchors": [
            Anchor(
                tier="primary", type="collected_works", repo="eulerarchive",
                url="https://scholarlycommons.pacific.edu/euler/",
                title="The Euler Archive (Opera Omnia index)",
                year_published=2002, language="latin",
                translation="english", translation_url=None,
                coverage="Indexed primary corpus: Opera Omnia and individual papers, with English summaries and many full translations.",
                relevance_note="Canonical online index of Euler's primary works. Earns primary slot as the master pointer to Opera Omnia.",
            ),
        ],
        "secondary_anchors": [],
    },
    "gauss": {
        "creator_names": ["Gauss, Carl Friedrich", "Carl Friedrich Gauss", "Gauss, C. F."],
        "anchors": [
            Anchor(
                tier="primary", type="collected_works", repo="archive.org",
                url="https://archive.org/details/werkecarlf01gausrich",
                title="Werke (Königliche Gesellschaft der Wissenschaften zu Göttingen edition)",
                year_published=1863, language="latin",
                translation=None,
                coverage="The Göttingen Werke edition of Gauss's collected works (multi-volume; this entry points to volume I; further volumes share the identifier prefix).",
                relevance_note="Standard scholarly edition of Gauss. Latin originals; some German. Earns primary slot.",
            ),
        ],
        "secondary_anchors": [],
    },
    "riemann": {
        "creator_names": ["Riemann, Bernhard", "Bernhard Riemann"],
        "anchors": [
            Anchor(
                tier="primary", type="collected_works", repo="archive.org",
                url="https://archive.org/details/gesammeltemathe00rieme",
                title="Gesammelte mathematische Werke und wissenschaftlicher Nachlass",
                year_published=1876, language="german",
                translation=None,
                coverage="Riemann's complete mathematical works and scientific Nachlass (Weber edition).",
                relevance_note="Canonical edition of Riemann's writings. Earns primary slot.",
            ),
        ],
        "secondary_anchors": [],
    },
    "grothendieck": {
        "creator_names": ["Grothendieck, Alexander", "Alexander Grothendieck", "Grothendieck, A."],
        "anchors": [
            Anchor(
                tier="primary", type="book", repo="numdam",
                url="https://www.numdam.org/journals/PMIHES/",
                title="Éléments de géométrie algébrique (EGA) — Publications mathématiques de l'IHÉS",
                year_published=1960, language="french",
                translation=None,
                coverage="EGA I–IV, foundational treatise on algebraic geometry, originally serialized in PMIHÉS.",
                relevance_note="Primary technical corpus. The numdam host is the canonical open-access mirror of PMIHÉS.",
            ),
            Anchor(
                tier="primary", type="lecture", repo="other",
                url="https://agrothendieck.github.io/",
                title="Grothendieck Circle archive (correspondence, Récoltes et Semailles, SGA notes)",
                year_published=None, language="french",
                translation="english", translation_url=None,
                coverage="Correspondence, manuscripts, autobiographical Récoltes et Semailles, and SGA seminar notes.",
                relevance_note="Heuristic-mind material — the writings where Grothendieck explicitly discusses method.",
            ),
        ],
        "secondary_anchors": [],
    },
    "erdos": {
        "creator_names": ["Erdős, Paul", "Paul Erdős", "Erdos, Paul", "Erdős, P.", "Erdos, P."],
        "anchors": [
            Anchor(
                tier="primary", type="paper", repo="other",
                url="https://users.renyi.hu/~p_erdos/Erdos.html",
                title="Bibliography of Paul Erdős (Rényi Institute)",
                year_published=None, language="english",
                translation=None,
                coverage="Comprehensive bibliography pointing to ~1500 Erdős papers across number theory, combinatorics, graph theory, set theory.",
                relevance_note="Canonical bibliography host. Earns primary slot as the master pointer; individual papers are reached through it.",
            ),
        ],
        "secondary_anchors": [],
    },
}


# ---------- archive.org augmentation ----------

@dataclass
class ArchiveItem:
    identifier: str
    title: str
    creator: str
    year: int | None
    language: str | None
    mediatype: str

    @property
    def url(self) -> str:
        return f"{ARCHIVE_DETAILS}/{self.identifier}"


def archive_search(creator_names: list[str], rows: int = 50, verbose: bool = False) -> list[ArchiveItem]:
    """Query archive.org advancedsearch for texts authored by any creator-name variant."""
    creator_clauses = " OR ".join(f'creator:"{n}"' for n in creator_names)
    q = f"({creator_clauses}) AND mediatype:texts"
    params = [
        ("q", q),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "creator"),
        ("fl[]", "year"),
        ("fl[]", "language"),
        ("fl[]", "mediatype"),
        ("rows", str(rows)),
        ("output", "json"),
    ]
    url = f"{ARCHIVE_API}?{urllib.parse.urlencode(params, doseq=True)}"
    if verbose:
        print(f"[archive] GET {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[archive] WARN: search failed ({e}); proceeding with anchors only", file=sys.stderr)
        return []
    docs = payload.get("response", {}).get("docs", [])
    out: list[ArchiveItem] = []
    for d in docs:
        title = d.get("title") or ""
        if isinstance(title, list):
            title = title[0] if title else ""
        creator = d.get("creator") or ""
        if isinstance(creator, list):
            creator = "; ".join(creator)
        lang = d.get("language")
        if isinstance(lang, list):
            lang = lang[0] if lang else None
        year_raw = d.get("year")
        year: int | None = None
        if year_raw:
            try:
                year = int(str(year_raw)[:4])
            except (ValueError, TypeError):
                year = None
        out.append(ArchiveItem(
            identifier=d.get("identifier", ""),
            title=title.strip(),
            creator=creator.strip(),
            year=year,
            language=(lang or "").lower() or None,
            mediatype=d.get("mediatype", "texts"),
        ))
    return out


# ---------- scoring archive.org results ----------

CANONICAL_TITLE_TOKENS = (
    "werke", "opera", "collected works", "gesammelte", "œuvres", "oeuvres",
    "correspondence", "correspondance", "briefe", "letters",
    "complete works", "selected papers", "selected works",
    "vorlesungen", "lectures",
)

EXCLUDE_TITLE_TOKENS = (
    # Drop reposts of fragments / single-page scans / review materials
    "review of", "abstracts of", "errata", "appendix to",
)


def archive_quality(item: ArchiveItem, surname: str) -> tuple[int, str]:
    """Return (score, reason). Higher score = better. 0 = drop."""
    title_l = item.title.lower()
    if not item.title or not item.identifier:
        return 0, "missing title or identifier"
    if any(tok in title_l for tok in EXCLUDE_TITLE_TOKENS):
        return 0, "title indicates fragment / review"
    # require creator match (substring of any creator-name variant)
    creator_l = item.creator.lower()
    if surname.lower() not in creator_l:
        return 0, f"creator {item.creator!r} does not include surname"
    score = 0
    matched = ""
    for tok in CANONICAL_TITLE_TOKENS:
        if tok in title_l:
            score += 10
            matched = tok
            break
    # title-length sanity: ultra-short titles ("misc", "ms", numeric) are usually noise
    if len(item.title.strip()) <= 4:
        return 0, "title too short — likely fragment"
    # tier hint by score: >=10 → strong primary candidate, else weak/secondary
    return score, f"matched canonical token {matched!r}" if matched else "generic creator match"


def archive_to_anchor(item: ArchiveItem, score: int, reason: str) -> Anchor:
    tier = "primary" if score >= 10 else "secondary"
    a_type = "collected_works" if score >= 10 else "book"
    return Anchor(
        tier=tier,
        type=a_type,
        repo="archive.org",
        url=item.url,
        title=item.title,
        year_published=item.year,
        year_written=None,
        language=item.language or "unknown",
        translation=None,
        translation_url=None,
        coverage=(
            f"archive.org scan; canonical-token match: {reason}."
            if score >= 10 else f"archive.org scan; {reason}."
        ),
        relevance_note=(
            "Discovered via archive.org creator-name search; "
            "title suggests canonical edition." if score >= 10 else
            "Discovered via archive.org creator-name search; "
            "weaker signal — verify before relying on as primary."
        ),
    )


# ---------- selection ----------

def select(
    anchors: list[Anchor],
    augmented: list[Anchor],
    include_secondary: bool,
    target_primary: int,
    target_secondary: int,
) -> list[Anchor]:
    seen_urls: set[str] = set()
    primaries: list[Anchor] = []
    secondaries: list[Anchor] = []

    def push(a: Anchor) -> None:
        if a.url in seen_urls:
            return
        seen_urls.add(a.url)
        if a.tier == "primary":
            primaries.append(a)
        else:
            secondaries.append(a)

    # curated anchors first; they are higher-confidence than augmented results.
    for a in anchors:
        push(a)
    for a in augmented:
        push(a)

    out = primaries[:target_primary]
    if include_secondary:
        out += secondaries[:target_secondary]
    return out


# ---------- YAML emission ----------

def _yaml_block_scalar(text: str, indent: int) -> str:
    pad = " " * indent
    body = text.strip()
    if not body:
        return f"|\n{pad}"
    return "|\n" + "\n".join(f"{pad}{ln}" for ln in body.splitlines())


def _yaml_inline_str(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _opt_int(n: int | None) -> str:
    return "null" if n is None else str(n)


def _opt_str(s: str | None) -> str:
    return "null" if s is None else _yaml_inline_str(s)


def render_manifest(surname: str, selected: list[Anchor]) -> str:
    today = _dt.date.today().isoformat()
    lines: list[str] = [
        "agent: corpus-collector",
        f"generated: {today}",
        f"surname: {surname}",
        "sources:",
    ]
    if not selected:
        lines.append("  []  # no entries — registry empty and archive.org returned no usable matches")
        return "\n".join(lines) + "\n"
    for a in selected:
        lines.append(f"  - tier: {a.tier}")
        lines.append(f"    type: {a.type}")
        lines.append(f"    repo: {a.repo}")
        lines.append(f"    url: {a.url}")
        lines.append(f"    title: {_yaml_inline_str(a.title)}")
        lines.append(f"    year_published: {_opt_int(a.year_published)}")
        lines.append(f"    year_written: {_opt_int(a.year_written)}")
        lines.append(f"    language: {a.language}")
        lines.append(f"    translation: {_opt_str(a.translation)}")
        lines.append(f"    translation_url: {_opt_str(a.translation_url)}")
        lines.append(f"    coverage: {_yaml_block_scalar(a.coverage, 6)}")
        lines.append(f"    relevance_note: {_yaml_block_scalar(a.relevance_note, 6)}")
    return "\n".join(lines) + "\n"


# ---------- entrypoint ----------

def run(args: argparse.Namespace) -> int:
    surname = args.surname.strip().lower()
    if surname not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        print(
            f"unknown surname {surname!r}. Registry has: {known}.\n"
            f"To add a new surname, edit distill_mathematicians/lib/corpus.py REGISTRY "
            f"with verified canonical-repo anchors. The corpus-collector agent spec forbids "
            f"inventing URLs, so this script will not guess.",
            file=sys.stderr,
        )
        return 1

    entry = REGISTRY[surname]
    curated_primaries: list[Anchor] = list(entry.get("anchors", []))
    curated_secondaries: list[Anchor] = list(entry.get("secondary_anchors", []))

    if args.dry_run:
        print(f"would emit {len(curated_primaries)} curated primary anchor(s)")
        print(f"would emit {len(curated_secondaries)} curated secondary anchor(s)")
        print(f"would query archive.org for creator: {entry['creator_names']}")
        print(f"would write: {args.output or '<stdout>'}")
        return 0

    augmented: list[Anchor] = []
    if not args.skip_augment:
        items = archive_search(entry["creator_names"], rows=args.augment_rows, verbose=args.verbose)
        if args.verbose:
            print(f"[corpus] archive.org returned {len(items)} candidates", file=sys.stderr)
        for it in items:
            score, reason = archive_quality(it, surname)
            if score == 0:
                continue
            augmented.append(archive_to_anchor(it, score, reason))
        if args.verbose:
            print(f"[corpus] archive.org kept {len(augmented)} after quality scoring", file=sys.stderr)

    all_anchors = curated_primaries + curated_secondaries
    selected = select(
        anchors=all_anchors,
        augmented=augmented,
        include_secondary=args.include_secondary,
        target_primary=args.target_primary,
        target_secondary=args.target_secondary,
    )

    primaries_n = sum(1 for a in selected if a.tier == "primary")
    secondaries_n = sum(1 for a in selected if a.tier == "secondary")
    if args.verbose:
        print(
            f"[corpus] selected: {primaries_n} primary, {secondaries_n} secondary "
            f"(targets: {args.target_primary}/{args.target_secondary})",
            file=sys.stderr,
        )
        if primaries_n < args.target_primary:
            print(
                f"[corpus] under-delivering on primaries — registry + augment yielded {primaries_n}",
                file=sys.stderr,
            )

    yaml_text = render_manifest(surname, selected)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {out} ({len(selected)} sources)")
    else:
        sys.stdout.write(yaml_text)
    return 0


def add_argparser(subparsers: argparse._SubParsersAction) -> None:
    sp = subparsers.add_parser("corpus", help="Build a corpus-collector manifest for an individual run.")
    sp.add_argument("--surname", required=True,
                    help=f"Surname slug. Known: {', '.join(sorted(REGISTRY))}")
    sp.add_argument("--include-secondary", action="store_true", default=True,
                    help="Emit secondary tier (biographies, expositions). Default true.")
    sp.add_argument("--no-include-secondary", dest="include_secondary", action="store_false")
    sp.add_argument("--target-primary", type=int, default=8)
    sp.add_argument("--target-secondary", type=int, default=4)
    sp.add_argument("--augment-rows", type=int, default=50,
                    help="archive.org rows to fetch before scoring.")
    sp.add_argument("--skip-augment", action="store_true",
                    help="Emit only curated registry anchors; skip archive.org search.")
    sp.add_argument("--output", help="Output YAML path. Defaults to stdout.")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--verbose", action="store_true")
    sp.set_defaults(func=run)
