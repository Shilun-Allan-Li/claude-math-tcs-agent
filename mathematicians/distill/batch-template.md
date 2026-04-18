# <batch-pack-name>

Template for **batch packs** — capturing a *domain playbook*: the optimal way to attack problems in a domain slice, as currently practiced by a batch of active authors. Voice-agnostic. Individual idiosyncrasy is noise; what the batch *shares* is the signal.

---

## Source profile
- Domain slice: <e.g., additive combinatorics, 2015–2025>
- Batch: <5–15 active authors, years>
- Primary corpus: <papers / surveys / lecture notes considered>
- Distillation target: **domain playbook** — route selection and attack stack
- Reliability note: <why these authors represent current domain practice>

---

## One-line domain summary
One sentence capturing the domain's default approach.

Examples:
- Additive combinatorics: "Find the right Fourier-analytic object, then bound its energy."
- Spectral graph theory: "Move the question into the Laplacian spectrum and read off the bound."
- Algorithmic graph theory: "Reduce to a structural decomposition, then run the standard DP."
- Modern complexity: "Fix the model, then either find a reduction or prove a lower bound against a specific technique."

---

## Canonical problem types
The 3–6 kinds of problem that dominate the slice.

- <type — standard form of the question>

Examples (additive combinatorics):
- sumset-size / additive-structure questions
- density-increment / density-threshold questions
- pattern-avoidance / Szemerédi-type extremal questions
- inverse questions (given structure, recover algebraic origin)

If a problem doesn't look like one of these types, this pack is probably the wrong one to load.

---

## Default attack stack
The tools tried in order. Top of the stack first, pop when it doesn't traction-yield.

1. <first tool — when it works, when to pop>
2. <second tool — same>
3. <fallback>

Example (spectral graph theory):
1. Direct λ₂ bound — works when the graph is explicit and small enough
2. Cheeger / expander mixing — works when edge-uniformity is the right abstraction
3. Pseudorandomness / quasirandomness framework — general fallback for bounds

Keep short. A long stack is a sign the slice is too broad.

---

## Route selection by problem features
Flat decision table: observed feature → go-to route.

| Problem feature | Go-to route |
|---|---|
| <feature> | <route> |
| <feature> | <route> |

Cap around 10 rows. Beyond that, split the pack.

---

## Standard reductions
Moves that turn a problem in this slice into a solved problem.

- <reduction — from / to / when it applies>

Examples (additive combinatorics):
- density increment: problem on [N] → same problem on an arithmetic progression of density ≥ 2δ
- Cayley-graph embedding: combinatorial bound → spectral bound
- dyadic pigeonhole: continuous statement → uniform statement on a scale

---

## In-the-water knowledge
Named results and tools assumed without citation. An agent that doesn't know these cannot write in this domain.

- <theorem / tool>

Examples (additive combinatorics):
- Plünnecke–Ruzsa inequality
- Balog–Szemerédi–Gowers
- Freiman's theorem
- Gowers norms U^k
- arithmetic regularity lemma

Each entry here is a **target for downstream skill-generation** — the pack drives which `skills/` snippets get authored, not the other way around.

---

## Failure indicators
Signals that the chosen route is not going to finish, and the switch.

- <signal → switch to>

Examples:
- L² bound saturates but the claim needs L^∞ → switch to higher-order Fourier
- density increment stops improving → obstruction is structured; apply inverse theorem
- direct spectral bound gives the wrong order → move to Cheeger-type analysis

---

## Common traps
Mistakes specific to this slice.

- <trap — what goes wrong>

Examples:
- applying Plünnecke in a non-commutative setting without checking
- conflating energy and density bounds
- invoking a dependent-random-choice lemma in a regime where the parameters don't fit

---

## Worked trace
One representative problem solved the way the domain currently does it.

**Problem.** <statement>

**Route.**
1. <feature noticed>
2. <tool chosen — why first>
3. <reduction applied>
4. <concluding bound>

Keep to the *route*. The write-up uses `concise_math_style.md`.

---

## Agent guidance

### Explorer
- match problem features to the decision table
- pop the default attack stack until something yields
- call out when the problem doesn't resemble a canonical type — a different pack may be needed

### Prover
- execute the chosen route; cite in-the-water results without restatement
- write in `concise_math_style.md`

### Reviewer
- check that the route matches domain standard practice for this feature set
- flag use of tools outside the in-the-water list without explicit citation
- flag novel tool use that an author in the batch would not reach for first

---

## Minimal playbook rules
Top 5 rules that survive everything else.

1. <rule>
2. <rule>
3. <rule>
4. <rule>
5. <rule>
