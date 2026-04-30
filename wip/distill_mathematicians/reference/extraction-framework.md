Proof-Style Distillation Framework

A methodology for extracting reusable mathematical and TCS reasoning patterns from raw sources.

1. Purpose

This framework defines how to move from raw mathematical material to reusable distilled proof-style patterns.

The goal is not to imitate a mathematician’s personality or writing voice. The goal is to extract patterns that help an agent:
	•	choose a proof route,
	•	identify useful structure,
	•	select the right theorem,
	•	set up notation efficiently,
	•	decompose a proof,
	•	avoid common mistakes,
	•	and write rigorous arguments with fewer wasted tokens.

This framework is designed for a multi-agent proof system where agents own the workflow and distilled packages provide compact reasoning priors.

⸻

2. What this framework extracts

This framework extracts proof-style patterns, not biographies or personas.

A proof-style pattern is a reusable rule about how a mathematician, TCS scientist, textbook, or proof tradition tends to reason.

Examples:
	•	“When symmetry appears, first search for an invariant or inner-product structure before expanding coordinates.”
	•	“In algorithm proofs, isolate the invariant before analyzing runtime.”
	•	“Use named theorems to compress background, but explicitly check hypotheses before invoking them.”
	•	“Reformulate the target statement before attempting computation.”
	•	“Split long arguments into local claims rather than one continuous paragraph.”

These patterns are useful because they change what an agent does on a new problem.

⸻

3. What this framework does not extract

Do not extract:
	•	biography,
	•	personality traits,
	•	motivational quotes,
	•	surface-level voice imitation,
	•	aesthetic compliments,
	•	one-off phrases,
	•	generic claims like “clear,” “rigorous,” “elegant,” or “deep.”

A claim like “the author writes clearly” is not a useful pattern unless it is converted into an operational rule, such as:

“The author states all hypotheses in one opening line, then avoids restating them unless the proof branches.”

⸻

4. The three-gate admission test

A candidate pattern may enter the distilled layer only if it passes all three gates:
	1.	Recurrence
	2.	Predictive Power
	3.	Exclusivity

If any gate fails, the pattern stays in extraction notes or is rejected.

⸻

5. Gate 1: Recurrence

A pattern must appear in at least two independent mathematical samples.

Independent samples may mean:
	•	different proofs,
	•	different chapters,
	•	different papers,
	•	different problem families,
	•	different source types,
	•	or different domains.

The goal is to avoid treating a one-off wording choice as a stable reasoning habit.

Good recurrence

A style repeatedly:
	•	states assumptions once at the beginning,
	•	reformulates the target before proving it,
	•	checks theorem hypotheses before theorem invocation,
	•	uses invariant-first reasoning across several problems.

Bad recurrence

A style uses one memorable phrase once.

That is not enough.

⸻

6. Gate 2: Predictive Power

A pattern must help predict how the style would behave on a new problem.

It should answer at least one of these questions:
	•	What structure would this style inspect first?
	•	Which proof route would it try before others?
	•	Which theorem family would it consider?
	•	How would it split the proof?
	•	What hypothesis would it check?
	•	What pitfall would it guard against?
	•	How would it compress the final argument?

If a pattern does not guide behavior on a new task, it is not useful enough to enter the distilled layer.

Good predictive pattern

“When a problem involves a monotone quantity or extremal object, first try an extremal argument before constructing explicitly.”

This predicts a route choice on new problems.

Bad predictive pattern

“The author is insightful.”

This predicts nothing operational.

⸻

7. Gate 3: Exclusivity

A pattern must distinguish this style from generic competent mathematical behavior.

It should not be something every good mathematician would say or do.

Too generic
	•	“Be rigorous.”
	•	“Check assumptions.”
	•	“Explain clearly.”
	•	“Use examples.”
	•	“Avoid mistakes.”

These are good principles, but they are not distinctive enough.

More exclusive
	•	“Prefer geometric structure before coordinate computation.”
	•	“Use theorem-name compression aggressively, but keep hypothesis checks explicit.”
	•	“Introduce a local lemma when the proof has more than one conceptual pivot.”
	•	“In reductions, first name the source problem and target problem before describing the mapping.”

These describe a specific methodological preference.

⸻

8. Admission decision

Each candidate pattern receives one decision:
	•	INCLUDE — passes all three gates.
	•	KEEP AS WEAK OBSERVATION — promising but lacks enough evidence.
	•	REJECT — generic, unsupported, non-predictive, or irrelevant.

Only INCLUDE patterns enter the final distilled style pack.

⸻

9. Extraction categories

When reading a source, look for evidence in the following categories.

⸻

9.1 Problem Framing

How does the source set up a problem?

Look for:
	•	how assumptions are stated,
	•	when notation is introduced,
	•	whether the target is reformulated,
	•	whether examples appear before the proof,
	•	whether the source begins with intuition or formal structure.

