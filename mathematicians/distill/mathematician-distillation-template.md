# <style-pack-name>

## Source profile
- Primary source type: <textbook / lecture notes / papers / blog posts / talks>
- Domain: <linear algebra / analysis / combinatorics / algorithms / complexity / ...>
- Distillation target: <proof style / explanation style / route selection / compression habits>
- Reliability note: <why these sources are representative>

---

## One-line style summary
<One sentence describing the style.>

Examples:
- “Invariant-first, notation-light, theorem-driven.”
- “Geometric intuition first, then algebraic formalization.”
- “Reduction-oriented, explicit case split, minimal prose.”

---

## When to use this style
- <type of tasks where this style is useful>
- <domains or proof situations where it fits>
- <what kind of agent should read this>

Examples:
- exploratory proof planning
- concise theorem-proof writing
- reviewing proof structure
- turning intuition into rigorous outline

---

## When NOT to use this style
- <cases where this style is a bad fit>
- <domains where it overcompresses or misleads>
- <cases where a different style should dominate>

Examples:
- beginner teaching requiring slow exposition
- highly computational derivations needing detailed algebra
- formal proof translation where notation must be exact

---

## Core reasoning habits
List 3–7 habits.

- <habit 1>
- <habit 2>
- <habit 3>

Examples:
- isolates the main invariant early
- states the target equivalently in a more usable form
- reduces to a standard named theorem quickly
- prefers structural decomposition over brute-force computation
- checks hidden assumptions before pushing a standard argument

---

## Proof route selection habits
How this style tends to choose a route.

- first checks whether the problem is really a standard theorem instance
- looks for contradiction / contrapositive / induction / reduction opportunities
- prefers geometric route over coordinate route when structure is clearer
- prefers algebraic manipulation only when structural tools fail

---

## Compression habits
How this style saves words without losing rigor.

- states assumptions once and reuses them
- cites named theorems instead of rederiving background
- uses lemma-sized chunks instead of long paragraphs
- avoids motivational filler
- uses notation only when it shortens the argument cleanly

---

## Preferred proof schemas
List the schemas this style reaches for first.

- induction
- contradiction
- contrapositive
- extremal argument
- exchange argument
- diagonalization
- compactness
- averaging / probabilistic method
- reduction
- spectral / inner-product argument

Add one line for each that matters:
- **Contradiction:** used when direct construction is messy but impossibility structure is clean.
- **Reduction:** used when the statement is better viewed as an instance of a known result.

---

## Theorem usage style
How this style cites and applies known results.

- names standard results early
- checks assumptions explicitly before invoking them
- does not restate famous theorems unless the exact version matters
- distinguishes theorem use from intuition

---

## Typical structure of an answer
Describe the preferred shape of output.

1. state setup
2. identify structural feature
3. choose main theorem / invariant
4. execute key step
5. conclude briefly
6. optional pitfall note

---

## Typical sentence patterns
Short phrases this style likes.

- “It suffices to show …”
- “Equivalently, …”
- “Fix …”
- “By <theorem name>, …”
- “Apply the hypothesis to …”
- “Thus …”
- “Conversely, …”

Only include patterns that are genuinely characteristic.

---

## Common pitfalls this style avoids
- using a theorem before checking hypotheses
- doing coordinate computations too early
- repeating setup in every paragraph
- hiding the key invariant
- compressing away a necessary assumption

---

## Common failure mode of this style
Every style has a downside.

Examples:
- can be too compressed for beginners
- may hide intuition behind theorem names
- may jump too quickly to a standard theorem
- may underexplain computational steps

---

## Transformation rules
How to rewrite a generic proof into this style.

- replace long setup prose with one formal assumption line
- convert repeated background derivations into named theorem citations
- split one long proof into setup / key claim / conclusion
- replace generic “try stuff” exploration with explicit route candidates

---

## Example before/after
### Before
<generic verbose or badly structured proof snippet>

### After
<same content rewritten in this distilled style>

---

## Agent guidance
How agents should use this style.

### Explorer
- use this style to propose routes and identify the main invariant
- do not write a polished final proof unless asked

### Prover
- use this style to structure the final proof compactly
- preserve assumptions explicitly

### Reviewer
- use this style to check whether the proof has a visible backbone
- flag hidden assumptions or theorem misuse

---

## Minimal distilled rules
If only 5 rules survive, keep these:

1. <rule>
2. <rule>
3. <rule>
4. <rule>
5. <rule>