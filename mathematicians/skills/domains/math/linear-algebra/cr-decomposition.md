# CR decomposition

Every m×n matrix A factors as A = CR, where C is m×r with columns equal to the r independent columns of A (taken in their original order), and R is r×n. The integer r is the rank of A.

R is obtained from the reduced row-echelon form of A by keeping only the nonzero rows. Its pivot columns form the r×r identity, and its free columns state exactly how each dependent column of A is built from the independent ones. Column k of A reads out as A[:, k] = C · R[:, k].

Consequences that drop out directly:

- Column space of A = column space of C, with a basis of r vectors that live in the data itself (no orthogonalization).
- Row space of A = row space of R, with a basis of r vectors already in reduced form.
- Column rank = row rank = r, visible on both sides of the factorization without any further argument.
- A is a sum of r rank-one matrices, A = Σ_k C[:, k] · R[k, :].

CR is a bookkeeping factorization, not a numerical algorithm. Its value is pedagogical and structural: the four fundamental subspaces and the equality of column and row rank are readable off CR with nothing but elimination. No inner products, no least squares, no orthogonality required.

Compared to neighbors: LU adds pivoting and triangularity but hides rank; QR adds orthonormality of C's column basis but costs Gram–Schmidt; SVD adds orthonormal bases on both sides and singular values but costs an eigenproblem on AᵀA. CR is the cheapest factorization that exposes rank and both column and row spaces.

Pitfall: R is not the full rref(A). It drops the zero rows, so R is r×n, not m×n. Using rref(A) as R gives a product whose inner dimension is wrong and whose row space picks up spurious zero rows.

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
