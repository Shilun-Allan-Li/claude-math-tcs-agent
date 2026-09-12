---
math-tcs: annotated/v1
slug: dn
chapter: 1
title: Unit 1 — Divisibility
source_path: /Users/rxw/Desktop/projects/research/claude-math-tcs-agent/plugins/math-tcs/examples/demo/source/01_unit-1-divisibility.md
source_sha256: ed191e2c602e59092a05ef88e6eacbb07ac6107241bb7950619535d6ca72fc8b
---
# Unit 1 — Divisibility

## Conventions
- (quote each section-wide convention verbatim → its meaning)

## Open questions
- none

## dn-ch1-thm-1.1
```json math-tcs
{
  "id": "dn-ch1-thm-1.1",
  "kind": "theorem",
  "label": "1.1",
  "section": "1.1",
  "page": 1,
  "name": "",
  "statement_nl": "",
  "hypotheses": [],
  "conclusion": "",
  "variables": [],
  "definitions_used": [],
  "depends_on": [],
  "has_source_proof": true,
  "mathlib_candidates": [],
  "difficulty": {
    "estimate": "",
    "reason": ""
  },
  "questions": []
}
```
### Source statement (verbatim)
> If $a \mid b$ and $b \mid c$, then $a \mid c$.
### Source proof (verbatim)
> Write $b = a q$ and $c = b r$. Then $c = (a q) r = a (q r)$, so $a \mid c$. □
### Interpretation (agent)


## dn-ch1-thm-1.2
```json math-tcs
{
  "id": "dn-ch1-thm-1.2",
  "kind": "theorem",
  "label": "1.2",
  "section": "1.1",
  "page": 1,
  "name": "",
  "statement_nl": "",
  "hypotheses": [],
  "conclusion": "",
  "variables": [],
  "definitions_used": [],
  "depends_on": [],
  "has_source_proof": true,
  "mathlib_candidates": [],
  "difficulty": {
    "estimate": "",
    "reason": ""
  },
  "questions": []
}
```
### Source statement (verbatim)
> If $a \mid b$ and $a \mid c$, then $a \mid (b + c)$.
### Source proof (verbatim)
> Write $b = a q$ and $c = a r$. Then $b + c = a q + a r = a (q + r)$. □
> 
> 
> ## 1.2 Consequences
### Interpretation (agent)


## dn-ch1-thm-1.3
```json math-tcs
{
  "id": "dn-ch1-thm-1.3",
  "kind": "theorem",
  "label": "1.3",
  "section": "1.2",
  "page": 2,
  "name": "",
  "statement_nl": "",
  "hypotheses": [],
  "conclusion": "",
  "variables": [],
  "definitions_used": [],
  "depends_on": [],
  "has_source_proof": true,
  "mathlib_candidates": [],
  "difficulty": {
    "estimate": "",
    "reason": ""
  },
  "questions": []
}
```
### Source statement (verbatim)
> If $a \mid b$ and $a \mid c$, then $a \mid (b + b + c)$.
### Source proof (verbatim)
> By theorem 1.2, $a \mid (b + c)$. Applying theorem 1.2 again to $b$ and $b + c$ gives $a \mid (b + (b + c))$, which is the claim by associativity. □
> 
> 
> 1.2.1 Show that $a \mid 0$ for every $a$.
> 
> 1.2.2 Show that if $a \mid b$ and $b \mid a$ then $a = b$.
### Interpretation (agent)


## dn-ch1-ex-1.2.1
```json math-tcs
{
  "id": "dn-ch1-ex-1.2.1",
  "kind": "exercise",
  "label": "1.2.1",
  "section": "1.2",
  "page": 2,
  "name": "",
  "statement_nl": "",
  "hypotheses": [],
  "conclusion": "",
  "variables": [],
  "definitions_used": [],
  "depends_on": [],
  "has_source_proof": false,
  "mathlib_candidates": [],
  "difficulty": {
    "estimate": "",
    "reason": ""
  },
  "questions": []
}
```
### Source statement (verbatim)
> Show that $a \mid 0$ for every $a$.
### Source proof (verbatim)
_No proof in source._
### Interpretation (agent)


## dn-ch1-ex-1.2.2
```json math-tcs
{
  "id": "dn-ch1-ex-1.2.2",
  "kind": "exercise",
  "label": "1.2.2",
  "section": "1.2",
  "page": 2,
  "name": "",
  "statement_nl": "",
  "hypotheses": [],
  "conclusion": "",
  "variables": [],
  "definitions_used": [],
  "depends_on": [],
  "has_source_proof": false,
  "mathlib_candidates": [],
  "difficulty": {
    "estimate": "",
    "reason": ""
  },
  "questions": []
}
```
### Source statement (verbatim)
> Show that if $a \mid b$ and $b \mid a$ then $a = b$.
### Source proof (verbatim)
_No proof in source._
### Interpretation (agent)

