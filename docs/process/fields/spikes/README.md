# The fields spikes: what each is, and how to rerun it

All run on 2026-09-30, with no model, no key and no spend. Each directory's README has every command,
version and output, and a "Rerun" section. Each prediction was written before its measurement, in a
`PREDICTIONS.md` beside it.

| Directory | What it asks | Needs | Rerun |
|---|---|---|---|
| `lean/mechanics/` | What Lean and Mathlib cost to install and check. What `#print axioms` shows. Cold against warm. | elan, Lean v4.34.1, Mathlib v4.34.1 (7.6 GB), Docker for comparator's sandbox | `lean/mechanics/README.md`, "Rerun" |
| `lean/gate/` | The check a Lean leaf carries: trusted inputs, a sandboxed build, type and axioms, kernel replay, SafeVerify, comparator | the tools, built by `install-tools.sh` (about 40 s) | `GATE_TRUSTED_REF=… GATE_TRUSTED_LAKE=… ./gate.sh PROJECT LEAF…` (`lean/gate/README.md`) |
| `lean/primes/` | The worked tree (primes ≡ 3 mod 4) in Graphene's text and in Lean; what $0 of automation closes; the seeded false leaf | as mechanics; Graphene from this repository (`uv run --project`) | `lean/primes/README.md`, "Rerun" |
| `redteam/` | 21 attacks on the gate, against seven layers, on core Lean; the scope layer on the real Graphene. Read its "Review" first | the tools; core Lean only, so no Mathlib | `./run_all.sh` (about 2 minutes) |
| `redteam/round2/` | One more attack (a stored axiom list), and two holes left open | — | not rerunnable: its scratch files were not kept, so only the record is here |
| `bio/` | Four checks as exit codes over 6,400 ClinVar records in six cancer genes | Python 3, network access to NCBI, UniProt and AlphaFold DB | `./run.sh` (about 65 s cold) |
| `bio/research/` | Two measurements the plan cites: MANE against UniProt canonical, and a KRAS join | Python 3, the public data named in its README | `bio/research/README.md` |

**The machine these ran on.** Apple silicon, 11 cores, 18 GB of RAM.
- Every wall time that includes loading Mathlib is that night's loaded machine, not Lean's, and says so.
- On such a machine, run one Mathlib-loading process at a time. Three at once took free disk under 15 GB,
  because swap lives on the same disk (`lean/gate/cost.md`).
