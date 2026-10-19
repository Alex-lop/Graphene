# A run on feeds, 7 October 2026

*This run is from 7 October 2026, before the cockpit: its screens are the older ones.*

The run the README showed until 13 October, kept whole. `feeds` is a small test repo I built: csv and json load, a new
supplier's XML doesn't yet, and there are acceptance checks the agents never see. Claude Code (on Sonnet) planned and
did the work. Trimmed where you see `…`:

```
$ graphene ask "Look at this repo. I want the new Northwind XML feed to load the same way csv and json …"
the planner says:
  I left these alone: vendor/, legacy/, normalize/money.py (its `to_major` is flagged as owned by a
  ticket), tests/test_contract.py (marked as not to be edited), and scripts/nightly.sh (stale, but it
  only runs csv).

$ graphene plan accept && graphene run --parallel 2
run: 2 done · agents <1 min, $0.3009 at list price · you 0 acts, 0 min

$ graphene plan --view tree
   Load the Northwind XML feed with the same `load` command as csv and json…
                       ┌───────────────┴───────────────┐
                    ✓ zero                           ✓ xml
          Skip zero prices for every…        Northwind XML source
                       │                               │
                  ✓ zero-rule                     ✓ xml-feed
        Reject price 0 in… $0.13 · <1m     Add the xml… $0.17 · <1m
2 sub-goals · 2 leaves

$ git log --graph --oneline
*   6944ab4 Add the xml reader and wire it in (xml-feed)
|\
| * 6449b2a Add the xml reader and wire it in
|/
*   807669b Reject price 0 in validation (zero-rule)
…
```

It asked me nothing this time. It said what it would leave alone, which is exactly what I'd have checked first, and it
was right. Against the hidden checks it passed 18 of 20 (the 2 misses are a change of mind I never sent) and 12 of 12
held-out, and the six files I'd put off limits weren't touched. Honestly though, in the three comparisons so far a
plain paragraph to the same agent did just as well for less ([the latest](../dev/test/results-2026-09-23.md)). What
I'm betting on is *when* you find out what it understood: before the work, not after.

The closing line reads differently today (`agents <1m, $0.3009 at list price · 2 of 2 at once · you: 0 moves, 0m`);
the run is as it was. [Back to the README](../README.md).
