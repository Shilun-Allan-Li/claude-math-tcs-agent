#!/usr/bin/env python3
"""Generate per-user config files for claude-math-tcs-agent.

Auto-detects what it can (git identity, installed CLI tools, registered
agents, registered great-mathematician souls) and prompts for the small
number of choices that need user input. The generated files
(`config/user.md`, `config/soul.md`, `config/agents.md`, `config/tools.md`)
are gitignored — they live only on the local machine.

Usage:
    python3 config/generate.py                 # interactive (default)
    python3 config/generate.py --defaults      # non-interactive; writes <USER> markers
    python3 config/generate.py --force         # overwrite existing files
    python3 config/generate.py --only soul     # regenerate just one file

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"

FILES = ("user", "soul", "agents", "tools")

# ---------- detection ----------

def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, check=False,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def detect_identity() -> dict:
    return {
        "git_name": _git("config", "user.name") or _git("config", "--global", "user.name") or "(unset)",
        "git_email": _git("config", "user.email") or _git("config", "--global", "user.email") or "(unset)",
        "project_root": str(ROOT),
        "detected_at": _dt.date.today().isoformat(),
    }


TOOL_PROBES = ("python3", "pdftotext", "pandoc", "tar", "unzip", "git", "gh", "curl", "wget")


def detect_tools() -> list[tuple[str, bool, str]]:
    rows = []
    for t in TOOL_PROBES:
        path = shutil.which(t) or ""
        rows.append((t, bool(path), path))
    return rows


AGENT_DIRS = (
    ("claude_prover/agents", "core proving"),
    ("engineers/agents", "compute helper"),
    ("distill_mathematicians/agents", "skill production"),
    (".claude/agents", "live install"),
)


def detect_agents() -> list[tuple[str, str]]:
    """Return [(agent_name, surface_dir)] from on-disk agent definitions."""
    seen: dict[str, str] = {}
    for rel, _label in AGENT_DIRS:
        d = ROOT / rel
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            seen.setdefault(p.stem, rel)
    return sorted(seen.items())


def detect_souls() -> tuple[list[tuple[str, list[str]]], list[str]]:
    """Return (registered_candidates, written_souls).

    registered_candidates = [(surname, [titles])] from the REGISTRY.
    written_souls = [source_id] for files already in skills/souls/.
    """
    candidates: list[tuple[str, list[str]]] = []
    try:
        sys.path.insert(0, str(ROOT))
        from distill_mathematicians.lib.collect import REGISTRY  # type: ignore
        for surname in sorted(REGISTRY):
            titles = [src["title"] for src in REGISTRY[surname]]
            candidates.append((surname, titles))
    except Exception as e:
        print(f"  [warn] could not load REGISTRY ({e})", file=sys.stderr)

    written: list[str] = []
    souls_dir = ROOT / "skills" / "souls"
    if souls_dir.exists():
        written = sorted(p.stem for p in souls_dir.glob("*.md"))
    return candidates, written

# ---------- prompts ----------

def _ask(label: str, default: str | None, choices: list[str] | None, interactive: bool) -> str:
    if not interactive:
        return f"<USER: {label}>" if default is None else default
    suffix = ""
    if choices:
        suffix += f" [{'/'.join(choices)}]"
    if default is not None:
        suffix += f" (default: {default})"
    while True:
        try:
            ans = input(f"  {label}{suffix}: ").strip()
        except EOFError:
            ans = ""
        if not ans and default is not None:
            return default
        if not ans:
            print("    (required)")
            continue
        if choices and ans not in choices:
            print(f"    pick one of: {', '.join(choices)}")
            continue
        return ans

# ---------- renderers ----------

def render_user(interactive: bool) -> str:
    ident = detect_identity()
    primary = _ask("primary area", None, ["math", "tcs", "both"], interactive)
    verticals = _ask("verticals of interest (comma-separated)", "(none)", None, interactive)
    comfort = _ask("comfort level", "grad", ["undergrad", "grad", "research"], interactive)
    verbosity = _ask("proof verbosity", "balanced", ["terse", "balanced", "verbose"], interactive)
    notation = _ask("notation preference", "latex", ["latex", "unicode", "both"], interactive)
    citation = _ask("citation discipline", "cite-by-name", ["cite-by-name", "always-restate"], interactive)
    return f"""# User profile

Per-user config. Auto-detected fields are filled in; lines tagged `<USER>` are filled at first login (or by editing this file directly).

## Identity (auto)

- Git name: {ident['git_name']}
- Git email: {ident['git_email']}
- Project root: {ident['project_root']}
- Detected at: {ident['detected_at']}

## Focus

- Primary area: {primary}
- Verticals of interest: {verticals}
- Comfort level: {comfort}

## Style

- Proof verbosity: {verbosity}
- Notation preference: {notation}
- Citation discipline: {citation}

## Cross-references

