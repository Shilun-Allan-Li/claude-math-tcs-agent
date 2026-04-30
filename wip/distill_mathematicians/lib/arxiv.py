"""arXiv collector — deterministic API-driven replacement for the agent's WebSearch path.

Implements the contract in distill_mathematicians/agents/arxiv-collector.md:
  - Inputs:  discipline, vertical, window, target, bias
  - Output:  YAML manifest matching the arxiv-collector schema
  - Behavior: applies the quality bar (cited >= 20 OR is_survey),
              caps surveys at ~30% of the slate, anti-pads (returns fewer
              than `target` rather than relax the gate)

Designed to be invoked from the distill-orchestrator's collect phase via Bash:

  python -m distill_mathematicians.lib.cli arxiv \
      --discipline math --vertical combinatorics --window 2015-2025 \
      --target 20 --bias mixed --output runs/<id>/manifests/arxiv.yaml

Stdlib only — no pyyaml, no requests.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# ---------- vertical → arXiv category mapping ----------
# CATALOG.md indexes verticals by MSC (math) / arXiv code (tcs); the API
# only takes arXiv categories, so the math side is mapped explicitly here.
# Multi-category verticals (e.g. abstract-algebra) issue one query per cat
# and merge results before scoring.

MATH_VERTICAL_CATEGORIES: dict[str, list[str]] = {
    "combinatorics": ["math.CO"],
    "abstract-algebra": ["math.RA", "math.GR", "math.RT"],
    "number-theory": ["math.NT"],
    "commutative-algebra": ["math.AC"],
    "algebraic-geometry": ["math.AG"],
    "linear-algebra": ["math.NA"],
    "real-analysis": ["math.CA"],
    "complex-analysis": ["math.CV"],
    "pde": ["math.AP"],
    "general-topology": ["math.GN"],
    "algebraic-topology": ["math.AT"],
    "probability": ["math.PR"],
}

TCS_VERTICAL_CATEGORIES: dict[str, list[str]] = {
    "complexity-theory": ["cs.CC"],
    "cryptography": ["cs.CR"],
    "algorithms": ["cs.DS"],
    "approximation-algorithms": ["cs.DS"],
    "randomized-algorithms": ["cs.DS"],
    "automata-and-formal-languages": ["cs.FL"],
    "coding-and-information-theory": ["cs.IT"],
    "learning-theory": ["cs.LG"],
    "logic-in-cs": ["cs.LO"],
}

ARXIV_API = "https://export.arxiv.org/api/query"
S2_BATCH_API = "https://api.semanticscholar.org/graph/v1/paper/batch"
ARXIV_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
USER_AGENT = "distill-mathematicians/0.1 (https://github.com/AngelaWuRX/claude-math-tcs-agent)"
ARXIV_QUERY_DELAY_S = 3.0  # arXiv API ToS asks for >=3s between queries
SURVEY_CAP_PCT = 30        # surveys earn at most this share of slots
CITATION_FLOOR = 20        # quality-bar threshold


# ---------- data ----------

@dataclass
class Paper:
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    primary_category: str
    published: str        # ISO date (yyyy-mm-dd)
    year: int
    is_survey: bool
    comment: str | None = None
    doi: str | None = None
    citation_count: int | None = None

    @property
    def s2_id(self) -> str:
        return f"ARXIV:{self.arxiv_id}"


# ---------- arXiv API ----------

def _http_get(url: str, accept: str = "application/atom+xml", timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _parse_window(window: str) -> tuple[int, int]:
    parts = window.split("-")
    if len(parts) != 2:
        raise ValueError(f"window must be like '2015-2025', got: {window}")
    start, end = int(parts[0]), int(parts[1])
    if start > end:
        raise ValueError(f"window start {start} > end {end}")
    return start, end


def _detect_survey(title: str, abstract: str, comment: str | None) -> bool:
    title_l = title.lower()
    survey_phrases = (
        "a survey of", "an introduction to", "survey on",
        "lectures on", "lecture notes on", "a tutorial on",
        ": a survey", ": an introduction", ": a tutorial",
    )
    if any(p in title_l for p in survey_phrases):
        return True
    if comment and any(w in comment.lower() for w in ("survey", "lecture notes", "tutorial")):
        return True
    abstract_l = abstract.lower()
    if abstract_l.startswith(("we survey ", "this survey ", "in this survey")):
        return True
    return False


def _parse_atom_feed(xml_bytes: bytes) -> list[Paper]:
    root = ET.fromstring(xml_bytes)
    papers: list[Paper] = []
    for entry in root.findall("a:entry", ARXIV_NS):
        id_el = entry.find("a:id", ARXIV_NS)
        title_el = entry.find("a:title", ARXIV_NS)
        summary_el = entry.find("a:summary", ARXIV_NS)
        published_el = entry.find("a:published", ARXIV_NS)
        primary_cat_el = entry.find("arxiv:primary_category", ARXIV_NS)
        comment_el = entry.find("arxiv:comment", ARXIV_NS)
        doi_el = entry.find("arxiv:doi", ARXIV_NS)

        if id_el is None or title_el is None or published_el is None:
            continue

        # id_el.text is like "http://arxiv.org/abs/2401.12345v2" — strip prefix and version.
        raw_id = (id_el.text or "").rsplit("/", 1)[-1]
        arxiv_id = raw_id.split("v")[0] if "v" in raw_id else raw_id

        published = (published_el.text or "")[:10]
        try:
            year = int(published[:4])
        except ValueError:
            continue

        title = " ".join((title_el.text or "").split())
        abstract = " ".join((summary_el.text or "").split()) if summary_el is not None else ""
        primary_category = (
            primary_cat_el.attrib.get("term", "") if primary_cat_el is not None else ""
        )
        comment = comment_el.text.strip() if comment_el is not None and comment_el.text else None
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

        authors: list[str] = []
        for au in entry.findall("a:author", ARXIV_NS):
            name = au.find("a:name", ARXIV_NS)
            if name is not None and name.text:
                authors.append(name.text.strip())

        papers.append(Paper(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            abstract=abstract,
            primary_category=primary_category,
            published=published,
            year=year,
            is_survey=_detect_survey(title, abstract, comment),
            comment=comment,
            doi=doi,
        ))
    return papers


def build_keyword_clause(keywords: list[str]) -> str:
    """Build (abs:K1 OR ti:K1 OR abs:K2 OR ti:K2 ...) for the arXiv query.

    Multi-word phrases are quoted so arXiv treats them as a phrase, not AND.
    """
    if not keywords:
        return ""
    parts: list[str] = []
    for kw in keywords:
        quoted = f'"{kw}"' if " " in kw else kw
        parts.append(f"abs:{quoted}")
        parts.append(f"ti:{quoted}")
    return "(" + " OR ".join(parts) + ")"


def fetch_arxiv_category(
    category: str,
    start_year: int,
    end_year: int,
    keywords: list[str] | None = None,
    page_size: int = 200,
    max_results: int = 600,
    verbose: bool = False,
) -> list[Paper]:
    """Page through arXiv API for one category within window, optionally
    restricted to papers whose title or abstract contains any of `keywords`."""
    out: list[Paper] = []
    seen: set[str] = set()
    start = 0
    while start < max_results:
        # arXiv submittedDate format: YYYYMMDDHHMM
        date_range = f"submittedDate:[{start_year}01010000 TO {end_year}12312359]"
        clauses = [f"cat:{category}", date_range]
        if keywords:
            clauses.append(build_keyword_clause(keywords))
        search_query = " AND ".join(clauses)
        params = urllib.parse.urlencode({
            "search_query": search_query,
            "start": start,
            "max_results": min(page_size, max_results - start),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
        url = f"{ARXIV_API}?{params}"
        if verbose:
            print(f"[arxiv] GET {url}", file=sys.stderr)
        try:
            xml_bytes = _http_get(url)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"[arxiv] WARN: query failed ({e}); stopping pagination", file=sys.stderr)
            break
        page = _parse_atom_feed(xml_bytes)
        if not page:
            break
        new_in_page = 0
        for p in page:
            if p.arxiv_id in seen:
                continue
            seen.add(p.arxiv_id)
            out.append(p)
            new_in_page += 1
        if new_in_page == 0:
            break
        start += page_size
        if start < max_results:
            time.sleep(ARXIV_QUERY_DELAY_S)
    return out


# ---------- Semantic Scholar citation enrichment ----------

def _s2_batch(ids: list[str], api_key: str | None, verbose: bool = False) -> dict[str, int]:
    """Return arxiv_id → citationCount for as many entries as S2 resolves."""
    if not ids:
        return {}
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["x-api-key"] = api_key
    out: dict[str, int] = {}
    # S2 batch endpoint: up to 500 ids per call, fields query string.
    CHUNK = 200
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        body = json.dumps({"ids": [f"ARXIV:{a}" for a in chunk]}).encode()
        url = f"{S2_BATCH_API}?fields=citationCount"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        if verbose:
            print(f"[s2] POST batch of {len(chunk)} ids", file=sys.stderr)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"[s2] WARN: batch failed ({e}); leaving citation counts unset", file=sys.stderr)
            continue
        # Response is a list aligned with input order; entries that don't resolve are null.
        if isinstance(data, list):
            for arxiv_id, entry in zip(chunk, data):
                if isinstance(entry, dict) and entry.get("citationCount") is not None:
                    out[arxiv_id] = int(entry["citationCount"])
        # be polite between batches
        if i + CHUNK < len(ids):
            time.sleep(1.0)
    return out


def enrich_citations(papers: list[Paper], verbose: bool = False) -> None:
    api_key = os.environ.get("S2_API_KEY")
    counts = _s2_batch([p.arxiv_id for p in papers], api_key, verbose=verbose)
    for p in papers:
        p.citation_count = counts.get(p.arxiv_id)


# ---------- scoring ----------

def qualifies(p: Paper) -> bool:
    """Quality bar from arxiv-collector.md.

    Active-practitioner condition (author has >=3 in-window papers in this category)
    is not implemented in v1 — would require an extra round-trip per author. The
    citation_count >=20 and is_survey conditions cover the common case.
    """
    if p.is_survey:
        return True
    if (p.citation_count or 0) >= CITATION_FLOOR:
        return True
    return False


def select(papers: list[Paper], target: int, bias: str) -> list[Paper]:
    qualified = [p for p in papers if qualifies(p)]
    surveys = sorted(
        (p for p in qualified if p.is_survey),
        key=lambda p: (-(p.citation_count or 0), -p.year),
    )
    research = sorted(
        (p for p in qualified if not p.is_survey),
        key=lambda p: (-(p.citation_count or 0), -p.year),
    )

    if bias == "surveys":
        ordered = surveys + research
        return ordered[:target]
    if bias == "research":
        ordered = research + surveys
        return ordered[:target]

    # mixed (default): cap surveys at SURVEY_CAP_PCT of target, fill rest with research.
    survey_cap = max(1, target * SURVEY_CAP_PCT // 100)
    pick_surveys = surveys[:survey_cap]
    remaining = target - len(pick_surveys)
    pick_research = research[:remaining]
    out = pick_surveys + pick_research
    # sort by citation count desc for stable presentation
    out.sort(key=lambda p: (-(p.citation_count or 0), -p.year))
    return out[:target]


# ---------- YAML emission ----------
# Hand-written for the fixed arxiv-collector.md schema. No pyyaml dep.

def _yaml_block_scalar(text: str, indent: int) -> str:
    """Emit a YAML literal block scalar (the `|` form) at the given indent."""
    pad = " " * indent
    body = text.strip()
    if not body:
        return f"|\n{pad}"
    lines = body.splitlines()
    return "|\n" + "\n".join(f"{pad}{ln}" for ln in lines)


def _yaml_inline_str(s: str) -> str:
    """Emit an inline (flow) string, double-quoted with minimal escaping."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _yaml_inline_list(items: list[str]) -> str:
    return "[" + ", ".join(_yaml_inline_str(i) for i in items) + "]"


