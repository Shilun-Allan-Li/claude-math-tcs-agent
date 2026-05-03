# Distilled: cook-paper

**Source**: The Complexity of Theorem-Proving Procedures (1971)
**URL**: https://www.cs.toronto.edu/~sacook/homepage/1971.pdf
**Kind**: great
**Tags**: cs.CC
**Area**: tcs
**Vertical**: complexity-theory

## Heuristics

### Formalize via recognition problem
- **When**: Studying computational difficulty of a problem class
- **Do**: Reformulate as a decision problem (yes/no answer) with a formal language; define the set of strings that encode positive instances
- **Evidence**: Cook frames tautology-checking as "given a formula in propositional calculus, is it a tautology?" and SAT as "given a formula in CNF, does there exist a satisfying assignment?" Both are language-recognition problems over {0,1}*.

### Anchor hardness in a minimal complete problem
- **When**: Establishing that a complexity class contains hard problems
- **Do**: Identify one natural problem and prove all others in the class reduce to it; this single problem witnesses the hardness of the entire class
- **Evidence**: Cook proves SAT is NP-complete by showing that any nondeterministic polynomial-time Turing machine computation can be encoded as a Boolean formula in CNF whose satisfiability is equivalent to acceptance. One reduction covers the entire class.

### Encode computation as constraint satisfaction
- **When**: Reducing a Turing machine problem to a logical problem
- **Do**: Represent the computation tableau (configurations over time) as variables, and express transition rules and acceptance conditions as Boolean clauses
- **Evidence**: Cook's reduction from an arbitrary NP problem to SAT constructs variables for tape symbols, head positions, and states at each time step, then writes clauses enforcing initial configuration, transition function, and final acceptance.

### Polynomial-time reduce via local gadgets
- **When**: Showing one decision problem is at least as hard as another
- **Do**: Build the reduction by designing small, reusable components (gadgets) that enforce local constraints; compose them to simulate the source problem's structure
- **Evidence**: Cook's SAT encoding uses clause gadgets for each type of constraint (initial state, transition, uniqueness of head position). Each gadget is constant-size; total formula size is polynomial in input length.

### Prove completeness by diagonalization over resource-bounded machines
- **When**: Establishing a problem is complete for a time- or space-bounded class
- **Do**: Use the universal simulation argument: show that the complete problem can encode and simulate any machine in the class within the same resource bound
- **Evidence**: Cook proves SAT is NP-complete by demonstrating that a nondeterministic Turing machine running in time p(n) can be encoded as a CNF formula of size polynomial in p(n), and satisfiability of the formula is equivalent to existence of an accepting computation path.

### Distinguish nondeterminism from determinism via certificate verification
- **When**: Defining complexity classes based on computational power
- **Do**: Characterize the nondeterministic class by the existence of short certificates verifiable in deterministic polynomial time
- **Evidence**: Cook defines NP as the class of languages recognized by nondeterministic polynomial-time Turing machines, equivalently as languages for which a "yes" instance has a polynomially-bounded witness checkable in deterministic polynomial time.

### Test hardness hypothesis on small cases first
- **When**: Investigating whether a problem is complete for a complexity class
- **Do**: Check if restricted or simplified versions already capture the full hardness; use minimal restrictions (e.g., 3-CNF, 3-colorability) to isolate the essential difficulty
- **Evidence**: Cook focuses on CNF-SAT rather than arbitrary Boolean formulas, and later work (Karp, Levin) showed even 3-CNF-SAT is NP-complete. The restriction does not reduce hardness.

### Separate complexity classes by closure properties
- **When**: Arguing that two complexity classes are distinct
- **Do**: Exhibit a closure property (e.g., under complement, intersection, or concatenation) that one class has and the other provably does not
- **Evidence**: Cook observes that if P = NP, then NP would be closed under complement (since P is), but it is unclear whether NP has this property. This observation motivates the P vs NP question as a fundamental separation problem.
