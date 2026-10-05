import Architect
import Proofs.Root

/-!
# The primes-3-mod-4 tree in LeanArchitect's form

Each leaf's theorem is a blueprint node with its statement in words and, as `uses`, the leaves it
needs. The attributes are added here, after the fact, so the challenge and the proofs stay as the
gate checks them.
-/

attribute [blueprint "prime_mod_four" (title := /-- Odd primes mod 4 -/)
  (statement := /-- A prime $p \neq 2$ satisfies $p \equiv 1$ or $p \equiv 3 \pmod 4$. -/)]
  prime_mod_four

attribute [blueprint "mul_one_mod_four"
  (statement := /-- If $a \equiv 1 \pmod 4$ then $ab \equiv b \pmod 4$. -/)]
  mul_one_mod_four

attribute [blueprint "factor_three_mod_four" (title := /-- Key lemma -/)
  (statement := /-- Every $n \equiv 3 \pmod 4$ has a prime factor $p \equiv 3 \pmod 4$. -/)
  (uses := ["prime_mod_four", "mul_one_mod_four"])]
  factor_three_mod_four

attribute [blueprint "euclid_mod_four"
  (statement := /-- For $P > 0$, $4P - 1 \equiv 3 \pmod 4$ (in $\mathbb{N}$, $4 \cdot 0 - 1 = 0$). -/)]
  euclid_mod_four

attribute [blueprint "not_dvd_euclid"
  (statement := /-- For $P > 0$, a prime $p \mid P$ does not divide $4P - 1$. -/)]
  not_dvd_euclid

attribute [blueprint "dvd_factorial"
  (statement := /-- Every $p$ with $0 < p \le n$ divides $n!$. -/)]
  dvd_factorial

attribute [blueprint "euclid" (title := /-- Euclid's argument -/)
  (statement := /-- For every $n$ there is a prime $p > n$ with $p \equiv 3 \pmod 4$. -/)
  (uses := ["factor_three_mod_four", "euclid_mod_four", "not_dvd_euclid", "dvd_factorial"])]
  euclid

attribute [blueprint "set_form"
  (statement := /-- The set of primes $p \equiv 3 \pmod 4$ is infinite. -/) (uses := ["euclid"])]
  set_form

attribute [blueprint "root" (title := /-- Infinitely many primes $\equiv 3 \pmod 4$ -/)
  (statement := /-- There are infinitely many primes congruent to $3$ mod $4$. -/)]
  root_set

#show_blueprint
