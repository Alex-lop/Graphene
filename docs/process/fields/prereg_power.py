"""Operating characteristics for the fields pre-registration (docs/process/fields/PREREG.md).

Standard library only, exact where it can be, seeded where it simulates:
    python3 docs/process/fields/prereg_power.py

1. Arms compared on targets proven: exact McNemar power for paired targets.
2. Kill criterion 1: the chance that "fewer than one real catch per ten statements" fires,
   for a true marginal catch rate r and n statements reviewed.
3. Kill criterion 2: the chance that "median review time over median write time > 0.5" fires,
   when times are lognormal (the spread is an assumption, printed with the table).
4. Seeded defects: the 95% interval on a catch rate for k of m seeded defects caught.
"""

import math
import random
from statistics import median


def binom_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * p**k * (1 - p) ** (n - k)


def binom_cdf(k: int, n: int, p: float) -> float:
    return sum(binom_pmf(i, n, p) for i in range(0, k + 1))


def mcnemar_rejects(b: int, d: int, alpha: float = 0.05) -> bool:
    """Exact two-sided McNemar: b of d discordant pairs favour one arm."""
    if d == 0:
        return False
    tail = min(binom_cdf(b, d, 0.5), 1 - binom_cdf(b - 1, d, 0.5))
    return min(1.0, 2 * tail) <= alpha


def mcnemar_power(n: int, p_only_c: float, p_only_other: float, alpha: float = 0.05) -> float:
    """Power when p_only_c of targets is proven only in arm C, and p_only_other only in the other arm."""
    pd = p_only_c + p_only_other
    share = p_only_c / pd
    power = 0.0
    for d in range(0, n + 1):
        pdd = binom_pmf(d, n, pd)
        if pdd < 1e-12:
            continue
        for b in range(0, d + 1):
            if mcnemar_rejects(b, d, alpha) and b > d / 2:
                power += pdd * binom_pmf(b, d, share)
    return power


def wilson(k: int, m: int, z: float = 1.96) -> tuple[float, float]:
    if m == 0:
        return (0.0, 1.0)
    p = k / m
    den = 1 + z * z / m
    centre = (p + z * z / (2 * m)) / den
    half = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def k2_fires(n_each: int, true_ratio: float, sigma: float, runs: int, rng: random.Random) -> float:
    fired = 0
    for _ in range(runs):
        write = [math.exp(rng.gauss(0, sigma)) for _ in range(n_each)]
        review = [true_ratio * math.exp(rng.gauss(0, sigma)) for _ in range(n_each)]
        if median(review) / median(write) > 0.5:
            fired += 1
    return fired / runs


def main() -> None:
    print("1. Targets proven, arm C against arm A or B (exact McNemar, two-sided alpha 0.05)")
    print("   power to detect C ahead, by targets n and discordant shares (only C, only the other)")
    shares = [(0.20, 0.05), (0.15, 0.05), (0.10, 0.02), (0.10, 0.05)]
    print("   n    " + "  ".join(f"C {a:.2f}/o {b:.2f}" for a, b in shares))
    for n in (10, 20, 30, 50, 80, 120):
        print(f"   {n:<4} " + "  ".join(f"{mcnemar_power(n, a, b):>13.2f}" for a, b in shares))

    print()
    print("2. Kill criterion 1 fires when marginal catches / statements < 0.10")
    print("   chance it fires, by statements reviewed n (rows) and true marginal catch rate r")
    rates = [0.02, 0.05, 0.10, 0.15, 0.20, 0.30]
    print("   n    " + "  ".join(f"r={r:.2f}" for r in rates))
    for n in (20, 40, 60, 100, 150):
        cut = math.ceil(0.10 * n) - 1  # fires when catches <= cut
        print(f"   {n:<4} " + "  ".join(f"{binom_cdf(cut, n, r):>6.2f}" for r in rates))

    print()
    print("3. Kill criterion 2 fires when median review time / median write time > 0.5")
    print("   lognormal times, sigma = 0.8 on the log scale (an assumption: typical of task times);")
    print("   chance it fires, by statements per condition n and true ratio of medians")
    rng = random.Random(20260930)
    ratios = [0.2, 0.3, 0.4, 0.5, 0.6, 0.8]
    print("   n    " + "  ".join(f"t={t:.1f}" for t in ratios))
    for n in (10, 20, 30, 50):
        print(f"   {n:<4} " + "  ".join(f"{k2_fires(n, t, 0.8, 4000, rng):>5.2f}" for t in ratios))

    print()
    print("4. Seeded defects: 95% Wilson interval on a catch rate, k caught of m seeded")
    for m in (10, 20, 30):
        row = []
        for k in (m // 4, m // 2, (3 * m) // 4):
            lo, hi = wilson(k, m)
            row.append(f"{k}/{m}: {lo:.2f}-{hi:.2f}")
        print("   " + "   ".join(row))


if __name__ == "__main__":
    main()
