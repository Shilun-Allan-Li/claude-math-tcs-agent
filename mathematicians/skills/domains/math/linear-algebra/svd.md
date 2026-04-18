# Singular value decomposition

Every m×n matrix A factors as A = UΣVᵀ, where U is m×m orthogonal, V is n×n orthogonal, and Σ is m×n with nonnegative entries σ₁ ≥ σ₂ ≥ … ≥ σ_r > 0 on the leading diagonal and zeros elsewhere. The σ_k are the singular values of A; r is the rank of A.

The factorization exists for every matrix — no diagonalizability assumption, no squareness assumption — and is essentially unique (up to signs and the handling of repeated singular values). This universality is the reason SVD is the default factorization whenever the structure of A is unknown or degenerate.

Geometric reading: A maps the unit sphere in ℝⁿ to an ellipsoid in ℝᵐ. The columns of V are orthonormal preimages of the ellipsoid's axes; the columns of U are the orthonormal axes themselves; the σ_k are the axis lengths. In short, "A rotates, stretches along orthogonal axes, then rotates."

Subspace payoffs read off the SVD directly:

- The first r columns of V span the row space; the remaining n − r columns span the null space.
- The first r columns of U span the column space; the remaining m − r columns span the left null space.
- The best rank-k approximation to A in both Frobenius and spectral norms is U[:, :k] Σ[:k, :k] V[:, :k]ᵀ (Eckart–Young).
- The 2-norm condition number of A is σ₁ / σ_r — an intrinsic quantity, visible at a glance.

Relation to eigendecomposition: the σ_k² are the eigenvalues of both AᵀA and AAᵀ; V diagonalizes AᵀA, and U diagonalizes AAᵀ. The SVD is essentially the eigendecomposition of the PSD matrix AᵀA, repackaged so that A itself appears.

Pitfall: never solve min ‖Ax − b‖ by forming AᵀA and diagonalizing it. The condition number squares when you do, so fine detail is lost to roundoff. Use QR or the SVD directly.

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
