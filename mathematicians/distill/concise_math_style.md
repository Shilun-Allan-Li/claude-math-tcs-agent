Reference note for writing mathematically rigorous content with high information density and low token waste.

# Agent behavior
Each agent should do this once:
- read concise-math-style.md
- extract the top 3 rules relevant to its role
- write them into its own working memory / contract / runtime state
- stop rereading unless the file changes

## Core principle

Write the **minimum text that preserves correctness**.

Do **not** optimize for shortest possible output.  
Optimize for:
- correct hypotheses
- explicit theorem use
- no repeated setup
- no filler
- high information per line

## Compression rules

### 1. State assumptions once
Put hypotheses at the top, then reuse them.

Good:
- “Let \(A \in \mathbb R^{n\times n}\) be symmetric.”

Bad:
- repeating “since \(A\) is symmetric” in every paragraph unless the reminder matters

### 2. Name the theorem instead of re-proving background
If a standard result is being used, cite it by name unless the proof is the point.

Good:
- “By rank-nullity, \(\dim V=\dim\ker T+\dim\operatorname{im}T\).”

Bad:
- re-deriving rank-nullity in a proof that is not about rank-nullity

### 3. Separate proof idea from proof execution
Do not mix brainstorming and final proof.

Use:
- **Idea:** one or two lines
- **Proof:** the actual derivation

This avoids repeated explanation.

### 4. Use mathematical notation when it compresses cleanly
Prefer symbols when they replace long prose unambiguously.

Good:
- “For all \(x\in X\), \(f_n(x)\to f(x)\) a.e.”
- “Assume \(n\ge 2\).”

Bad:
- symbolic clutter that is denser but less readable

### 5. Use lemma-sized chunks
Break long proofs into:
- setup
- claim
- key identity
- conclusion

This is shorter and clearer than one large paragraph.

### 6. Avoid motivational filler in runtime outputs
Cut phrases like:
- “intuitively speaking”
- “we now observe that”
- “it is worth noting that”
unless they add actual reasoning value

### 7. Do not restate notation already fixed
Once notation is defined, reuse it directly.

