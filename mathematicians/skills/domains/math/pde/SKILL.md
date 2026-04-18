---
name: pde
description: |
  TRIGGER when: problem involves a partial differential equation —
  classical (Laplace, heat, wave, Navier–Stokes, Burgers) or
  abstract; weak / strong / classical solutions; Sobolev spaces;
  energy estimates; maximum principles; method of characteristics;
  Galerkin or fixed-point existence proofs; semigroup theory.
  SKIP when: problem is purely an ODE; numerical schemes for PDE
  (use a numerical-analysis skill — not yet curated); PDE on
  Riemannian manifolds qua geometric flow (use a geometric-analysis
  skill — not yet curated).
canonical-id: math.pde
layer: domain
status: curated
taxonomy:
  msc: ["35-XX"]
  arxiv: []
depends-on: [core.proof-writing, math.real-analysis]
---

## Purpose

Conventions and named theorems for partial differential equations:
classification, function-space framework, and existence/uniqueness
techniques.

## How to use

1. **Classify the PDE** first: linear vs. nonlinear; order; elliptic
   / parabolic / hyperbolic; quasilinear vs. fully nonlinear.
2. **Specify the function space**: classical `C^k`, Hölder
   `C^{k,\alpha}`, Sobolev `W^{k,p}`, distributional. Solution
   regularity follows the space.
3. **State the boundary / initial conditions** completely. Existence
   theorems are sensitive to these.
4. **Pick a method** matched to the type:
   - Elliptic: Lax–Milgram, variational, Schauder.
   - Parabolic: Galerkin, energy method, semigroup.
   - Hyperbolic: characteristics, energy method.

## Notation and conventions

- Domain: `\Omega \subseteq \mathbb{R}^n`, boundary `\partial \Omega`.
- Sobolev space: `W^{k,p}(\Omega)`, `H^k = W^{k,2}`.
- Hölder: `C^{k,\alpha}(\Omega)`.
- Operators: Laplacian `\Delta`, gradient `\nabla`, divergence
  `\nabla \cdot`, Hessian `D^2 u`.
- Test functions `\varphi \in C_c^\infty(\Omega)`.

## Canonical theorems (cite by name)

- **Lax–Milgram**: existence/uniqueness of weak solutions to coercive
  bilinear forms on a Hilbert space.
- **Sobolev embedding theorem** (Gagliardo–Nirenberg–Sobolev).
- **Rellich–Kondrachov compactness**.
- **Trace theorem**: `H^1(\Omega) \to H^{1/2}(\partial \Omega)` bounded.
- **Poincaré inequality**.
- **Maximum principle** (weak and strong, for elliptic / parabolic).
- **Schauder estimates**, **De Giorgi–Nash–Moser** regularity.
- **Hille–Yosida** for `C_0`-semigroups.
- **Method of characteristics** for first-order PDE.
- **Energy method** for hyperbolic / parabolic.

## Common pitfalls

- Treating a weak solution as classical without regularity argument.
- Forgetting boundary conditions when integrating by parts.
- Sobolev embedding fails at the critical exponent — track the
  exact range carefully (`p < n / k` etc.).
- Maximum principle requires the right sign convention on operator
  and source term.
- Using compactness arguments where embedding is not compact (e.g.,
  `H^1(\mathbb{R}^n) \hookrightarrow L^2(\mathbb{R}^n)` is not).
- Method of characteristics breaks at shocks — for nonlinear
  hyperbolic PDE, weak entropy solutions are needed.

## References

(none yet)
