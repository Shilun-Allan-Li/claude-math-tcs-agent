# Eigendecomposition

An n×n matrix A is diagonalizable when it has n linearly independent eigenvectors. Collecting those eigenvectors as the columns of X and the corresponding eigenvalues on the diagonal of Λ gives A = XΛX⁻¹. Equivalently, AX = XΛ one column at a time: Ax_k = λ_k x_k.

The factorization makes powers and polynomials of A cheap. A^k = XΛ^kX⁻¹, so repeated application of A becomes raising the diagonal Λ to a power. This is the reason eigendecomposition dominates the analysis of linear dynamical systems, Markov chains, and any recurrence of the form v_{k+1} = Av_k: the long-term behavior of v_k is controlled by the eigenvalues of largest modulus.

Not every matrix is diagonalizable. A has n independent eigenvectors iff every eigenvalue's geometric multiplicity (dimension of its eigenspace) equals its algebraic multiplicity (its multiplicity as a root of det(A − λI)). When these disagree, the matrix is *defective*, and the Jordan normal form replaces the diagonal Λ with Jordan blocks that capture the missing dimensions.

Two special cases are substantially stronger:

- **Real symmetric A**: A = QΛQᵀ with Q orthogonal and Λ real. Eigenvectors for distinct eigenvalues are automatically orthogonal; the spectral theorem guarantees this basis exists.
- **Normal A** (AA* = A*A): A = UΛU* with U unitary and Λ complex-diagonal. Includes Hermitian, skew-Hermitian, and unitary matrices as subcases.

Pitfalls:

- Eigendecomposition is basis-specific. For non-symmetric A the columns of X need not be orthogonal, and X⁻¹ can be extremely ill-conditioned — numerical trouble that the SVD does not share.
- A non-square matrix has no eigenvalues. "Eigenvectors of a rectangular matrix" usually means *singular* vectors; do not conflate them.
- Complex eigenvalues are routine even for real A. A real 2×2 rotation has eigenvalues e^{±iθ}; its eigenvectors live in ℂ², not ℝ².

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
