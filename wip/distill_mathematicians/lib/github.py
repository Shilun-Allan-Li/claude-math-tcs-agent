"""GitHub curator — deterministic API-driven replacement for the agent's WebSearch path.

Implements the contract in distill_mathematicians/agents/github-curator.md:
  - Inputs:  discipline, vertical, [topic_keywords], min_stars, target
  - Output:  YAML manifest matching the github-curator schema
  - Behavior: filters by stars + archived + fork; classifies primary_content from
              file extensions; scores structural_quality from README structure +
              topic-organized folder names + link density; drops link-aggregator
              repos (`awesome-*`, `list-of-*`); under-delivers rather than relax
              the gate.

CLI: python -m distill_mathematicians.lib.cli github \
        --discipline math --vertical linear-algebra \
        --target 10 --min-stars 1000 --output runs/<id>/manifests/github.yaml

Stdlib only. Honors GITHUB_TOKEN env var (raises rate limit from 60/hr to 5000/hr;
search endpoint is 30/min in either case, throttled internally).
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# ---------- vertical → keyword expansions ----------
# The vertical slug + curated companion phrases form the search query. Keep
# expansions tight; the keyword list is OR'd in GitHub search and noise blooms
# fast otherwise.

MATH_VERTICAL_TERMS: dict[str, list[str]] = {
    "combinatorics": ["combinatorics"],
    "abstract-algebra": ["abstract algebra", "group theory"],
    "number-theory": ["number theory"],
    "commutative-algebra": ["commutative algebra"],
    "algebraic-geometry": ["algebraic geometry"],
    "linear-algebra": ["linear algebra"],
    "real-analysis": ["real analysis"],
    "complex-analysis": ["complex analysis"],
    "pde": ["partial differential equations", "PDE"],
    "general-topology": ["general topology", "point-set topology"],
    "algebraic-topology": ["algebraic topology"],
    "probability": ["probability theory"],
}

TCS_VERTICAL_TERMS: dict[str, list[str]] = {
    "complexity-theory": ["computational complexity", "complexity theory"],
    "cryptography": ["cryptography"],
    "algorithms": ["algorithms", "data structures"],
    "approximation-algorithms": ["approximation algorithms"],
    "randomized-algorithms": ["randomized algorithms"],
    "automata-and-formal-languages": ["formal languages", "automata theory"],
    "coding-and-information-theory": ["information theory", "coding theory"],
    "learning-theory": ["learning theory", "statistical learning"],
    "logic-in-cs": ["logic in computer science", "mathematical logic"],
}

DEFAULT_TOPIC_TERMS = ["notes", "lecture notes", "course"]

GITHUB_API = "https://api.github.com"
USER_AGENT = "distill-mathematicians/0.1 (https://github.com/AngelaWuRX/claude-math-tcs-agent)"
SEARCH_THROTTLE_S = 2.5         # search endpoint is 30/min; pace ourselves
DETAIL_THROTTLE_S = 0.2         # core endpoint is 5000/hr authenticated
README_CAP_BYTES = 32_768       # don't waste tokens on monster READMEs
RECENT_COMMIT_MAX_DAYS = 730    # ~24 months
MIN_STARS_DEFAULT = 1000

BLOCKLIST_NAME_PATTERNS = (
    re.compile(r"^awesome[-_]"),
    re.compile(r"^list[-_]of[-_]"),
    re.compile(r"^free[-_]programming[-_]books"),
)

TOPIC_FOLDER_RE = re.compile(
    r"(lecture|chapter|topic|week|module|unit|part)[-_\s]?\d+",
    re.IGNORECASE,
)

CODE_EXTS = {
    ".py", ".cpp", ".cc", ".c", ".h", ".hpp", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".rs", ".go", ".rb", ".php", ".swift", ".kt", ".scala", ".m",
    ".sh", ".bash", ".pl", ".r",
}


# ---------- data ----------

@dataclass
class Repo:
    full_name: str          # owner/repo
    url: str
    title: str
    description: str
    stars: int
    last_commit: str        # ISO date (yyyy-mm-dd)
    is_fork: bool
    is_archived: bool
    default_branch: str
    primary_content: str = "mixed"
    structural_quality: str = "medium"
    readme_text: str = ""
    section_count: int = 0
    topic_dir_count: int = 0
    link_density: float = 0.0
    contents_summary: str = ""


# ---------- HTTP ----------

def _auth_headers() -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_json(url: str, timeout: int = 30, allow_404: bool = False) -> dict | list | None:
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
        if e.code in (403, 429):
            print(f"[github] WARN: rate-limited/forbidden ({e.code}) on {url}", file=sys.stderr)
            return None
        raise


# ---------- search ----------

def build_query(keywords: list[str], min_stars: int) -> str:
    """GitHub search query: bare keywords + filters."""
    quoted = " ".join(f'"{k}"' if " " in k else k for k in keywords)
    return f"{quoted} stars:>={min_stars} archived:false fork:false"


def search_candidates(
    keywords: list[str],
    min_stars: int,
    pages: int = 3,
    verbose: bool = False,
) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        params = urllib.parse.urlencode({
            "q": build_query(keywords, min_stars),
            "sort": "stars",
            "order": "desc",
            "per_page": 100,
            "page": page,
        })
        url = f"{GITHUB_API}/search/repositories?{params}"
        if verbose:
            print(f"[github] GET {url}", file=sys.stderr)
        try:
            data = _http_json(url)
        except urllib.error.URLError as e:
            print(f"[github] WARN: search page {page} failed ({e})", file=sys.stderr)
            break
        if not data or "items" not in data:
            break
        items = data["items"]
        if not items:
            break
        for it in items:
            full = it["full_name"]
            if full in seen:
                continue
            seen.add(full)
            out.append(it)
        if len(items) < 100:
            break  # last page
        time.sleep(SEARCH_THROTTLE_S)
    return out


# ---------- per-repo enrichment ----------

def fetch_readme(full_name: str) -> str:
    data = _http_json(f"{GITHUB_API}/repos/{full_name}/readme", allow_404=True)
    if not data or "content" not in data:
        return ""
    try:
        raw = base64.b64decode(data["content"])
    except Exception:
        return ""
    text = raw.decode("utf-8", errors="replace")
    if len(text) > README_CAP_BYTES:
        text = text[:README_CAP_BYTES]
    return text


def fetch_contents(full_name: str, default_branch: str) -> list[dict]:
    data = _http_json(f"{GITHUB_API}/repos/{full_name}/contents", allow_404=True)
    if not data:
        return []
    if isinstance(data, dict):  # contents API returns a dict only for single-file repos
        return [data]
    return data


def fetch_last_commit(full_name: str) -> str | None:
    data = _http_json(f"{GITHUB_API}/repos/{full_name}/commits?per_page=1", allow_404=True)
    if not data or not isinstance(data, list) or not data:
        return None
    commit = data[0].get("commit", {})
    iso = commit.get("author", {}).get("date") or commit.get("committer", {}).get("date")
    return iso[:10] if iso else None


# ---------- scoring ----------

def detect_primary_content(contents: list[dict]) -> str:
    counts = {"markdown": 0, "jupyter": 0, "pdf": 0, "tex": 0, "code": 0}
    for item in contents:
        if item.get("type") != "file":
            continue
        name = item.get("name", "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext in (".md", ".markdown"):
            counts["markdown"] += 1
        elif ext == ".ipynb":
            counts["jupyter"] += 1
        elif ext == ".pdf":
            counts["pdf"] += 1
        elif ext == ".tex":
            counts["tex"] += 1
        elif ext in CODE_EXTS:
            counts["code"] += 1
    total = sum(counts.values())
    if total == 0:
        return "mixed"
    sorted_counts = sorted(counts.items(), key=lambda kv: -kv[1])
    top, top_count = sorted_counts[0]
    if top_count / total >= 0.6:
        return top if top != "tex" else "pdf"  # tex sources distill to pdf-equivalent
    return "mixed"


def count_sections(readme: str) -> int:
    return sum(1 for ln in readme.splitlines() if ln.startswith(("## ", "### ")))


def link_density(readme: str) -> float:
    lines = readme.splitlines()
    if not lines:
        return 0.0
    link_lines = sum(1 for ln in lines if "](http" in ln)
    return link_lines / len(lines)


def count_topic_dirs(contents: list[dict]) -> int:
    return sum(
        1 for item in contents
        if item.get("type") == "dir" and TOPIC_FOLDER_RE.search(item.get("name", ""))
    )


def score_structural_quality(repo: Repo) -> str:
    # link-aggregator gate: dense link list with little prose ⇒ low.
    if repo.link_density >= 0.30 and repo.section_count <= 3:
        return "low"

    # primarily code ⇒ low (per spec, code-heavy repos do not feed batch distillation).
    if repo.primary_content == "code":
        return "low"

    # high: study-guide README OR topic-organized folders, AND notes-shaped content.
    notes_shaped = repo.primary_content in ("markdown", "jupyter", "pdf", "tex", "mixed")
    if notes_shaped and (repo.section_count >= 5 or repo.topic_dir_count >= 3):
        return "high"

    # otherwise medium if at least notes-shaped and some structure.
    if notes_shaped and (repo.section_count >= 2 or repo.topic_dir_count >= 1):
        return "medium"

    return "low"


def is_blocked(name: str) -> bool:
    n = name.lower()
    return any(p.search(n) for p in BLOCKLIST_NAME_PATTERNS)


def is_recent_or_archived_canonical(last_commit: str | None, archived: bool) -> bool:
    if archived:
        # archived but kept as a canonical reference is acceptable per spec.
        return True
    if not last_commit:
        return False
    try:
        d = _dt.date.fromisoformat(last_commit)
    except ValueError:
        return False
    return (_dt.date.today() - d).days <= RECENT_COMMIT_MAX_DAYS


# ---------- pipeline ----------

def enrich(item: dict, verbose: bool = False) -> Repo | None:
    full = item["full_name"]
    repo = Repo(
        full_name=full,
        url=item["html_url"],
        title=item.get("name") or full,
        description=(item.get("description") or "").strip(),
        stars=int(item.get("stargazers_count", 0)),
        last_commit="",
        is_fork=bool(item.get("fork")),
        is_archived=bool(item.get("archived")),
        default_branch=item.get("default_branch") or "main",
    )
    if is_blocked(repo.title) or is_blocked(repo.full_name):
        if verbose:
            print(f"[github] drop {full}: blocklisted name", file=sys.stderr)
        return None

    last = fetch_last_commit(full)
    if last:
        repo.last_commit = last
    time.sleep(DETAIL_THROTTLE_S)

    if not is_recent_or_archived_canonical(repo.last_commit or None, repo.is_archived):
        if verbose:
            print(f"[github] drop {full}: stale (last_commit={repo.last_commit})", file=sys.stderr)
        return None

    repo.readme_text = fetch_readme(full)
    time.sleep(DETAIL_THROTTLE_S)
    repo.section_count = count_sections(repo.readme_text)
    repo.link_density = link_density(repo.readme_text)

    contents = fetch_contents(full, repo.default_branch)
    time.sleep(DETAIL_THROTTLE_S)
    repo.primary_content = detect_primary_content(contents)
    repo.topic_dir_count = count_topic_dirs(contents)

    repo.structural_quality = score_structural_quality(repo)
    repo.contents_summary = (
        f"{len([c for c in contents if c.get('type') == 'file'])} files, "
        f"{len([c for c in contents if c.get('type') == 'dir'])} dirs"
    )
    return repo


def select(repos: list[Repo], target: int) -> list[Repo]:
    qualified = [r for r in repos if r.structural_quality in ("high", "medium")]
    qualified.sort(
        key=lambda r: (
            0 if r.structural_quality == "high" else 1,
            -r.stars,
        )
    )
    return qualified[:target]


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


def _relevance_note(r: Repo) -> str:
    bits: list[str] = []
    bits.append(f"{r.stars} stars")
    bits.append(f"last commit {r.last_commit or 'unknown'}")
    bits.append(f"primary content: {r.primary_content}")
    bits.append(f"structure: {r.section_count} README sections, {r.topic_dir_count} topic-organized dirs")
    if r.is_archived:
        bits.append("archived (treated as canonical reference)")
    return "; ".join(bits) + "."


def render_manifest(discipline: str, vertical: str, selected: list[Repo]) -> str:
    today = _dt.date.today().isoformat()
    lines: list[str] = [
        "agent: github-curator",
        f"generated: {today}",
        f"discipline: {discipline}",
        f"vertical: {vertical}",
        "sources:",
    ]
    if not selected:
        lines.append("  []  # no repos cleared the structural-quality gate")
        return "\n".join(lines) + "\n"

    for r in selected:
        lines.append("  - type: github")
        lines.append(f"    url: {r.url}")
        lines.append(f"    repo: {r.full_name}")
        lines.append(f"    title: {_yaml_inline_str(r.title)}")
        lines.append(f"    description: {_yaml_inline_str(r.description)}")
        lines.append(f"    stars: {r.stars}")
        lines.append(f"    last_commit: {r.last_commit or 'null'}")
        lines.append(f"    primary_content: {r.primary_content}")
        lines.append(f"    structural_quality: {r.structural_quality}")
        lines.append(f"    relevance_note: {_yaml_block_scalar(_relevance_note(r), 6)}")
    return "\n".join(lines) + "\n"


# ---------- entrypoint ----------

def resolve_terms(discipline: str, vertical: str) -> list[str]:
    if discipline == "math":
        terms = MATH_VERTICAL_TERMS.get(vertical)
    elif discipline == "tcs":
        terms = TCS_VERTICAL_TERMS.get(vertical)
    else:
        raise ValueError(f"discipline must be 'math' or 'tcs', got: {discipline}")
    if not terms:
        known = sorted(MATH_VERTICAL_TERMS if discipline == "math" else TCS_VERTICAL_TERMS)
        raise ValueError(
            f"unknown vertical {vertical!r} for discipline {discipline}. "
            f"Known: {', '.join(known)}"
        )
    return terms


def run(args: argparse.Namespace) -> int:
    try:
        vertical_terms = resolve_terms(args.discipline, args.vertical)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    extra = args.keywords or DEFAULT_TOPIC_TERMS
    keywords = vertical_terms + extra

    if args.dry_run:
        print(f"would search GitHub: {build_query(keywords, args.min_stars)}")
        print(f"would target: {args.target} repos (high or medium structural_quality only)")
        print(f"would write: {args.output or '<stdout>'}")
        return 0

    if args.verbose:
        if not os.environ.get("GITHUB_TOKEN"):
            print("[github] WARN: no GITHUB_TOKEN set; rate limit is 60 req/hr", file=sys.stderr)

    candidates = search_candidates(
        keywords, args.min_stars,
        pages=args.search_pages,
        verbose=args.verbose,
    )
    if args.verbose:
        print(f"[github] {len(candidates)} candidates from search", file=sys.stderr)

    enriched: list[Repo] = []
    # cap how many we enrich — each costs 3 detail calls
    enrich_cap = min(len(candidates), max(args.target * 3, 30))
    for i, item in enumerate(candidates[:enrich_cap]):
        repo = enrich(item, verbose=args.verbose)
        if repo:
            enriched.append(repo)
        if args.verbose and (i + 1) % 10 == 0:
            print(f"[github] enriched {i + 1}/{enrich_cap}", file=sys.stderr)

    selected = select(enriched, args.target)
    if args.verbose:
        print(
            f"[github] selected: {len(selected)}/{args.target} "
            f"(high={sum(1 for r in selected if r.structural_quality == 'high')}, "
            f"medium={sum(1 for r in selected if r.structural_quality == 'medium')})",
            file=sys.stderr,
        )
        if len(selected) < args.target:
            print("[github] under-delivering — quality gate not relaxed", file=sys.stderr)

    yaml_text = render_manifest(args.discipline, args.vertical, selected)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {out} ({len(selected)} sources)")
    else:
        sys.stdout.write(yaml_text)
    return 0


def add_argparser(subparsers: argparse._SubParsersAction) -> None:
    sp = subparsers.add_parser("github", help="Build a GitHub-curator manifest for a batch run.")
    sp.add_argument("--discipline", required=True, choices=("math", "tcs"))
    sp.add_argument("--vertical", required=True)
    sp.add_argument("--min-stars", type=int, default=MIN_STARS_DEFAULT)
    sp.add_argument("--target", type=int, default=10)
    sp.add_argument("--keywords", nargs="*", default=None,
                    help=f"Additional topic terms. Default: {DEFAULT_TOPIC_TERMS}")
    sp.add_argument("--search-pages", type=int, default=3,
                    help="Pages of search results to fetch (100/page).")
    sp.add_argument("--output", help="Output YAML path. Defaults to stdout.")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--verbose", action="store_true")
    sp.set_defaults(func=run)
