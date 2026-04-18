# Four fundamental subspaces

Every m×n matrix A has four subspaces attached to it. They live in two ambient spaces and fit together as two orthogonal pairs.

In ℝⁿ (the domain):

- **Row space** C(Aᵀ) — span of the rows of A. Dimension r.
- **Null space** N(A) — solutions of Ax = 0. Dimension n − r.

In ℝᵐ (the codomain):

- **Column space** C(A) — span of the columns of A; equivalently, the image of the map x ↦ Ax. Dimension r.
- **Left null space** N(Aᵀ) — solutions of Aᵀy = 0. Dimension m − r.

The central facts, collectively called the **fundamental theorem of linear algebra**:

1. dim C(A) = dim C(Aᵀ) = r. Column rank equals row rank.
2. dim N(A) = n − r, dim N(Aᵀ) = m − r (rank–nullity in both ambient spaces).
3. C(Aᵀ) ⊥ N(A) in ℝⁿ, and they together span ℝⁿ.
4. C(A) ⊥ N(Aᵀ) in ℝᵐ, and they together span ℝᵐ.

The orthogonality is immediate from the definitions. If Ax = 0, then every row of A is perpendicular to x, so the row space is perpendicular to the null space. Transposing A gives the other pair for free.

Each fundamental subspace reads off cleanly from the right factorization:

- **CR**: columns of C span C(A); rows of R span C(Aᵀ). Rank is the shared inner dimension.
- **SVD**: orthonormal bases for all four at once — first r columns of V for C(Aᵀ), remaining V-columns for N(A); first r columns of U for C(A), remaining U-columns for N(Aᵀ).

Pitfall: "null space" on its own almost always refers to N(A), the solutions of Ax = 0. When N(Aᵀ) also matters, name both explicitly. The left null space is the subspace most often silently dropped when people recite "three subspaces" instead of four.

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
