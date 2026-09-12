---
math-tcs: annotated/v1
slug: dn
chapter: 1
title: Unit 1 — Divisibility
source_path: examples/demo/source/01_unit-1-divisibility.md
source_sha256: ed191e2c602e59092a05ef88e6eacbb07ac6107241bb7950619535d6ca72fc8b
---
# Unit 1 — Divisibility

## Conventions
- "Throughout this unit $a$, $b$ and $c$ denote natural numbers." → every variable ranges over ℕ; no variable is assumed nonzero.

## Open questions
- none

## dn-ch1-def-1.1-1
```json math-tcs
{
  "id": "dn-ch1-def-1.1-1",
  "kind": "definition",
  "label": null,
  "section": "1.1",
  "page": 1,
  "name": "divides",
  "statement_nl": "a divides b (written a ∣ b) when b is a multiple of a: some natural number q satisfies b = a·q.",
  "hypotheses": [],
  "conclusion": "a ∣ b is defined as ∃ q : ℕ, b = a * q",
  "variables": [{"name": "a", "type": "natural number", "from": "convention"}, {"name": "b", "type": "natural number", "from": "convention"}, {"name": "q", "type": "natural number", "from": "statement"}],
  "definitions_used": [],
  "depends_on": [],
  "has_source_proof": false,
  "mathlib_candidates": [{"name": "Dvd.dvd", "status": "exists"}, {"name": "Nat.instDvdNat", "status": "uncertain"}],
  "difficulty": {"estimate": "low", "reason": "a one-line existential; Mathlib's `∣` on ℕ has the same unfolding (`b = a * c`)"},
  "questions": []
}
```
### Source statement (verbatim)
> We say that $a$ *divides* $b$, written $a \mid b$, if there is a natural number $q$ with $b = a q$.
### Source proof (verbatim)
_No proof in source._
### Interpretation (agent)
The definition is stated inline in prose and carries no number. It matches Mathlib's `Dvd` instance on ℕ exactly (`a ∣ b ↔ ∃ c, b = a * c`); the scaffold may either introduce a local `Divides` mirroring the source or map to `Dvd.dvd`. The demo keeps a local definition so that the later theorems exercise the pipeline end to end.

## dn-ch1-thm-1.1
```json math-tcs
{
  "id": "dn-ch1-thm-1.1",
  "kind": "theorem",
  "label": "1.1",
  "section": "1.1",
  "page": 1,
  "name": "transitivity of divisibility",
  "statement_nl": "If a divides b and b divides c, then a divides c.",
  "hypotheses": ["a divides b", "b divides c"],
  "conclusion": "a divides c",
  "variables": [{"name": "a", "type": "natural number", "from": "convention"}, {"name": "b", "type": "natural number", "from": "convention"}, {"name": "c", "type": "natural number", "from": "convention"}],
  "definitions_used": [{"term": "divides", "id": "dn-ch1-def-1.1-1"}],
  "depends_on": [],
  "has_source_proof": true,
  "mathlib_candidates": [{"name": "dvd_trans", "status": "exists"}, {"name": "Dvd.dvd.trans", "status": "uncertain"}],
  "difficulty": {"estimate": "low", "reason": "compose the two witnesses; `Nat.mul_assoc` closes it"},
  "questions": []
}
```
### Source statement (verbatim)
> If $a \mid b$ and $b \mid c$, then $a \mid c$.
### Source proof (verbatim)
> Write $b = a q$ and $c = b r$. Then $c = (a q) r = a (q r)$, so $a \mid c$. □
### Interpretation (agent)
Direct witness composition: from b = a·q and c = b·r obtain c = a·(q·r). No hidden hypotheses; the convention that all variables are naturals is the only context.

## dn-ch1-thm-1.2
```json math-tcs
{
  "id": "dn-ch1-thm-1.2",
  "kind": "theorem",
  "label": "1.2",
  "section": "1.1",
  "page": 1,
  "name": "divisibility of a sum",
  "statement_nl": "If a divides b and a divides c, then a divides b + c.",
  "hypotheses": ["a divides b", "a divides c"],
  "conclusion": "a divides b + c",
  "variables": [{"name": "a", "type": "natural number", "from": "convention"}, {"name": "b", "type": "natural number", "from": "convention"}, {"name": "c", "type": "natural number", "from": "convention"}],
  "definitions_used": [{"term": "divides", "id": "dn-ch1-def-1.1-1"}],
  "depends_on": [],
  "has_source_proof": true,
  "mathlib_candidates": [{"name": "dvd_add", "status": "exists"}, {"name": "Dvd.dvd.add", "status": "uncertain"}],
  "difficulty": {"estimate": "low", "reason": "witness q + r and distributivity (`Nat.mul_add`)"},
  "questions": []
}
```
### Source statement (verbatim)
> If $a \mid b$ and $a \mid c$, then $a \mid (b + c)$.
### Source proof (verbatim)
> Write $b = a q$ and $c = a r$. Then $b + c = a q + a r = a (q + r)$. □
### Interpretation (agent)
Witness q + r; the computation is left distributivity of multiplication over addition.