def _short_summary(abstract: str, max_chars: int = 240) -> str:
    """Produce a one-sentence-ish abstract summary.

    Spec asks for "one sentence in your own words — not the verbatim abstract."
    Without an LLM in this script we can't paraphrase, so we truncate the
    arXiv abstract to first sentence (or N chars) and flag it. The extractor
    rephrases later if needed.
    """
    # take the first sentence
    text = abstract.strip()
    for sep in (". ", "? ", "! "):
        idx = text.find(sep)
        if 0 < idx < max_chars:
            return text[: idx + 1]
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _relevance_note(p: Paper) -> str:
    bits: list[str] = []
    if p.is_survey:
        bits.append("survey/exposition")
    if p.citation_count is not None:
        bits.append(f"{p.citation_count} citations")
    else:
        bits.append("citation count unavailable")
    bits.append(f"primary category {p.primary_category or 'unknown'}")
    bits.append(f"published {p.published}")
    return "; ".join(bits) + "."


def render_manifest(
    discipline: str,
    vertical: str,
    window: str,
    selected: list[Paper],
) -> str:
    today = _dt.date.today().isoformat()
    lines: list[str] = [
        "agent: arxiv-collector",
        f"generated: {today}",
        f"discipline: {discipline}",
        f"vertical: {vertical}",
        f"window: {window}",
        "sources:",
    ]
    if not selected:
        lines.append("  []  # no papers cleared the quality bar")
        return "\n".join(lines) + "\n"

    for p in selected:
        url = f"https://arxiv.org/abs/{p.arxiv_id}"
        cat_field = p.primary_category or ""
        cit = "null" if p.citation_count is None else str(p.citation_count)
        lines.append(f"  - type: arxiv")
        lines.append(f"    id: {p.arxiv_id}")
        lines.append(f"    url: {url}")
        lines.append(f"    title: {_yaml_inline_str(p.title)}")
        lines.append(f"    authors: {_yaml_inline_list(p.authors)}")
        lines.append(f"    year: {p.year}")
        lines.append(f"    primary_category: {cat_field}")
        lines.append(f"    msc_or_arxiv_cat: {cat_field}")
        lines.append(f"    citation_count: {cit}")
        lines.append(f"    is_survey: {'true' if p.is_survey else 'false'}")
        lines.append(f"    abstract_summary: {_yaml_block_scalar(_short_summary(p.abstract), 6)}")
        lines.append(f"    relevance_note: {_yaml_block_scalar(_relevance_note(p), 6)}")
    return "\n".join(lines) + "\n"


