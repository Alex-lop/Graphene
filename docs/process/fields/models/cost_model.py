"""Arithmetic behind models.md sections (d) and (e). Run: python3 cost_model.py
Every price is $/1M tokens, read 2026-09-30; sources are in models.md. Every number marked
ASSUMPTION is a guess to be replaced by a measurement."""

# ---------- (e) LeanMarathon, arXiv 2606.05400, Tables 2 and 3 ----------
LM = {  # run: (GPT-5.5 API-equiv $, total tokens M, proof nodes in final blueprint, new proof nodes)
    "ErdosGraham": (257.17, 308, 111, 111),
    "Erdos1196": (189.43, 245, 44, 44),
    "Prim": (623.54, 796, 147, 103),  # seeded with the 44 #1196 nodes; 103 new obligations
}
GPT55 = (5.0, 0.50, 30.0)  # uncached in, cached in, out (the paper's Table 3 caption; OpenAI page agrees)


def per_node():
    for run, (usd, tok, nodes, new) in LM.items():
        print(
            f"{run:12s} ${usd / nodes:5.2f}/proof node  ${usd / new:5.2f}/new node  ${usd / tok:.3f}/M tokens blended"  # noqa: E501
        )
    usd = sum(v[0] for v in LM.values())
    new = sum(v[3] for v in LM.values())
    print(f"{'all three':12s} ${usd:,.2f} / {new} distinct lemmas+theorems = ${usd / new:.2f}")
    return usd / new


def mix_bounds(usd, tok_m, p=GPT55):
    """Token mix is not published. Cost = pu*u + pc*c + po*o with u+c+o = T.
    Extreme A: no uncached input (max output). Extreme B: no output (max uncached input)."""
    pu, pc, po = p
    extra = usd - pc * tok_m  # $ above the all-cached floor
    o_max = extra / (po - pc)  # A: u = 0
    u_max = extra / (pu - pc)  # B: o = 0
    return {"A": (0.0, tok_m - o_max, o_max), "B": (u_max, tok_m - u_max, 0.0)}


def reprice(mix, p):
    u, c, o = mix
    return p[0] * u + p[1] * c + p[2] * o


SHEETS = {  # (uncached in, cached in, out); Token Factory has no cached price: cached = uncached
    "GPT-5.5 (as paper)": (5.0, 0.50, 30.0),
    "Claude Opus 5.5": (4.0, 0.20, 20.0),
    "GPT-6 Astra": (10.0, 1.00, 50.0),
    "Gemini 3.1 Pro Preview": (2.0, 0.20, 12.0),
    "TF DeepSeek-V4-Flash-0731": (0.14, 0.14, 0.28),
    "TF Nemotron-3-Super": (0.30, 0.30, 0.90),
    "TF Nemotron-3-Ultra": (1.00, 1.00, 3.00),
    "TF DeepSeek-V4-Pro-0813": (1.32, 1.32, 3.96),
    "TF GLM-5.3": (1.40, 1.40, 4.40),
    "TF Kimi-K3": (3.00, 3.00, 15.0),
}


def reprice_leanmarathon():
    usd, tok, nodes, _ = LM["ErdosGraham"]
    m = mix_bounds(usd, tok)
    print(
        f"ErdosGraham token mix bounds (M tokens u/c/o): A={tuple(round(x, 2) for x in m['A'])} B={tuple(round(x, 2) for x in m['B'])}"  # noqa: E501
    )
    assert abs(reprice(m["A"], GPT55) - usd) < 0.01 and abs(reprice(m["B"], GPT55) - usd) < 0.01
    for name, p in SHEETS.items():
        lo, hi = sorted((reprice(m["A"], p), reprice(m["B"], p)))
        print(
            f"  same tokens at {name:28s} ${lo:7.2f}-${hi:7.2f}  = ${lo / nodes:5.2f}-${hi / nodes:5.2f} per proof node"  # noqa: E501
        )


# ---------- (d) cascade per leaf ----------
def attempts_until_success(p, k):
    """Independent attempts with success prob p, capped at k: (E[attempts], P(success))."""
    P = 1 - (1 - p) ** k
    return P / p, P


def cascade(tiers):
    """tiers: list of (name, expected $ spent on a leaf that reaches the tier, P(tier proves it)).
    Returns expected $ per leaf and P(proven) after all tiers."""
    reach, cost = 1.0, 0.0
    for _name, c, p in tiers:
        cost += reach * c
        reach *= 1 - p
    return cost, 1 - reach


