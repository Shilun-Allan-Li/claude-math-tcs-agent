# Spectral theorem

A real symmetric matrix A (A = Aᵀ) admits an orthonormal eigenvector basis: A = QΛQᵀ, with Q orthogonal (QᵀQ = I) and Λ real diagonal. The complex version is Hermitian matrices (A = A*): A = UΛU* with U unitary and Λ real.

Two nontrivial claims are packed into the statement:

- Every eigenvalue of a symmetric (or Hermitian) matrix is real, before any basis is chosen.
- Eigenvectors for distinct eigenvalues are automatically orthogonal; when eigenvalues repeat, the corresponding eigenspace still admits an orthonormal basis (pickable by Gram–Schmidt inside it).

Consequences that get used constantly:

- **Diagonalization is a rotation.** A = QΛQᵀ acts as: rotate into the eigenbasis, scale each axis by λ_k, rotate back. No shear, no skew, no complex stretching.
- **Definiteness is eigenvalue signs.** A is positive definite iff all λ_k > 0, positive semidefinite iff all λ_k ≥ 0. Testing definiteness reduces to signs.
- **Functions of A are entrywise on Λ.** f(A) = Q f(Λ) Qᵀ for any reasonable f: A^k, exp(A), log(A) when A is PD, A^{1/2} when A is PSD.
- **Quadratic forms.** xᵀAx = Σ_k λ_k (q_kᵀx)² — a sum of squares weighted by eigenvalues, the basis for Rayleigh quotients and the Courant–Fischer min-max characterization.

The statement generalizes to normal matrices (AA* = A*A), which also admit an orthonormal eigenbasis but with possibly complex eigenvalues. Unitary, skew-Hermitian, and circulant matrices are all normal and so fall under this umbrella.

Pitfall: the spectral theorem is about the eigendecomposition of symmetric or normal matrices, not about the SVD. For a general non-symmetric matrix, left and right singular vectors live in different spaces and are not eigenvectors of A. Conflating "A = QΛQᵀ" with "A = UΣVᵀ" silently costs you either the nonnegativity of Σ or the symmetry of A.

Source: https://github.com/kenjihiranabe/The-Art-of-Linear-Algebra — The-Art-of-Linear-Algebra.pdf
