# Skills catalog

Index of skill verticals in `skills/domains/`, tagged with the standard classification used in that discipline:

- **Math** → [Mathematics Subject Classification (MSC 2020)](https://mathscinet.ams.org/msnhtml/msc2020.pdf), 2-digit primary codes.
- **TCS** → [arXiv CS subject categories](https://arxiv.org/corr/subjectclasses).

Skills list the *currently populated* snippets per vertical. "—" means the folder exists but no snippets have been authored yet; those are targets for future pack-driven skill generation.

## Math — by MSC

| MSC | Vertical | Skills |
|---|---|---|
| 05 | combinatorics | — |
| 08 (also 16, 17, 20) | abstract-algebra | — |
| 11 | number-theory | — |
| 13 | commutative-algebra | — |
| 14 | algebraic-geometry | — |
| 15 | linear-algebra | cr-decomposition, eigendecomposition, four-fundamental-subspaces, four-views-of-matrix-vector-product, lu-decomposition, qr-decomposition, spectral-theorem, svd |
| 26 | real-analysis | — |
| 30 | complex-analysis | — |
| 35 | pde | uses package format: SKILL.md + skill.yaml + references/  |
| 54 | general-topology | — |
| 55 | algebraic-topology | — |
| 60 | probability | — |

## TCS — by arXiv category

| arXiv | Vertical | Skills |
|---|---|---|
| cs.CC | complexity-theory | — |
| cs.CR | cryptography | — |
| cs.DS | algorithms | master-theorem |
| cs.DS | approximation-algorithms | — |
| cs.DS | randomized-algorithms | — |
| cs.FL | automata-and-formal-languages | — |
| cs.IT | coding-and-information-theory | — |
| cs.LG | learning-theory | — |
| cs.LO | logic-in-cs | — |

## Notes

- Multiple TCS verticals share `cs.DS` — the folder split is pedagogical (by technique family), while the arXiv code is the research category. Both cuts are useful; the folders survive.
- `abstract-algebra` is a teaching label, not an MSC code. The closest MSC primaries are 08 (general algebraic systems), with 16 (associative rings), 17 (nonassociative rings), 20 (group theory) all fitting specific sub-concepts.
- **Format drift to fix:** `pde/` uses the full-skill package format from `skill-creator/SKILLS.md` §Anatomy; every other skill here uses the flat-snippet format from that file's §Evaluation. Normalize when skill-generation reaches pde. Separately, `SKILLS.md` §Verification shows example paths without the `domains/` segment that the actual tree uses; update the example when SKILLS.md next gets edited.
- **Authoring contract for new snippets:** `skill-creator/SKILLS.md` §§Evaluation and Verification. One concept per file, 150–400 words, no frontmatter, `Source:` line at the end.
