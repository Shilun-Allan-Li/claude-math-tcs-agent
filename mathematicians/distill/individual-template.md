# <individual-pack-name>

Template for **individual packs** — capturing the *heuristic mind* of a single great mathematician. What do they notice first, what do they reach for, how do they reframe, when do they abandon a route. Written style is out of scope here; use `concise_math_style.md` for that.

---

## Source profile
- Mathematician: <name, years>
- Primary corpus: <collected works / correspondence / books / lectures>
- Distillation target: **heuristic mind** — approach and thinking process
- Reliability note: <why this corpus is enough to recover thinking patterns, not just polished style>

---

## One-line heuristic summary
One sentence capturing the central move.

Examples:
- Grothendieck: "Reframe until the statement becomes trivial."
- Erdős: "Randomize first; worry about concentration second."
- Gauss: "Find the invariant before computing anything."
- Euler: "Treat the formal series as the object; justify convergence later."
- Polya: "Have you seen a related problem?"

---

## First moves
What this mathematician does in the first minute of seeing a problem, before committing to a route.

- <move 1>
- <move 2>
- <move 3>

Examples:
- rewrite the problem in its most general natural setting
- tabulate small cases n=1,2,3 and look for a pattern
- ask "what would make this false?" and look for the obstruction
- check whether the statement has a symmetry currently hidden by notation

---

## What they notice first
The structural features that jump out for this person before anyone else.

Format: **feature → what it triggers**.

Examples:
- symmetry → exploit via group action; do not break it coordinate-wise
- extremal case → the problem is really about the boundary object
- a sequence → check whether the generating function is rational
- inner-product structure → Cauchy–Schwarz or spectral decomposition is available
- a universal property → the object is determined; stop trying to build it

---

## Reframings they reach for
Standard rewordings this person uses to make problems tractable.

- <reframing — when it triggers>

Examples:
- dual / contrapositive statement
- translate to an equivalent category or language
- embed into a more symmetric ambient structure
- quotient by the trivial symmetry
- switch from "exists" to "generic" (probabilistic reformulation)
- replace a hard specific with an easier general

---

## Characteristic tools
Tools this person reaches for before others.

- <tool — what problems it first-applies to>

Examples:
- Erdős: probabilistic method, deletion method, union bound, Lovász Local Lemma
- Euler: generating functions, interchange of limits, formal manipulation
- Gauss: quadratic-reciprocity-style invariants, finite-group averaging, explicit construction
- Grothendieck: universal property, descent, six-functor formalism, relative viewpoint

Each tool named here is a **target for downstream skill-generation** — the pack drives which `skills/` snippets get authored, not the other way around.

---

## Heuristics and slogans
One-line principles this person acts on.

Examples:
- "If a problem is too hard, solve a more general one."
- "The right definition makes the theorem trivial."
- "An existence claim is a probability computation in disguise."
- "Two proofs means you haven't found the right proof yet."

Only include slogans that show up as *recurring* moves in the corpus, not one-off quotes.

---

## When they abandon a route
Signals this person uses to cut losses.

- <signal — what they switch to>

Examples:
- computation is getting worse, not collapsing → wrong variables, re-coordinatize
- case split is growing unboundedly → missed a symmetry
- hypothesis being used is weaker than needed → generalize rather than push
- bound has a parameter that doesn't tighten → wrong quantity being bounded

---

## Anti-patterns
Moves this mathematician would not make, and why.

- <anti-pattern — reason>

Examples:
- Grothendieck: no grind of a coordinate computation; find the basis-free statement first
- Erdős: no insistence on constructive proof where existence suffices
- Gauss: no publishing until the result is airtight — "few but ripe"

---

## Worked trace
One problem shown as this mathematician would *think through* it, not the polished proof.

**Problem.** <statement>

**Trace.**
1. <first noticing>
2. <first reframing>
3. <tool chosen — and why *this* one first>
4. <what would make them abandon and switch>
5. <concluding move>

Keep to thought, not prose. The polished proof belongs in the prover's output, written in `concise_math_style.md`.

---

## Failure modes of this mind
How this heuristic mind goes wrong when applied carelessly.

- <failure — why>

Examples:
- Grothendieck-style reframing can delay concrete progress indefinitely
- Erdős-style randomization gives existence but not construction
- Gauss-style invariant hunt fails when no clean invariant exists and brute computation is correct

---

## Agent guidance

### Explorer
- adopt this mind during *planning*: pick the route this person would pick
- surface the first noticing and the first reframing explicitly in the plan
- do not produce a polished proof in this role

### Prover
- inherit the chosen *route*; write the proof in `concise_math_style.md`, not in the person's literary voice
- preserve the reframing only when it genuinely shortens or clarifies

### Reviewer
- check that the route matches what this mind would actually pick
- flag when the pack has been invoked but the proof uses a foreign route (the pack was decoration, not guidance)

---

## Minimal heuristic rules
Top 5 rules that survive everything else.

1. <rule>
2. <rule>
3. <rule>
4. <rule>
5. <rule>
