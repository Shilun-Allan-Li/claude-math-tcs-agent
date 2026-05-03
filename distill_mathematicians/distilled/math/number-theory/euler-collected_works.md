# Distilled: euler-collected_works

**Source**: Opera Omnia (Euler Archive)
**URL**: https://eulerarchive.maa.org/
**Kind**: great
**Tags**: math.HO, math.NT, math.CA
**Area**: math
**Vertical**: number-theory

## Heuristics

### Convert sum to generating function
- **When**: Counting problem or recursive sequence appears
- **Do**: Define a power series whose coefficients encode the sequence, manipulate algebraically
- **Evidence**: Euler's solution to the partition problem P(n) via the pentagonal number theorem; transforms counting into product manipulations (1 - x)(1 - x²)(1 - x³)... = Σ(-1)^k x^(k(3k-1)/2)

### Express closed form via infinite product
- **When**: Seeking identity for series or multiplicative structure is visible
- **Do**: Factor as infinite product over primes or natural numbers; often reveals hidden symmetry
- **Evidence**: Euler's product formula for zeta function ζ(s) = Π_p (1 - p^(-s))^(-1) connects additive (sum over n) to multiplicative (product over primes) structure

### Substitute formal parameter then specialize
- **When**: General formula is opaque or hard to discover
- **Do**: Introduce symbolic parameter, derive relation in generality, then set parameter to concrete value
- **Evidence**: Basel problem (sum of 1/n²): Euler factored sin(πx)/πx as infinite product Π(1 - x²/n²), expanded, matched coefficients, set x=1

### Name the function before proving convergence
- **When**: Series or limit appears computationally useful
- **Do**: Treat it as a well-defined object, derive properties algebraically, verify convergence later
- **Evidence**: Euler manipulated divergent series (e.g., 1 - 1 + 1 - 1 + ... = 1/2) using summation methods; prioritized operational rules over foundational rigor

### Exploit recurrence to telescope
- **When**: Sequence satisfies recurrence or difference equation
- **Do**: Write relation between consecutive terms, sum or multiply to eliminate intermediate terms
- **Evidence**: Euler's derivation of Fibonacci closed form via characteristic equation; recurrence a_n = a_(n-1) + a_(n-2) transforms into algebraic equation x² = x + 1

### Split sum by residue class
- **When**: Summand exhibits periodicity or divisibility pattern
- **Do**: Partition indices modulo m, handle each class separately, recombine
- **Evidence**: Euler's quadratic reciprocity investigations partition sums over primes by congruence conditions; separates cases p ≡ 1 (mod 4) vs. p ≡ 3 (mod 4)

### Expand in series then integrate term-by-term
- **When**: Integral of known function needed
- **Do**: Write integrand as power series, integrate each term, justify exchange later if questioned
- **Evidence**: Euler's evaluations of ζ(2k) via Bernoulli numbers; expands cotangent as power series, integrates to recover zeta values

### Transform discrete to continuous analogue
- **When**: Discrete sum or product is hard to evaluate
- **Do**: Replace by integral, use substitution or calculus technique, interpret back
- **Evidence**: Euler-Maclaurin formula bridges sums and integrals; Euler derived asymptotic formulas (e.g., log n! ≈ n log n - n) by approximating sum with integral

