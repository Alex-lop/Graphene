# The arithmetic behind "models and money"

Written by the fields run's models researcher on 2026-09-30. Linted by the integrator; `ruff format`
changed the layout only, and the output is byte for byte the same as before. Standard library only.

- `python3 cost_model.py` prints two things.
  - **(e)** LeanMarathon's cost per proof node from its Tables 2 and 3 (arXiv 2606.05400): $2.32, $4.31 and
    $6.05 per new node, $4.15 pooled. Also the same token counts repriced at other list prices.
  - **(d)** The cascade's expected cost per leaf for three leaf profiles: automation, then a cheap open model,
    then a frontier model or Aristotle, then the person.
- **Every price** was read on 2026-09-30. `../landscape.md` §5 lists each price page. The researcher's full
  notes stay on the machine that made them.
- **Every number marked `ASSUMPTION`** in the script is a guess, to be replaced by a measurement. That covers
  every success probability except where a source is named, and the person's hourly rate and minutes per
  leaf.
- **One is now measured.** The textbook profile assumes automation closes 60% of leaves. On the fields
  spike's tree it closed 3 of 8, 37.5% (`../spikes/lean/primes/Auto/baseline.md`).
- `python3 reprice_near.py` reprices NEAR AI's PutnamBench trajectories at Token Factory's list prices,
  which have no cached-input rate. It needs NEAR's public `costs.tsv` next to it, saved as
  `near-costs.tsv`. That file was read at commit `bedec8e` of
  https://github.com/SkidanovAlex/putnambench-deepseek (2026-08-27). It is not copied here.
