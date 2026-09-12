<!-- p.1 -->

# Unit 1 — Divisibility

## 1.1 Divisibility

Throughout this unit $a$, $b$ and $c$ denote natural numbers.

We say that $a$ *divides* $b$, written $a \mid b$, if there is a natural number $q$ with $b = a q$.

**Theorem 1.1** If $a \mid b$ and $b \mid c$, then $a \mid c$.

*Proof* Write $b = a q$ and $c = b r$. Then $c = (a q) r = a (q r)$, so $a \mid c$. □

**Theorem 1.2** If $a \mid b$ and $a \mid c$, then $a \mid (b + c)$.

*Proof* Write $b = a q$ and $c = a r$. Then $b + c = a q + a r = a (q + r)$. □

<!-- p.2 -->

## 1.2 Consequences

**Theorem 1.3** If $a \mid b$ and $a \mid c$, then $a \mid (b + b + c)$.

*Proof* By theorem 1.2, $a \mid (b + c)$. Applying theorem 1.2 again to $b$ and $b + c$ gives $a \mid (b + (b + c))$, which is the claim by associativity. □

*Exercises*

1.2.1 Show that $a \mid 0$ for every $a$.

1.2.2 Show that if $a \mid b$ and $b \mid a$ then $a = b$.
