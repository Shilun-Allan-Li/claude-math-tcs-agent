# LU decomposition

For a square matrix A that can be reduced to echelon form without row swaps, A = LU, where L is lower triangular with ones on the diagonal and U is upper triangular. L records the multipliers used in Gaussian elimination — entry L[i, j] is the multiplier subtracted from row i using row j. U is the echelon form that elimination produces.

The factorization turns Ax = b into two triangular solves: first Ly = b by forward substitution, then Ux = y by back substitution. Each triangular solve costs O(n²), compared to O(n³) for elimination. That amortization is why LU is the standard way to handle many right-hand sides with the same A: pay O(n³) once to form L and U, then O(n²) per new b.

When row swaps are needed — as soon as a zero or near-zero pivot appears — the factorization becomes PA = LU, with P a permutation matrix reordering the rows of A. Partial pivoting, which chooses the largest available pivot in each column, is the default variant used for numerical stability because it keeps every entry of L bounded by 1 in absolute value. Full pivoting (also reordering columns) is more stable still but rarely worth the cost.

Notation to watch: the U in LU is the upper-triangular elimination factor and is unrelated to the left-singular-vector matrix in SVD. The letter collides across factorizations.

Pitfalls:

- LU without pivoting can fail even for an invertible A. A zero pivot during elimination is an ordering problem, not a rank problem; use PA = LU.
- The shortcut det(A) = product of U's pivots holds only when no row swaps occur. With pivoting, include det(P) = ±1 explicitly.
- L and U are not unique without the convention "L has unit diagonal." Different numerical libraries sometimes use the opposite convention (unit diagonal on U), which silently transposes the split.

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
