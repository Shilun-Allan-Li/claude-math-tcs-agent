# Distilled: gauss-collected_works

**Source**: Werke (archive.org Gesammelte Werke vol. 1)
**URL**: https://archive.org/details/werkecarlf01gausrich
**Kind**: great
**Tags**: math.HO, math.NT, math.AG
**Area**: math
**Vertical**: number-theory

## Heuristics

### Reduce to congruence structure first
- **When**: Faced with a divisibility or number-theoretic equation
- **Do**: Immediately reformulate the problem in terms of congruences modulo appropriate integers; name the congruence classes explicitly
- **Evidence**: Disquisitiones Arithmeticae systematically develops congruence notation (≡) and makes it the primary language for all subsequent proofs, replacing ad-hoc divisibility arguments

### Classify by residues before proving
- **When**: A theorem involves integers with special properties (primes, squares, etc.)
- **Do**: Perform exhaustive case analysis based on residue classes modulo small integers (especially 3, 4, 8) before attempting general proof
- **Evidence**: Quadratic reciprocity proofs begin with complete case enumeration of residues; the law of biquadratic reciprocity similarly partitions by residue classes mod 8

### Compute numerical instances to infer form
- **When**: Investigating an unknown pattern or searching for a general theorem
- **Do**: Systematically calculate small cases (first 20-50 instances) and tabulate results to identify invariants and periodicities
- **Evidence**: The classification of binary quadratic forms relied on extensive numerical tables of reduced forms for discriminants up to 100+; theory followed calculation

### Identify the relevant modular invariant
- **When**: Multiple congruence conditions appear or the problem has symmetry under multiplication
- **Do**: Look for a single composite modulus or a character that captures all conditions; reformulate the problem in terms of this invariant
- **Evidence**: Introduction of primitive roots and indices (discrete logarithms) converts multiplicative problems into additive ones modulo φ(n); the Gaussian integers add a new modulus structure to handle residues mod primes ≡ 1 (mod 4)

### Reduction theory for representatives
- **When**: Working with equivalence classes (of forms, ideals, etc.)
- **Do**: Define an explicit algorithmic reduction procedure that produces a unique canonical representative from each class; prove termination and uniqueness separately
- **Evidence**: The reduction algorithm for binary quadratic forms (ax² + bxy + cy²) uses bounds |b| ≤ a ≤ c and iterative transformations; this concrete algorithm precedes the abstract class group structure

### Compose objects before factoring them
- **When**: Studying a class of structured objects (quadratic forms, ideals)
- **Do**: Define a composition law on the objects first; then investigate which objects are prime/irreducible under composition
- **Evidence**: Composition of binary quadratic forms is defined via Dirichlet's rule before investigating which forms are primitive; the theory of unique factorization emerges from composition structure

### Prove existence via counting arguments
- **When**: Establishing that an object with certain properties exists
- **Do**: Use pigeonhole or cardinality bounds to force existence; avoid explicit construction when counting suffices
- **Evidence**: Existence of primitive roots uses the fact that the number of solutions to x^d ≡ 1 (mod p) is at most d, so counting arguments bound the number of elements of each order
