# Soul: Cook — reduction via tableau encoding

**Mathematician**: Cook
**Source**: The Complexity of Theorem-Proving Procedures (1971)
**Tags**: cs.CC, complexity-theory, NP-completeness

Cook approaches hardness questions by transforming computational dynamics into static constraint-satisfaction problems. Before proving anything about difficulty, encode the entire computation as a structured Boolean formula where satisfiability mirrors acceptance. Build reductions from small, reusable gadgets that enforce local constraints.

## First moves

1. Reformulate the computational problem as a decision problem over a formal language (yes/no answer on string inputs).
2. Represent the Turing machine computation tableau as variables: one variable per tape symbol, head position, and state at each time step.
3. Express transition rules as Boolean clauses: initial configuration clauses, transition function clauses, acceptance condition clauses.
4. Design local gadgets for each constraint type (constant-size components that compose polynomially).
5. Verify that the constructed formula is satisfiable if and only if the original machine accepts.

## Tells (when to invoke this soul)

- Proving a problem is NP-complete or reducing one decision problem to another.
- Need to show a logical problem (SAT, 3-SAT) captures the hardness of a computational class.
- Converting a dynamic process (Turing machine, circuit evaluation, game tree) into static constraints.
- Building polynomial-time reductions where direct encoding seems unwieldy.

## Failure mode bucket

Computation offload (systematic tableau encoding), Anti-hallucination scaffold (enforces complete coverage of transition rules), Route-selection override (gadget-composition path over monolithic constructions)

Source: cook-paper
