# QR decomposition

Any m×n matrix A with linearly independent columns factors as A = QR, where Q is m×n with orthonormal columns (QᵀQ = I) and R is n×n upper triangular with positive diagonal entries. The columns of Q are the Gram–Schmidt orthonormalization of the columns of A, and R stores the coefficients that express each column of A in terms of the Q-columns processed so far.

Because Q has orthonormal columns, Qᵀ is a left inverse: QᵀA = R. That identity is the engine of least squares. To solve min ‖Ax − b‖ for full-column-rank A, multiply the normal equations by Qᵀ and the problem collapses to Rx = Qᵀb, a single triangular back-substitution. QR avoids forming AᵀA, whose condition number is the square of A's — the reason QR is preferred to the normal equations whenever A is at all ill-conditioned.

Variants:

- **Full QR**: Q is m×m orthogonal (square), R is m×n with a zero block below row n. Useful when a basis for the left null space of A is needed.
- **Thin QR**: Q is m×n, R is n×n. The economical form used in practice.

Implementations, in ascending order of numerical quality:

- Classical Gram–Schmidt: unstable, later Q-columns lose orthogonality to earlier ones.
- Modified Gram–Schmidt: orthogonalizes against running partial sums; substantially better.
- Householder reflections or Givens rotations: produce QR directly without explicit orthogonalization; the library default.

Pitfall: A = QR as stated requires independent columns. For rank-deficient A, plain QR puts a zero on the diagonal of R and the corresponding Q-column is undetermined. The fix is either QR with column pivoting (AP = QR, where P moves dependent columns to the back) or, when the rank structure really matters, the SVD. Treating a defective QR output as if it were full-rank is a common silent error.

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
