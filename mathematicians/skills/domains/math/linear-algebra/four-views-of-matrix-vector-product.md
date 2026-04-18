# Four views of the matrix-vector product

The product Ax, with A of size m×n and x in ℝⁿ, admits four equivalent readings. Each is the right tool in a different setting; switching between them is the single most useful skill in applied linear algebra.

**1. Row-by-row: dot products.** Entry i of Ax is the dot product of row i of A with x. This is the entry-level definition and the fastest hand computation for small A.

**2. Column-by-column: linear combination of columns.** Ax = x₁·A[:, 1] + x₂·A[:, 2] + … + x_n·A[:, n]. This reading makes the column space visible: Ax ranges over C(A) and nothing else. When the question is existence of a solution to Ax = b, this is the view to hold — b is reachable iff it lies in C(A).

**3. Low-rank sum (outer-product form).** Write A as a sum of rank-one pieces A = Σ_k u_k v_kᵀ, via whichever factorization fits (CR, SVD, eigendecomposition). Then Ax = Σ_k u_k (v_kᵀ x), a weighted sum of direction vectors u_k with weights v_kᵀ x read off from x by the v_k. This is the operative view for SVD-based low-rank approximation, PCA, and compression.

**4. As a linear map.** A is the matrix of a linear transformation T : ℝⁿ → ℝᵐ written in the standard basis. Ax is "apply T to x." Change of basis, composition, and invariants (rank, trace, determinant) are natural in this view and awkward in the others.

Pitfall: the column-combination view and the row-dot-product view are equally correct but not equally informative. Questions about *which b are reachable* want the column view; questions about *which x satisfy a constraint* want the row view. Reaching for the wrong view — especially row-dot-products when the real question is about C(A) — is a common source of proofs that get stuck after a page of correct but unilluminating arithmetic.

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
