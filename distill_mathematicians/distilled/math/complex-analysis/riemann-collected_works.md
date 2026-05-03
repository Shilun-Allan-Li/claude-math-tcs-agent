# Distilled: riemann-collected_works

**Source**: Gesammelte Mathematische Werke
**URL**: https://archive.org/details/gesammeltemathem0000bern
**Tags**: math.HO, math.CV, math.DG

## Heuristics

### Complexify the domain
- **When**: Facing a real-variable problem (integration, number theory, geometry)
- **Do**: Extend functions and domains to the complex plane; study the problem on a Riemann surface
- **Evidence**: Riemann's zeta function extends Euler's sum to the complex plane; abelian integrals live on multi-sheeted surfaces (Riemann surfaces). The dissertation "Grundlagen für eine allgemeine Theorie der Functionen" systematically builds function theory by first defining domains in C.

### Exploit holomorphy plus boundary data
- **When**: A function is holomorphic on a domain and you know its boundary behavior
- **Do**: Apply Cauchy's theorem, residue calculus, or conformal mapping; the interior is determined by the boundary
- **Evidence**: Riemann mapping theorem (every simply connected domain ≠ C is conformally equivalent to the unit disk). Dirichlet problem solved via analytic continuation and harmonic measure.

### Replace point-by-point estimates with topological/global arguments
- **When**: Direct local analysis is intractable
- **Do**: Use connectivity, monodromy, genus, or a "continuity method" (vary a parameter, track the solution)
- **Evidence**: Riemann's existence theorem for algebraic functions uses topological properties (branch points, sheets) rather than explicit formulas. His proof of the mapping theorem uses Dirichlet's principle (variational/global energy minimization).

### Introduce geometric invariants (curvature, metric)
- **When**: Studying manifolds, surfaces, or higher-dimensional spaces
- **Do**: Define a Riemannian metric; compute curvature; classify by curvature invariants
- **Evidence**: "Über die Hypothesen, welche der Geometrie zu Grunde liegen" (1854 Habilitationsschrift) introduces the Riemann curvature tensor and the concept of manifold with intrinsic metric, unifying elliptic/Euclidean/hyperbolic geometries.

### Count zeros/poles via integration (argument principle)
- **When**: You need to locate or count solutions to f(z)=0 in a region
- **Do**: Integrate (1/2πi)∫(f'/f)dz around the boundary; the result is #zeros - #poles (with multiplicity)
- **Evidence**: Core technique in complex analysis used throughout Riemann's work on meromorphic functions and in the study of the zeta function's non-trivial zeros.

### Reformulate existence as a variational/potential problem
- **When**: Proving a function exists with prescribed properties
- **Do**: Minimize an energy functional (Dirichlet integral) over an appropriate space
- **Evidence**: Riemann's original "proof" of the mapping theorem via Dirichlet's principle: minimize ∫|∇u|² among functions with given boundary values. (Later made rigorous by Hilbert and Weyl, but the operational heuristic is Riemann's.)

### Use analytic continuation to eliminate case distinctions
- **When**: A formula or function is initially defined piecewise or on a restricted domain
- **Do**: Extend it analytically; the continuation often unifies disparate cases into a single global object
- **Evidence**: ζ(s) defined for Re(s)>1 by a series; Riemann's functional equation extends it to all s∈C (except s=1), revealing symmetry and connecting values at s and 1-s.
