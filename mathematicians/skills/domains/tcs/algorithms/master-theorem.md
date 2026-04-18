# Master theorem

The master theorem solves divide-and-conquer recurrences of the form T(n) = a·T(n/b) + f(n), with a ≥ 1 and b > 1. Set c = log_b a. Compare f(n) to n^c:

1. **f(n) = O(n^(c−ε))** for some ε > 0 → T(n) = Θ(n^c). Leaves dominate.
2. **f(n) = Θ(n^c · log^k n)** for some k ≥ 0 → T(n) = Θ(n^c · log^(k+1) n). Balanced.
3. **f(n) = Ω(n^(c+ε))** for some ε > 0, plus the regularity condition a·f(n/b) ≤ k·f(n) for some k < 1 and all large n → T(n) = Θ(f(n)). Root dominates.

One-line rule: whichever of n^c and f(n) is polynomially larger wins; if they match to within logs, multiply by one extra log factor.

Canonical fits:
- merge sort: T(n) = 2T(n/2) + Θ(n), c = 1, Case 2 (k=0) → Θ(n log n).
- binary search: T(n) = T(n/2) + Θ(1), c = 0, Case 2 (k=0) → Θ(log n).
- Strassen: T(n) = 7T(n/2) + Θ(n²), c = log₂ 7 ≈ 2.807, Case 1 → Θ(n^(log₂ 7)).

Pitfalls:
- "Polynomially smaller/larger" requires a gap of at least n^ε; log factors alone do not trigger Case 1 or Case 3.
- Case 3's regularity condition is easy to forget and is required — skipping it is the most common source of wrong applications.
- Only recurrences that divide the input by a constant factor b fit; T(n) = T(n−1) + f(n) is not a master-theorem recurrence.

For unbalanced splits, subtractive recurrences, or log-gap regimes the master theorem does not cover, use the Akra–Bazzi method.

Source: Cormen, Leiserson, Rivest, Stein — *Introduction to Algorithms*, 4th ed., §4.5.
