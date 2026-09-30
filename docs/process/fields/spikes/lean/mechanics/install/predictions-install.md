# Predictions written before the Lean install (2026-09-30 ~00:55 EDT, before any command ran)

- elan + toolchain v4.34.1 download: expect the toolchain to unpack to 0.8-1.6 GB under ~/.elan, and to take 1-3 minutes on home broadband.
- `lake exe cache get` for Mathlib v4.34.1: expect 4-7 GB unpacked in .lake/packages (mathlib build ~5 GB), roughly 0.8-1.5 GB downloaded into ~/.cache/mathlib, 2-6 minutes.
- `git clone` of mathlib and deps by `lake update`: expect 0.5-1 GB of git objects, 1-3 minutes.
- First `lake build` of a one-file project importing Mathlib (after the cache): expect 10-40 s, dominated by loading oleans.