# ---------- entrypoint ----------

def resolve_categories(discipline: str, vertical: str) -> list[str]:
    if discipline == "math":
        cats = MATH_VERTICAL_CATEGORIES.get(vertical)
    elif discipline == "tcs":
        cats = TCS_VERTICAL_CATEGORIES.get(vertical)
    else:
        raise ValueError(f"discipline must be 'math' or 'tcs', got: {discipline}")
    if not cats:
        known = sorted(
            MATH_VERTICAL_CATEGORIES if discipline == "math" else TCS_VERTICAL_CATEGORIES
        )
        raise ValueError(
            f"unknown vertical {vertical!r} for discipline {discipline}. "
            f"Known: {', '.join(known)}"
        )
    return cats


def run(args: argparse.Namespace) -> int:
    try:
        cats = resolve_categories(args.discipline, args.vertical)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        start_year, end_year = _parse_window(args.window)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.bias not in ("surveys", "research", "mixed"):
        print(f"--bias must be surveys|research|mixed, got: {args.bias}", file=sys.stderr)
        return 2

    if args.dry_run:
        kw_part = f", keywords={args.keywords}" if args.keywords else ""
        for cat in cats:
            print(f"would query: cat={cat} window={start_year}-{end_year}{kw_part}")
        print(f"would target: {args.target} entries, bias={args.bias}")
        print(f"would write: {args.output or '<stdout>'}")
        return 0

    all_papers: list[Paper] = []
    for i, cat in enumerate(cats):
        if i > 0:
            time.sleep(ARXIV_QUERY_DELAY_S)
        page = fetch_arxiv_category(
            cat, start_year, end_year,
            keywords=args.keywords,
            max_results=max(600, args.target * 30),
            verbose=args.verbose,
        )
        if args.verbose:
            print(f"[arxiv] {cat}: {len(page)} candidates", file=sys.stderr)
        all_papers.extend(page)

    # dedup across categories (a paper can be cross-listed)
    by_id: dict[str, Paper] = {}
    for p in all_papers:
        if p.arxiv_id not in by_id:
            by_id[p.arxiv_id] = p
    pool = list(by_id.values())
    if args.verbose:
        print(f"[arxiv] dedup pool: {len(pool)} unique papers", file=sys.stderr)

    enrich_citations(pool, verbose=args.verbose)

    selected = select(pool, args.target, args.bias)
    if args.verbose:
        print(f"[arxiv] selected: {len(selected)} (target {args.target})", file=sys.stderr)
        if len(selected) < args.target:
            print(
                f"[arxiv] under-delivering — only {len(selected)} cleared the quality bar",
                file=sys.stderr,
            )

    yaml_text = render_manifest(args.discipline, args.vertical, args.window, selected)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {out_path} ({len(selected)} sources)")
    else:
        sys.stdout.write(yaml_text)
    return 0


def add_argparser(subparsers: argparse._SubParsersAction) -> None:
    sp = subparsers.add_parser("arxiv", help="Build an arXiv manifest for a batch run.")
    sp.add_argument("--discipline", required=True, choices=("math", "tcs"))
    sp.add_argument("--vertical", required=True)
    sp.add_argument("--window", required=True, help="Year range like 2015-2025.")
    sp.add_argument("--target", type=int, default=20)
    sp.add_argument("--bias", default="mixed")
    sp.add_argument("--keywords", nargs="*", default=None,
                    help="Restrict to papers whose title or abstract contains any of these "
                         "phrases. Multi-word phrases are quoted automatically.")
    sp.add_argument("--output", help="Output YAML path. Defaults to stdout.")
    sp.add_argument("--dry-run", action="store_true",
                    help="Print planned queries without hitting the network.")
    sp.add_argument("--verbose", action="store_true")
    sp.set_defaults(func=run)
