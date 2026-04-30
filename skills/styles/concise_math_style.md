# Concise math style

Procedural patches for writing rigorous math without burning tokens.

## Rules

1. **State assumptions once.** Put hypotheses at the top, then reuse them. Don't repeat "since $A$ is symmetric" in every paragraph.
2. **Cite theorems by name.** Don't re-prove background. "By rank-nullity, …" beats re-deriving rank-nullity.
3. **Separate idea from execution.** Use `**Idea.**` (1–2 lines) and `**Proof.**` (the derivation). Don't mix brainstorming into the final proof.
4. **Explicit quantifiers.** Never "for large $n$" — write "there exists $N$ such that for all $n > N$".
5. **`:=` vs `=`.** Use `:=` for definitions, `=` for equalities. Always.
6. **Lemma-sized chunks.** For long arguments: setup → claim → key identity → conclusion. Multiple short blocks beat one paragraph.
7. **Cut filler.** Drop "intuitively", "we now observe that", "it is worth noting" unless they add reasoning.
8. **Don't restate fixed notation.** Once defined, reuse directly.

## Failure mode bucket

Compression / decompression discipline (skills/README.md taxonomy item 7).

## Consumers

`proof-prover` (writing steps), `proof-reviewer` (auditing for overcompression and missing quantifiers), `proof-formatter` (stripping filler when cleaning LaTeX).