- Soul (chosen great-mathematician heuristic): see `config/soul.md`
- Enabled agents: see `config/agents.md`
- Enabled tools: see `config/tools.md`
"""


def render_soul(interactive: bool) -> str:
    candidates, written = detect_souls()
    surnames = [s for s, _ in candidates]
    chosen = _ask(
        f"chosen soul (one of: {', '.join(surnames) if surnames else '<none registered>'})",
        None if surnames else "(none)",
        surnames or None,
        interactive,
    )
    activated = _ask("activated", "yes", ["yes", "no"], interactive)

    lines = ["# Soul", "",
             "The chosen great-mathematician heuristic mind, injected into proving sessions as a route-selection prior.",
             "",
             "A soul is one of the great-mathematician fragments under `skills/souls/<source_id>.md` (written by `skill-creator` when it processes a `Kind: great` distilled file). The user picks one at first login; the proving agents read the chosen soul's \"First moves\" and \"Tells\" sections before each proof step.",
             "",
             "## Available (auto)",
             ""]
    if written:
        lines += ["### Souls already written to disk", ""]
        lines += [f"- `skills/souls/{w}.md`" for w in written]
        lines += [""]
    lines += ["### Registered candidates (REGISTRY in distill_mathematicians/lib/collect.py)", ""]
    for surname, titles in candidates:
        lines.append(f"- **{surname}** — " + "; ".join(titles))
    lines += ["",
              "## Chosen",
              "",
              f"- Soul: {chosen}",
              f"- Activated: {activated}",
              "",
              "## How activation works",
              "",
              "When `Activated: yes`, the proof-orchestrator and proof-prover read `skills/souls/<chosen-surname>-*.md` at the start of each session and treat the \"First moves\" list as a route-selection bias. Switch souls anytime by editing this file."]
    return "\n".join(lines) + "\n"


def render_agents(interactive: bool) -> str:
    agents = detect_agents()
    disable = _ask("disable from defaults (comma-separated, or empty)", "", None, interactive)
    add_on = _ask("add to always-on (comma-separated, or empty)", "", None, interactive)
    reviewer = _ask("reviewer mode", "strict", ["light", "strict"], interactive)

    lines = ["# Agents", "",
             "Per-user agent enablement. Auto-detected list comes from agent directories on disk.",
             "",
             "## Detected (auto)",
             "",
             "| Agent | Surface |",
             "|---|---|"]
    for name, surface in agents:
        lines.append(f"| {name} | {surface} |")
    lines += ["",
              "## Defaults",
              "",
              "- **Always enabled**: `proof-orchestrator`, `proof-prover`, `proof-reviewer`.",
              "- **Enabled on demand**: `proof-explorer`, `proof-formatter`, `engineer`.",
              "- **Pipeline-only**: `distiller`, `skill-creator`.",
              "",
              "## User overrides",
              "",
              f"- Disable from defaults: {disable or '(none)'}",
              f"- Add to always-on: {add_on or '(none)'}",
              f"- Preferred reviewer mode: {reviewer}"]
    return "\n".join(lines) + "\n"


def render_tools(interactive: bool) -> str:
    tools = detect_tools()
    have = {t: present for t, present, _ in tools}
    compute = _ask("computation engine", "python", ["python", "matlab", "cpp", "manual"], interactive)
    web_search = _ask("web search enabled", "yes", ["yes", "no"], interactive)
    cite_mode = _ask("citation verification mode", "strict", ["strict", "lenient", "off"], interactive)
    allow_fetch = _ask("allow sub-agents to WebFetch", "no", ["yes", "no"], interactive)

    today = _dt.date.today().isoformat()
    lines = ["# Tools", "",
             f"Per-user tool wiring. Auto-detection ran at config generation ({today}); user picks which detected tools are wired into proving sessions.",
             "",
             "## Detected on this machine (auto)",
             "",
             "| Tool | Present | Path |",
             "|---|---|---|"]
    for t, present, path in tools:
        lines.append(f"| {t} | {'yes' if present else 'no'} | {path or '—'} |")

    pdf_engine = "pdftotext" if have["pdftotext"] else ("pandoc" if have["pandoc"] else "none — install pdftotext or pandoc")
    archive_dl = "curl" if have["curl"] else ("wget" if have["wget"] else "none — install curl or wget")
    lines += ["",
              "## Defaults",
              "",
              "- **Computation**: dispatch to `engineer` agent (uses python3 / matlab / cpp depending on the verb).",
              f"- **PDF / LaTeX → markdown**: `proof-formatter` uses `{pdf_engine}`.",
              f"- **Source archive download**: `{archive_dl}`.",
              "- **Citation lookup**: web search via the `WebFetch` tool — requires `WebFetch(*)` in `.claude/settings.json`'s `permissions.allow`.",
              "",
              "## User overrides",
              "",
              f"- Computation engine: {compute}",
              f"- Web search enabled: {web_search}",
              f"- Citation verification mode: {cite_mode}",
              f"- Allow sub-agents to WebFetch: {allow_fetch}"]

    missing = [t for t, present, _ in tools if not present]
    if missing:
        lines += ["", "## Missing tools", ""]
        for t in missing:
            hint = {
                "pandoc": "brew install pandoc — needed for clean LaTeX → markdown when PDFs aren't available",
                "wget":   "optional; curl covers the same use cases",
                "gh":     "brew install gh — only needed if you use GitHub PR / issue automation",
                "pdftotext": "brew install poppler — needed for paper formatting",
            }.get(t, "")
            lines.append(f"- `{t}` — {hint}" if hint else f"- `{t}`")
    return "\n".join(lines) + "\n"


RENDERERS = {
    "user": render_user,
    "soul": render_soul,
    "agents": render_agents,
    "tools": render_tools,
}

# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate per-user config files.")
    p.add_argument("--defaults", action="store_true",
                   help="Non-interactive: write <USER> markers and documented defaults.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing files.")
    p.add_argument("--only", choices=FILES,
                   help="Regenerate just one of the four files.")
    args = p.parse_args(argv)

    interactive = not args.defaults
    targets = [args.only] if args.only else list(FILES)

    CONFIG.mkdir(exist_ok=True)
    for name in targets:
        path = CONFIG / f"{name}.md"
        if path.exists() and not args.force:
            print(f"skip  {path.relative_to(ROOT)}  (exists; pass --force to overwrite)")
            continue
        if interactive:
            print(f"\n=== {name}.md ===")
        body = RENDERERS[name](interactive)
        path.write_text(body)
        print(f"wrote {path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