Extract patterns such as:
	•	“State hypotheses first, then define notation.”
	•	“Convert the target into an equivalent form before proving.”
	•	“Use a small example to reveal the invariant before stating the general argument.”

⸻

9.2 Route Selection

How does the source choose a proof strategy?

Look for preferences among:
	•	induction,
	•	contradiction,
	•	contrapositive,
	•	construction,
	•	compactness,
	•	diagonalization,
	•	reduction,
	•	exchange argument,
	•	extremal argument,
	•	probabilistic method,
	•	invariant-based reasoning,
	•	geometric reasoning,
	•	coordinate computation.

Extract patterns such as:
	•	“When direct construction is unstable, switch to contradiction.”
	•	“For algorithmic correctness, identify the invariant before runtime.”
	•	“For symmetry, test whether an inner-product argument is available.”

⸻

9.3 Proof Decomposition

How does the source break long arguments apart?

Look for:
	•	lemmas,
	•	claims,
	•	case splits,
	•	setup/key-step/conclusion structure,
	•	local reductions,
	•	intermediate propositions.

Extract patterns such as:
	•	“Use a lemma when the proof has two independent conceptual moves.”
	•	“Separate existence and uniqueness into different claims.”
	•	“Keep computational verification local rather than mixing it into the main proof.”

⸻

9.4 Theorem Use

How does the source use known results?

Look for:
	•	named theorem citations,
	•	restatement of theorem hypotheses,
	•	explicit hypothesis checks,
	•	when background results are cited without proof,
	•	when the source chooses to reprove a result.

Extract patterns such as:
	•	“Cite standard theorems by name to compress background.”
	•	“Restate only the version of a theorem needed for the proof.”
	•	“Check hypotheses before invoking a theorem, even in concise proofs.”

⸻

9.5 Compression Habits

How does the source reduce words without losing rigor?

Look for:
	•	assumption reuse,
	•	notation reuse,
	•	symbolic compression,
	•	theorem-name compression,
	•	short transition phrases,
	•	omitted obvious algebra,
	•	lemma-sized chunks.

Extract patterns such as:
	•	“State assumptions once and reuse them by reference.”
	•	“Use ‘It suffices to show’ to isolate the real target.”
	•	“Replace repeated background derivation with a named theorem plus one hypothesis check.”

⸻

9.6 Pitfall Management

What mistakes does the source actively prevent?

Look for:
	•	warnings,
	•	edge cases,
	•	hypothesis checks,
	•	counterexamples,
	•	distinctions between similar concepts,
	•	comments on why a tempting shortcut fails.

Extract patterns such as:
	•	“Distinguish diagonalizable from orthogonally diagonalizable.”
	•	“Do not assume an eigenvector is real when the eigenvalue is initially complex.”
	•	“In reductions, verify both correctness directions, not just the construction.”

⸻

10. Evidence record format

Each candidate pattern should be recorded using the following structure.

### Candidate Pattern: <short operational name>

- Category: <problem-framing / route-selection / decomposition / theorem-use / compression / pitfall-management>
- Claim: <one precise sentence>
- Evidence:
  - Source 1: <short quote or paraphrase with location>
  - Source 2: <short quote or paraphrase with location>
- Recurrence: <PASS / FAIL> — <reason>
- Predictive Power: <PASS / FAIL> — <what this predicts on a new problem>
- Exclusivity: <PASS / FAIL> — <why this is not generic>
- Decision: <INCLUDE / KEEP AS WEAK OBSERVATION / REJECT>
- Distilled Rule if Included: <one operational rule>


⸻

11. Example: included pattern

### Candidate Pattern: Structure Before Coordinates

- Category: route-selection
- Claim: When a linear algebra problem exposes symmetry or orthogonality, this style searches for inner-product or invariant-subspace structure before coordinate expansion.
- Evidence:
  - Source 1: Spectral theorem discussion emphasizes orthogonal decomposition before computation.
  - Source 2: SVD discussion treats geometry of subspaces before matrix entries.
- Recurrence: PASS — appears across multiple linear algebra topics.
- Predictive Power: PASS — predicts that on a new symmetric-matrix problem, the style will try an inner-product route before brute-force characteristic polynomial manipulation.
- Exclusivity: PASS — distinguishes this style from coordinate-first linear algebra presentations.
- Decision: INCLUDE
- Distilled Rule if Included: Check structural properties before expanding coordinates.


⸻

12. Example: rejected pattern

### Candidate Pattern: Clear Explanation

- Category: explanation
- Claim: The author explains clearly.
- Evidence:
  - Source 1: Several passages are easy to understand.
- Recurrence: FAIL — not recorded as a repeated operational behavior.
- Predictive Power: FAIL — does not predict how to approach a new proof.
- Exclusivity: FAIL — all good mathematical writing aims to be clear.
- Decision: REJECT
- Distilled Rule if Included: N/A


⸻

13. Extraction workflow

Step 1: Build a source inventory

