# Source-collection catalog — batches

Index of vertical slices for batch source collection, tagged with the standard classification used in that discipline:

- **Math** → [Mathematics Subject Classification (MSC 2020)](https://mathscinet.ams.org/msnhtml/msc2020.pdf), 2-digit primary codes.
- **TCS** → [arXiv CS subject categories](https://arxiv.org/corr/subjectclasses).

This catalog is **collection scaffolding for the distill backend**, not a skills index. It tells the distillers which verticals are recognized and where to drop raw corpus material (papers, surveys) before a batch pack is produced.

Paths split by discipline: `batches/math/<vertical>/` and `batches/tcs/<vertical>/`. A vertical folder may stay empty for a long time. "—" in the Status column means no sources collected yet.

## Math — by MSC

| MSC | Vertical | Status |
|---|---|---|
| 05 | combinatorics | — |
| 08 (also 16, 17, 20) | abstract-algebra | — |
| 11 | number-theory | — |
| 13 | commutative-algebra | — |
| 14 | algebraic-geometry | — |
| 15 | linear-algebra | — |
| 26 | real-analysis | — |
| 30 | complex-analysis | — |
| 35 | pde | — |
| 54 | general-topology | — |
| 55 | algebraic-topology | — |
| 60 | probability | — |

## TCS — by arXiv category

| arXiv | Vertical | Status |
|---|---|---|
| cs.CC | complexity-theory | — |
| cs.CR | cryptography | — |
| cs.DS | algorithms | — |
| cs.DS | approximation-algorithms | — |
| cs.DS | randomized-algorithms | — |
| cs.FL | automata-and-formal-languages | — |
| cs.IT | coding-and-information-theory | — |
| cs.LG | learning-theory | — |
| cs.LO | logic-in-cs | — |

## Notes

- Multiple TCS verticals share `cs.DS` — the folder split is pedagogical (by technique family), while the arXiv code is the research category. Both cuts are useful; the folders survive.
- `abstract-algebra` is a teaching label, not an MSC code. The closest MSC primaries are 08 (general algebraic systems), with 16 (associative rings), 17 (nonassociative rings), 20 (group theory) fitting specific sub-concepts.
- A batch is a vertical *slice* over a time window (e.g. "additive combinatorics, 2015–2025"). Sub-organize each vertical folder by window/slice as collections accumulate; this catalog only tracks the vertical layer.
