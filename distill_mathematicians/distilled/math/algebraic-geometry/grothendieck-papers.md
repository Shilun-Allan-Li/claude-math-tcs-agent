# Distilled: grothendieck-papers

**Source**: Grothendieck publications (numdam)
**URL**: https://www.numdam.org/
**Tags**: math.AG, math.CT

## Heuristics

### Replace objects by functors they represent
- **When**: An object (scheme, variety, sheaf) is hard to study directly
- **Do**: Replace it by the functor it represents — study the category of morphisms into it instead of the object itself
- **Evidence**: Functor of points: a scheme X is determined by Hom(−, X). This turns geometric questions into categorical ones and makes relative notions (families, moduli) natural. (EGA I, Tohoku)

### Relativize to a base scheme
- **When**: A construction or theorem is stated for varieties or schemes over a field
- **Do**: Immediately generalize to the relative setting over an arbitrary base scheme S
- **Evidence**: Replace "variety over k" with "scheme over S" throughout. Fibered products, base change, proper morphisms — all defined relatively. Hard theorems (coherent sheaf cohomology) proved in relative setting first. (EGA II-IV)

### Build the abstract machinery first
- **When**: Facing a concrete problem (e.g., Weil conjectures, resolution of singularities)
- **Do**: Construct the general theory that makes the problem trivial or formal, rather than attacking directly
- **Evidence**: "Rising sea" method: to prove the Weil conjectures, build étale cohomology, topos theory, derived categories. The concrete result becomes a corollary once the ocean rises high enough. (SGA 4, SGA 5)

### Find the right category and the proof becomes formal
- **When**: A theorem requires intricate technical arguments in classical language
- **Do**: Search for the categorical framework where the statement is tautological or follows from abstract nonsense
- **Evidence**: Many classical results in algebraic geometry (Serre duality, Riemann-Roch) become formal once you work in derived categories with the right adjunctions and duality functors. (Tohoku paper, derived categories)

### Name and isolate the correct notion
- **When**: Multiple constructions share hidden structure or a pattern repeats
- **Do**: Define the abstract concept (abelian category, topos, scheme, motive) that captures exactly the common invariant
- **Evidence**: Abelian categories axiomatize what's needed for homological algebra; schemes unify varieties and arithmetic; toposes isolate what's needed for cohomology theories. Each definition isolates minimal requirements. (Tohoku, EGA, SGA)

### Reduce to the affine case then glue
- **When**: Proving a property of schemes or sheaves
- **Do**: First prove for affine schemes (where it reduces to commutative algebra), then use gluing/descent to extend to general schemes
- **Evidence**: Coherence, quasi-coherence, flatness, properness — all checked on affine charts first, then glued. The affine case is computable; gluing is formal. (EGA I, faithfully flat descent)

### Use the trivial case to find the structure
- **When**: Generalizing a construction (e.g., from vector bundles to coherent sheaves)
- **Do**: Start with the trivial case (affine line, trivial bundle), identify what structure makes it work, then axiomatize that structure
- **Evidence**: Vector bundles ↔ projective modules; coherent sheaves ↔ coherent modules. The equivalence on Spec(A) guides the general sheaf-theoretic definition. (Serre FAC, EGA)

### Make the parametrization intrinsic
- **When**: Studying families or moduli (curves, varieties, sheaves)
- **Do**: Replace "parameterized by coordinates" with "classified by a representing object" — construct the moduli space/stack that universally represents the functor
- **Evidence**: Hilbert schemes, Picard schemes, moduli stacks. Don't index families by ad-hoc parameters; find the geometric object that *is* the parameter space. (FGA, later developments on stacks)