For each source, record:
	•	title,
	•	author,
	•	source type,
	•	domain,
	•	license or access status,
	•	why it is relevant,
	•	confidence that it represents the target style.

Example:

- Source: The Art of Linear Algebra
- Type: visual notes / open-source educational material
- Domain: linear algebra
- Relevance: strong source for geometric linear algebra intuition
- Confidence: high


⸻

Step 2: Read for behavior, not content

Do not summarize the source chapter by chapter.

Instead, read for repeated behavior:
	•	How does it start proofs?
	•	What structures does it inspect first?
	•	How does it compress standard facts?
	•	What errors does it warn against?
	•	When does it switch from intuition to formalism?

⸻

Step 3: Log candidate patterns

Record every plausible pattern in the evidence format.

At this stage, do not force inclusion.
The extraction layer is allowed to contain weak or rejected observations.

⸻

Step 4: Apply the three gates

For each candidate, evaluate:
	•	Recurrence
	•	Predictive Power
	•	Exclusivity

Do not promote a pattern because it sounds elegant.
Promote only if it changes future reasoning behavior.

⸻

Step 5: Merge duplicates

Many patterns will overlap.

Example:
	•	“State assumptions early”
	•	“Do not repeat hypotheses”
	•	“Reuse notation after setup”

may merge into:

“Fix assumptions and notation once, then reuse them without re-expansion.”

⸻

Step 6: Write distilled rules

Convert included patterns into short operational rules.

A good rule is:
	•	short,
	•	actionable,
	•	predictive,
	•	not merely aesthetic.

⸻

Step 7: Create the distilled style pack

Use the distilled rules to write a compact style pack.

The style pack should contain only included patterns, plus necessary warnings about failure modes.

⸻

14. Distilled layer requirements

A distilled style pack should include:
	•	one-line style summary,
	•	when to use,
	•	when not to use,
	•	core reasoning habits,
	•	route-selection habits,
	•	theorem-use habits,
	•	compression habits,
	•	common pitfalls,
	•	failure modes,
	•	minimal distilled rules.

It should not include:
	•	long source summaries,
	•	biography,
	•	unsupported personality claims,
	•	raw evidence dumps,
	•	long quotations,
	•	textbook exposition.

⸻

15. How agents should use distilled packs

Distilled packs are not full proof scripts.

They are compact reasoning priors.

Explorer

Uses distilled packs to:
	•	choose possible proof routes,
	•	identify likely structures,
	•	name useful theorem families,
	•	avoid premature computation.

Prover

Uses distilled packs to:
	•	organize the proof,
	•	cite the right theorem,
	•	keep assumptions explicit,
	•	write compactly.

Reviewer

Uses distilled packs to:
	•	detect missing hypotheses,
	•	catch theorem misuse,
	•	check whether the proof has a visible backbone,
	•	identify overcompression.

Formatter

Uses distilled packs only for:
	•	compact style,
	•	theorem-proof structure,
	•	removal of filler.

⸻

16. Quality checklist

Before promoting an extraction into a distilled style pack, check:

Evidence
	•	Does each included pattern have at least two independent examples?
	•	Are the examples specific enough to verify?
	•	Are weak observations separated from included rules?

Predictive value
	•	Does each rule guide behavior on a new problem?
	•	Does it affect route selection, proof structure, theorem use, compression, or pitfall detection?
	•	Would an agent behave differently after reading it?

Exclusivity
	•	Is the rule more specific than “be rigorous” or “explain clearly”?
	•	Does it reflect a recognizable methodological preference?
	•	Could another competent style reasonably choose a different route?

Token efficiency
	•	Is the distilled pack compact?
	•	Does it avoid source summaries?
	•	Does it avoid long examples?
	•	Does each line carry operational value?

Agent usefulness
	•	Can the explorer use it?
	•	Can the prover use it?
	•	Can the reviewer use it?
	•	Can the formatter use it, if relevant?

⸻

17. Common failure modes

Failure mode 1: Vibes instead of rules

Bad:

“This style is elegant and insightful.”

Fix:

Identify the concrete behavior that creates the elegance.

⸻

Failure mode 2: Personality imitation

Bad:

“Write like this mathematician.”

Fix:

Extract proof behaviors, not voice or personality.

⸻

Failure mode 3: One-off overfitting

Bad:

“This source used contradiction once, so the style prefers contradiction.”

Fix:

Require recurrence across independent samples.

⸻

Failure mode 4: Generic advice

Bad:

“Check assumptions.”

Fix:

Specify which assumptions are typically at risk and when the style checks them.

⸻

Failure mode 5: Overcompression

Bad:

“Cite theorem names and omit all details.”

Fix:

Cite theorem names, but preserve hypothesis checks and the key logical transition.

⸻

18. Final rule

A distilled pattern is worth keeping only if it helps answer:

“Given a new proof problem, what would this style do differently?”

If the answer is unclear, do not promote it.