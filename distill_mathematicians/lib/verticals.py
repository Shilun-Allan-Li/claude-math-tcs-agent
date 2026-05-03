"""Vertical taxonomy: arxiv tag -> (area, vertical-folder).

Math = MSC 2020 primaries (12 verticals).
TCS  = arXiv cs.* categories (9 verticals; the cs.DS folder splits
       pedagogically into algorithms / approximation-algorithms /
       randomized-algorithms — default route is `algorithms`).

Greats often carry several tags (e.g. Riemann: math.HO, math.CV, math.DG).
`select_primary_tag` drops history/general tags when others are present
and returns the first remaining recognized tag. Use `route(tags)` to pick
the (area, vertical) folder for a distilled output.
"""

from __future__ import annotations

# MSC primary -> vertical folder (12 verticals).
# Note: MSC 15 (linear-algebra) and MSC 08/16/17/20 (abstract-algebra)
# share the math.RA arxiv tag; routing prefers abstract-algebra unless
# the source explicitly carries a linear-algebra signal in its title.
MATH_VERTICALS = {
    "math.CO": "combinatorics",          # MSC 05
    "math.RA": "abstract-algebra",       # MSC 08/16/17/20
    "math.NT": "number-theory",          # MSC 11
    "math.AC": "commutative-algebra",    # MSC 13
    "math.AG": "algebraic-geometry",     # MSC 14
    "math.CA": "real-analysis",          # MSC 26/28
    "math.CV": "complex-analysis",       # MSC 30
    "math.AP": "pde",                    # MSC 35
    "math.GN": "general-topology",       # MSC 54
    "math.AT": "algebraic-topology",     # MSC 55
    "math.PR": "probability",            # MSC 60
    # math.DG kept for completeness — not one of the 12, falls through.
}

# Manual aliases — verticals that have no clean primary arxiv tag.
MATH_ALIASES = {
    "math.NA": "linear-algebra",         # numerical analysis tends to live here too
}

# arXiv cs.* -> vertical folder.
TCS_VERTICALS = {
    "cs.CC": "complexity-theory",
    "cs.CR": "cryptography",
    "cs.DS": "algorithms",               # also approx- and randomized- (move by hand)
    "cs.FL": "automata-and-formal-languages",
    "cs.IT": "coding-and-information-theory",
    "cs.LG": "learning-theory",
    "cs.LO": "logic-in-cs",
}

# Tags ignored when choosing the primary routing tag.
_DEMOTE = {"math.HO", "math.GM", "math.MP"}


def tag_to_vertical(tag: str) -> tuple[str, str] | None:
    """Map a single arxiv tag to (area, vertical-folder). None if unrecognized."""
    if tag in MATH_VERTICALS:
        return ("math", MATH_VERTICALS[tag])
    if tag in MATH_ALIASES:
        return ("math", MATH_ALIASES[tag])
    if tag in TCS_VERTICALS:
        return ("tcs", TCS_VERTICALS[tag])
    return None


def select_primary_tag(tags: list[str]) -> str | None:
    """Pick the primary tag for routing: drop history/general, take first known."""
    for t in tags:
        if t in _DEMOTE:
            continue
        if t in MATH_VERTICALS or t in MATH_ALIASES or t in TCS_VERTICALS:
            return t
    for t in tags:
        if t not in _DEMOTE:
            return t
    return tags[0] if tags else None


def route(tags: list[str]) -> tuple[str, str] | None:
    """Convenience: tag list -> (area, vertical-folder), or None."""
    t = select_primary_tag(tags)
    if t is None:
        return None
    return tag_to_vertical(t)


def category_label(tags: list[str]) -> str | None:
    """Render the in-skill `Category:` label, e.g. 'tcs-algorithms'."""
    r = route(tags)
    if r is None:
        return None
    area, vertical = r
    return f"{area}-{vertical}"