def leaf_profiles():
    # T0 automation: ASSUMPTION 60 CPU-seconds per leaf; Nebius CPU-only from $0.05/h (Ice Lake, 2 vCPU
    # min), $0.06 from 2026-10-01.
    c0 = 60 / 3600 * 0.06
    # T1a whole-proof sampling, TF Nemotron-3-Super $0.30/$0.90. ASSUMPTION 2,000 in + 7,000 out tokens per
    # attempt
    # (the 16,384-token cap of arXiv 2606.05632; its Fig 3.3a puts Nemotron near $0.007/attempt by eye).
    c_att = (2000 * 0.30 + 7000 * 0.90) / 1e6
    # homogeneous-equivalent per-attempt p from pass@32 read by eye from Fig A.1/A.2: miniF2F 0.76, miniCTX
    # 0.42.
    p_f2f = 1 - (1 - 0.76) ** (1 / 32)
    p_ctx = 1 - (1 - 0.42) ** (1 / 32)
    ea_f2f, P_f2f = attempts_until_success(p_f2f, 32)
    ea_ctx, P_ctx = attempts_until_success(p_ctx, 32)
    print(
        f"T1a Nemotron-Super: ${c_att:.4f}/attempt; p/attempt miniF2F {p_f2f:.3f} (E att {ea_f2f:.1f}, P {P_f2f:.2f}), "  # noqa: E501
        f"miniCTX {p_ctx:.3f} (E att {ea_ctx:.1f}, P {P_ctx:.2f}); $/proven = ${c_att / p_f2f:.3f} / ${c_att / p_ctx:.3f}"  # noqa: E501
    )
    # T1b agent loop on TF DeepSeek-V4-Flash-0731 repriced from NEAR costs.tsv (no cache): median $0.19, p90
    # $2.08.
    # ASSUMPTION cap $2/leaf; ASSUMPTION P(prove within cap) per profile below.
    # T2 frontier agent: Forall (Claude Opus 5 xhigh) mean $3.52/Putnam problem; x0.8 for Opus 5.5 list =
    # $2.82 (same tokens);
    # LeanMarathon GPT-5.5: $2.32-$6.05 per research proof node.
    # T3 Aristotle: $0 fee today (terms 2026-09-24), hours of wall time. T4 the person: ASSUMPTION $100/h.
    person_hour = 100.0
    profiles = {
        # name: list of (tier, $ spent on a leaf reaching it, P(proves)) ; all P are ASSUMPTIONS unless noted
        "textbook leaf (Lagrange/FLT chain)": [
            ("T0 automation", c0, 0.60),
            ("T1a Nemotron-Super x<=32", c_att * ea_f2f, P_f2f),  # miniF2F-like after automation
            ("T2 Opus 5.5 agent", 2.82, 0.95),
            ("T4 person 30 min", person_hour * 0.5, 1.0),
        ],
        "competition-hard leaf (Putnam-like)": [
            ("T0 automation", c0, 0.05),
            ("T1b V4-Flash agent, cap $2", 2.0 * 0.5, 0.85),  # ASSUMPTION mean spend = half the cap
            ("T2 Opus 5.5 agent", 2.82 * 2, 0.80),  # ASSUMPTION residue costs 2x the mean
            ("T4 person 3 h", person_hour * 3, 1.0),
        ],
        "research leaf (LeanMarathon-like)": [
            ("T0 automation", c0, 0.02),
            ("T1a Nemotron-Super x<=32", c_att * ea_ctx, 0.10),  # ASSUMPTION well below miniCTX 0.42
            ("T2 GPT-5.5 harness", 4.15, 0.90),  # LeanMarathon mean per distinct node
            ("T3 Aristotle", 0.0, 0.30),
            ("T4 person 4 h", person_hour * 4, 1.0),
        ],
    }
    for name, tiers in profiles.items():
        cost, P = cascade(tiers)
        print(f"{name}: expected ${cost:.2f} per leaf, P(proven) {P:.2f}")
        reach = 1.0
        for t, c, p in tiers:
            print(
                f"    {t:30s} reached by {reach:6.3f} of leaves, spends ${c:7.3f} there -> contributes ${reach * c:6.3f}; proves {p:.2f} of what reaches it"  # noqa: E501
            )
            reach *= 1 - p
        # the same leaf sent straight to the frontier tier, then the person
        ft = next(x for x in tiers if x[0].startswith("T2"))
        print(
            f"    frontier-first (skip T0/T1): ${cascade([ft, tiers[-1]])[0]:.2f};  person-only: ${tiers[-1][1]:.2f}"  # noqa: E501
        )
    return profiles


if __name__ == "__main__":
    mean = per_node()
    assert 4.14 < mean < 4.16  # $1,070.14 / 258
    reprice_leanmarathon()
    # self-check of the cascade formula: one tier that always proves costs exactly its price
    assert cascade([("x", 3.0, 1.0)]) == (3.0, 1.0)
    assert abs(cascade([("a", 1.0, 0.5), ("b", 10.0, 1.0)])[0] - 6.0) < 1e-9
    leaf_profiles()