## dn-ch1-thm-1.3
```json math-tcs
{
  "id": "dn-ch1-thm-1.3",
  "kind": "theorem",
  "label": "1.3",
  "section": "1.2",
  "page": 2,
  "name": "divisibility of b + b + c",
  "statement_nl": "If a divides b and a divides c, then a divides b + b + c.",
  "hypotheses": ["a divides b", "a divides c"],
  "conclusion": "a divides b + b + c",
  "variables": [{"name": "a", "type": "natural number", "from": "convention"}, {"name": "b", "type": "natural number", "from": "convention"}, {"name": "c", "type": "natural number", "from": "convention"}],
  "definitions_used": [{"term": "divides", "id": "dn-ch1-def-1.1-1"}],
  "depends_on": [{"ref": "theorem 1.2", "id": "dn-ch1-thm-1.2", "role": "uses"}],
  "has_source_proof": true,
  "mathlib_candidates": [{"name": "dvd_add", "status": "exists"}],
  "difficulty": {"estimate": "low", "reason": "two applications of Theorem 1.2; note the source's `b + b + c` parses as `(b + b) + c` in Lean, so the second application is to `b + b` and `c`, not as the prose says"},
  "questions": [{"text": "The prose applies Theorem 1.2 to `b` and `b + c` and appeals to associativity; Lean's left-associative `b + b + c` makes the direct route `(b + b) + c`. Not blocking.", "blocks_formalization": false}]
}
```
### Source statement (verbatim)
> If $a \mid b$ and $a \mid c$, then $a \mid (b + b + c)$.
### Source proof (verbatim)
> By theorem 1.2, $a \mid (b + c)$. Applying theorem 1.2 again to $b$ and $b + c$ gives $a \mid (b + (b + c))$, which is the claim by associativity. □
### Interpretation (agent)
Depends on Theorem 1.2 twice. A term-mode proof `divides_add (divides_add hab hab) hac` matches the left-associated Lean statement directly.

## dn-ch1-ex-1.2.1
```json math-tcs
{
  "id": "dn-ch1-ex-1.2.1",
  "kind": "exercise",
  "label": "1.2.1",
  "section": "1.2",
  "page": 2,
  "name": "everything divides zero",
  "statement_nl": "Every natural number a divides 0.",
  "hypotheses": [],
  "conclusion": "a divides 0",
  "variables": [{"name": "a", "type": "natural number", "from": "convention"}],
  "definitions_used": [{"term": "divides", "id": "dn-ch1-def-1.1-1"}],
  "depends_on": [],
  "has_source_proof": false,
  "mathlib_candidates": [{"name": "dvd_zero", "status": "exists"}],
  "difficulty": {"estimate": "low", "reason": "witness 0 and `Nat.mul_zero`"},
  "questions": []
}
```
### Source statement (verbatim)
> Show that $a \mid 0$ for every $a$.
### Source proof (verbatim)
_No proof in source._
### Interpretation (agent)
An exercise: the source gives no proof. Witness q = 0.

## dn-ch1-ex-1.2.2
```json math-tcs
{
  "id": "dn-ch1-ex-1.2.2",
  "kind": "exercise",
  "label": "1.2.2",
  "section": "1.2",
  "page": 2,
  "name": "antisymmetry of divisibility",
  "statement_nl": "If a divides b and b divides a, then a = b.",
  "hypotheses": ["a divides b", "b divides a"],
  "conclusion": "a = b",
  "variables": [{"name": "a", "type": "natural number", "from": "convention"}, {"name": "b", "type": "natural number", "from": "convention"}],
  "definitions_used": [{"term": "divides", "id": "dn-ch1-def-1.1-1"}],
  "depends_on": [],
  "has_source_proof": false,
  "mathlib_candidates": [{"name": "Nat.dvd_antisymm", "status": "exists"}],
  "difficulty": {"estimate": "medium", "reason": "true on ℕ (including a = b = 0) but needs `Nat.dvd_antisymm` or a case split on zero; false over ℤ, so the ℕ convention is load-bearing"},
  "questions": []
}
```
### Source statement (verbatim)
> Show that if $a \mid b$ and $b \mid a$ then $a = b$.
### Source proof (verbatim)
_No proof in source._
### Interpretation (agent)
Holds on ℕ only because there are no units other than 1; the section-wide convention that variables are natural numbers is what makes the statement true. Over ℤ the conclusion would need `a = b ∨ a = -b`.
