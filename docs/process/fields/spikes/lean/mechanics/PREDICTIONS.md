# Predictions, then results

Each entry is written before the measurement runs (the timestamp is when it was written), and the
result is appended beside it afterwards. Machine: MacBook, Apple silicon, 11 cores, 18 GB RAM,
macOS (Darwin 25.5.0). Lean 4.34.1, Mathlib v4.34.1 (d13f23b7).

## P1. Cloning the base project's .lake (144,200 files, 7.6 GB) with APFS copy-on-write
- 2026-09-30 00:59:29 EDT prediction: `cp -cR base/.lake mechanics/.lake` takes 20-60 s (one clonefile per
  file, 144k files) and `df` free space drops by under 0.5 GB (metadata only). Guess, not measured before.
- result: 28.0 s wall (22.9 s sys), free space fell by 82 MB (38,903,336 KB -> 38,821,512 KB). Inside the
  predicted range.

## P2. `lake build` of a leaf-sized file, with and without `sorry`
- 2026-09-30 01:01:23 EDT prediction: `lake build Measure.Clean` (first build in this project; the Mathlib
  oleans are clones, so the page cache may be cold for them): rc 0, 10-150 s. `lake build Measure.Sorry`
  right after: rc 0 (sorry is a warning, not an error), warning text
  "declaration uses 'sorry'", 3-15 s. `lake build --wfail Measure.Sorry` after it was built: rc 1, and I
  expect Lake to fail on the replayed warning too (not sure; Lake replays logs of cached modules).
  `lake build --wfail Measure.Clean`: rc 0.

## P3. `#print axioms` output
- 2026-09-30 01:01:23 EDT prediction: clean (`Int.mul_emod`, `norm_num`) -> `'clean' depends on axioms:
  [propext, Classical.choice, Quot.sound]` (norm_num pulls in Classical.choice through Mathlib's ring
  lemmas; could be fewer). sorry -> the list includes `sorryAx`. native_decide -> the list includes
  `Lean.ofReduceBool` (and maybe `Lean.trustCompiler`, which newer Lean versions add). declared axiom
  -> the list includes `cheat`.

- P2 result (logs/build-*.log): the machine was under memory pressure the whole time (swap 13.7-13.9 GB of
  14.3-15.4 GB used, Docker's VM and a browser resident, another agent building Lean beside this one;
  load average 4-5 on 11 cores). Every *new* build of a one-lemma file that imports Mathlib took
  2.5-4 minutes, not the 3-15 s predicted:
  - `lake build Measure.Clean`: rc 0, 193.5 s (Lean's own line: "Built Measure.Clean (184s)"), peak
    RSS 1.7 GB. The lean process ran at ~12% CPU while it loaded, so the time is spent paging, not
    computing.
  - `lake build Measure.Sorry` right after: rc 0, 183.7 s, so the second build was not faster (the
    first-build-is-cold guess was wrong). Output: `warning: Measure/Sorry.lean:3:8: declaration uses
    `sorry`` then `info: ... 'withSorry' depends on axioms: [sorryAx]`, "Build completed
    successfully". A sorry does not fail `lake build`.
  - `lake build --wfail Measure.Sorry` (module already built, so Lake replayed it): rc 1 in 5.6 s,
    "Some required targets logged failures: - Measure.Sorry / error: build failed". So --wfail does fail
    on a replayed warning (the uncertain part of the prediction held).
  - `lake build --wfail Measure.Clean` (replayed): rc 0, 3.8 s.
  - `lake build Measure.Native`: rc 0, 256.4 s. `lake build Measure.Axiom`: rc 0, 163.1 s.
- P3 result, exact `#print axioms` lines (from the build logs):
  - clean: `'clean' depends on axioms: [propext, Classical.choice, Quot.sound]` (as predicted)
  - sorry: `'withSorry' depends on axioms: [sorryAx]` (as predicted)
  - native_decide: `'withNative' depends on axioms: [propext, withNative._native.native_decide.ax_1_1]`.
    **Prediction wrong**: Lean 4.34.1 no longer shows `Lean.ofReduceBool`; `native_decide` now adds an
    auxiliary axiom named after the theorem (`<thm>._native.native_decide.ax_1_1`). A check that
    looks for `Lean.ofReduceBool` by name (a deny-list) would pass this proof; only an allow-list of
    exactly propext, Classical.choice and Quot.sound rejects it.
  - declared axiom: `'withAxiom' depends on axioms: [cheat]` (as predicted)

## P4. Building the tools against v4.34.1 (gate/install-tools.sh)
- 2026-09-30 01:16:18 EDT prediction: repl (tag v4.34.0 with the toolchain bumped to v4.34.1) builds with no
  source change in 1-4 min. comparator v4.34.0 + lean4export build with no source change in 2-6 min.
  SafeVerify (written for v4.27.0) needs source fixes for seven minor versions of API drift: I give it
  50% to build unchanged. LeanParanoia (v4.25.0, depends on the archived lean4checker) fails to build
  without code changes; 30% it builds after swapping in core's Lean.Replay.

- P4 result (logs/install-*.log): repl built unchanged in 12.4 s; comparator + lean4export built
  unchanged in 10.7 s (both far faster than predicted: neither imports Mathlib). SafeVerify failed
  first (`Unknown identifier CollectAxioms.collect`: Lean made it private) and built in 13.0 s after a
  four-line port to the public `Lean.collectAxioms` (the patch is in gate/install-tools.sh).

## P5. Building the layout (Challenge, Spec.*, Proofs.*)
- 2026-09-30 01:18:53 EDT prediction: `lake build` (Challenge, then 3 Spec and 3 Proofs modules, Lake runs
  what it can in parallel): rc 0 with 3 `sorry` warnings from Spec, 6-12 min on this loaded machine
  (Challenge ~3 min, then the rest in parallel ~3-6 min). My proofs of sqMod4/sumTwoSq/root were
  written without Lean at hand: 60% all three compile first time.

- P5 result (logs/build-layout.log): rc 0 in 692.5 s (11.5 min), all three proofs compiled first time;
  three `declaration uses sorry` warnings, one per Spec stub, as expected. Lean's per-module times:
  Challenge 165 s; then Spec.Root, Spec.SqMod4, Spec.SumTwoSq, Proofs.SqMod4, Proofs.SumTwoSq in
  parallel, 294 s each; then Proofs.Root 224 s. Every module pays the Mathlib import again.

## P6. One-lemma check, cold against warm (mechanics/cold_warm.py, 5 runs each)
- 2026-09-30 01:31:44 EDT prediction: on this memory-starved machine a cold `lake env lean Measure/Clean.lean`
  costs about what a module build costs: median 120-240 s (on an idle machine I would expect 5-15 s,
  but that is not what I can measure tonight). Warm: the REPL's `import Mathlib` costs about one cold
  run (120-240 s) once; each lemma after it 0.1-1.5 s, median ~0.3 s. REPL resident memory after: 1-4 GB.

## P7. comparator in Docker (linux/arm64, Docker Desktop VM: kernel 6.12.76-linuxkit, 7.75 GiB)
- 2026-09-30 01:33:38 EDT prediction: the image (landrun from source + Debian) builds in 1-4 min and adds
  ~1 GB to Docker's disk (the Go builder image is most of it). Landlock: 70% it works in Docker
  Desktop's kernel with Docker's default seccomp profile; if not, it will need
  `--security-opt seccomp=unconfined`. The Linux toolchain on the bind mount: ~2.7 GB, <1 min. Reusing
  the macOS-built Mathlib .lake inside Linux (an APFS clone, no download): 60% Lake accepts it without
  rebuilding (I believe .olean files and Lake's traces do not depend on the OS; not sure).

- P7 partial result (logs/docker-build.log, logs/docker-setup.log): image built in 27.7 s, 291 MB.
  Landlock works under Docker Desktop's default seccomp profile: with comparator's own landrun flags
  (`--best-effort --ro / --rw /dev -ldd -add-exec --rwx <dir>`) a write inside the allowed directory
  succeeded and a write outside it got "Permission denied". (A first probe with `--ro /` and no
  `-add-exec` failed with "permission denied" on exec; that was my flags, not Landlock.) The Linux
  toolchain: 50.2 s, 3.0 GB under /work/home/.elan. **The macOS-built Mathlib .lake is accepted as is
  on Linux**: `lake build --no-build Mathlib` in the container said "All targets up-to-date (8923
  jobs)" in 63.2 s; both toolchains report commit 5045d0056413. So one trusted .lake (an APFS clone,
  no download) serves both.
- 2026-09-30 01:39:34 EDT prediction, comparator verdicts: positive project (proj-pos) passes for sqMod4,
  sumTwoSq and root; negative project (proj-neg: sqMod4 over ℕ, sumTwoSq with an extra `Odd a`) fails
  both with "Challenge and solution theorem statement do not match". Time per leaf: dominated by the two
  sandboxed `lake build`s (challenge, solution), each paying a Mathlib import: 3-10 min for the first
  leaf (it also builds Challenge), 2-6 min for each after; lean4export + kernel replay of the proof's
  closure: 5-60 s. Building comparator inside the container: <1 min.

- P7 result, part 2 (Mathlib under real landrun): **failed, for a reason I did not predict.** comparator
  in the container stopped at "Building Spec.SqMod4" with "[landrun:error] permission denied" for
  every leaf (logs/comparator-pos.log). Probing (commands in README) showed that under Landlock every
  read, write and exec of a file on Docker Desktop's bind mount is denied, even with an explicit
  `--rwx`/`--rox` rule for that directory; the same probes on the container's own filesystem behave
  as specified. The bind mount is a "fakeowner" filesystem (`mount`: `/run/host_mark/private on /work
  type fakeowner`), and Landlock's rules do not attach to its files. So comparator's sandbox needs the
  toolchain, the tools and the whole project, Mathlib included, on the container's own disk: ~3 GB +
  7.6 GB inside Docker's disk image. With 18-20 GB free on the host (swap files were growing with
  memory pressure) that would cross the 15 GB floor, so I did not do it. Instead: (i) comparator with
  real landrun in Docker on a core-Lean copy of the layout (mechanics/core/, no Mathlib), everything in a
  tmpfs; (ii) comparator on the Mathlib project natively on macOS with the repository's own
  fake-landrun shim (no sandbox), labelled as such.
- 2026-09-30 01:47:54 EDT prediction, (i) core layout in Docker with real landrun: first run downloads the
  582 MB toolchain tarball and builds comparator (~2 min); each later run ~15-30 s to unpack into tmpfs.
  Verdicts: positive passes for sqMod4 and sumTwoSq; negative (mod 3 instead of mod 4; an extra
  hypothesis) fails both with "theorem statement do not match". Per leaf < 10 s.

- P7 (i) result (logs/comparator-core-*.log): positive: sqMod4 pass in 14.6 s, sumTwoSq pass in 2.3 s,
  after 42.9 s of setup (582 MB toolchain download, comparator build, unpack into tmpfs); negative:
  both FAIL with "uncaught exception: Challenge and solution theorem statement do not match: 'sqMod4'"
  (and 'sumTwoSq') in 4.5 s and 3.9 s, after 15.3 s of setup (cached download, unpack only).
- 2026-09-30 01:50:03 EDT prediction, the sandbox itself: a correct proof whose file writes
  `Spec/SqMod4.lean` during its own build (core/negatives/SqMod4_writes.lean) fails under comparator's
  real landrun (the write is refused, so the `#eval` errors and the build fails); run natively with the
  fake-landrun shim, the write succeeds.

- P7 sandbox result (logs/comparator-core-writes*.log): under comparator's real landrun the build of
  the writing proof failed: "error: Proofs/SqMod4.lean:7:0: permission denied (error code: 13)",
  comparator FAIL in 2.6 s. Natively with the fake-landrun shim the first run printed "Your solution is
  okay!" (the challenge had been exported before the solution was built) **and the proof's build
  rewrote Spec/SqMod4.lean on disk**; the next run on the same directory failed on the changed stub. A
  subtler rewrite (a stub matching a weaker theorem) would have passed that next run. So the sandbox,
  not comparator's comparison, is what stops a proof that edits its own challenge.

## P8. leanchecker (kernel replay), default and --fresh
- 2026-09-30 01:57:15 EDT prediction: core layout (mechanics/core, imports only Init): default mode on
  Proofs.SqMod4 < 1 s; --fresh (replays all of Init as well) 20-90 s (the verifiers notes measured
  --fresh Init.Core at 54 s on this toolchain). Mathlib layout: default mode costs one Mathlib import
  (minutes on this machine); --fresh replays every constant Mathlib's closure holds, single-threaded:
  I guess 30-120 min and several GB of memory, which on this machine risks the swap growth that eats the
  disk, so I run it only under a guard that kills it if free disk falls under 17 GB.

- P6 result (logs/cold_warm-run1.log; 01:31-02:06 EDT, while another agent was building 8 Lean files
  at once, load average 5-11, swap 13.7-21.5 GB used): cold, 5 fresh `lake env lean Measure/Clean.lean`:
  398.6, 412.4, 326.0, 325.0, 256.1 s, **median 326.0 s**. Warm: the REPL's `import Mathlib` took
  346.8 s once; then the same lemma 5 times on that environment: 0.263, 0.011, 0.010, 0.011, 0.010 s,
  **median 0.011 s**. REPL resident memory after: 711 MB (the mapped Mathlib pages are mostly not
  resident under this pressure). The cold numbers are far above my range (120-240 s) and are this
  night's machine, not Lean: the core-Lean layout (no Mathlib) checks a leaf in 0.25-0.3 s cold on the
  same machine at the same time (logs/core-gate-*.log). The warm median is at the bottom of my range;
  since the same text was sent 5 times, a second run sends a differently named lemma each time, to rule
  out any caching by text.

- P8 core result (logs/leanchecker-core*.log): default mode on Proofs.SqMod4 2.2 s (most of it finding
  oleans on the search path), --fresh 39.8 s. Both rc 0.

## P9. gate.sh on the Mathlib layout (repo gate-demo, tag mathlib-trusted; leaves SqMod4 SumTwoSq Root)
- 2026-09-30 02:07:13 EDT prediction, positive (the proofs in mechanics/Proofs): every layer passes. Times
  on this machine, each layer dominated by Mathlib imports, leaves in parallel: (a) 30-70 s (the .lake
  clone); trusted build 10-30 s (up to date); (b) 6-12 min (SqMod4 and SumTwoSq in parallel, then Root);
  (c) 4-8 min; (d) 4-8 min; SafeVerify 8-20 min (it imports the target's and the submission's imports
  more than once per leaf); comparator (fake-landrun) 8-20 min (two lean4export runs per leaf, each
  importing Mathlib, then a kernel replay of the proof's closure). Total 40-80 min.
- Negative (negatives/SqMod4.lean over ℕ, negatives/SumTwoSq.lean with an extra `Odd a`; leaves SqMod4
  SumTwoSq): (a) pass, (b) pass (both files compile: they prove true statements), (c) FAIL with "Type
  mismatch" for both, (d) pass (leanchecker does not compare statements), SafeVerify FAIL ("theorem type
  mismatch"), comparator FAIL ("theorem statement do not match").

## P10. LeanParanoia (ported to v4.34.1) on the core layout
- 2026-09-30 02:07:25 EDT prediction: passes the real proof (success true), fails the sorry proof
  (Sorry/CustomAxioms), and passes the mod-3 proof, since it checks a proof without a reference
  statement. Each run < 5 s (core only).

- P10 result (logs/paranoia-*.log): with default options the ported LeanParanoia **rejected the correct
  proof**: its Replay check failed on a core declaration ("while replaying declaration
  '_private.Init.SimpLemmas.0.Lean.Arrow.eq_1': (kernel) declaration type mismatch"), and on the sorry
  proof it also flagged core's `lcProof` axiom and `Lean.Name.*._override` as unsafe. My reading of
  the cause, not verified: the port compiles, but LeanParanoia reads one .olean part per module
  (`readModuleData`), while Lean 4.34 splits modules that use the module system (Init does) into
  exported/server/private parts, which core's leanchecker reads together (`readModuleDataParts` in
  LeanChecker.lean). Either way it is a false failure, not a finding about the proof. With
  `--trust-modules Init,Std,Lean`: the real proof passes (1.8 s), the sorry proof fails with "Theorem 'sqMod4' contains sorry" (1.0 s), and the mod-3 proof
  passes (0.5 s), as predicted for a checker with no reference statement.

- P9 positive, first result (logs/gate-mathlib-pos.log; the snapshot run started 02:10): (a) pass 33.8 s;
  trusted build pass 14.5 s; (b) pass 398.8 s (Lean: SqMod4 and SumTwoSq 255 s each in parallel, Root
  136 s); (c) pass 172.5 s (`sqMod4: [propext, Classical.choice, Quot.sound]; sumTwoSq: [propext,
  Quot.sound]; root: [propext, Classical.choice, Quot.sound]`); (d) pass 173.1 s. Then my guard killed
  the run during SafeVerify: free disk fell from 16 GB to 14 GB within 5 s (swap 22.6 GB; macOS grows
  swap files in steps), below the 15 GB floor I was given. Three SafeVerify processes ran at once, and
  each imports Mathlib several times over (the target's and the submission's imports for its
  import-superset check, then again to replay each file). That was my mistake in how I ran it, not a
  finding about SafeVerify; I freed 0.9 GB (the Docker toolchain tarball and comparator binaries,
  both re-downloadable) and measured (e) one leaf at a time below, with the guard polling every 2 s.
- 2026-09-30 02:25:10 EDT prediction, SafeVerify alone on SqMod4 (Mathlib): 3-8 min (about four Mathlib
  environments in one process), peak memory 3-6 GB.

- Result: killed again by the guard after 76 s, with free disk at 16,003 MB (from 18,051 MB at 31 s;
  swap 21.7 -> 22.7 GB), before SafeVerify had printed anything past its header
  (logs/safeverify-mathlib-SqMod4.*). At that moment another agent's Lean process was using 10 cores
  and the load average was 12. One Mathlib-loading process of mine was enough to push the disk toward
  the floor, so I stopped starting them until the machine was quieter.

## P11. The same one-lemma check with a narrow import (Measure/Narrow.lean: Mathlib.Tactic.NormNum.Basic)
- 2026-09-30 02:29:00 EDT prediction: the lemma still elaborates (norm_num and ℤ come with that module);
  a cold `lake env lean Measure/Narrow.lean` takes 10-60 s on this loaded machine against the 326 s
  median for `import Mathlib`, because it loads a fraction of the .olean files. Same axioms line.

- P11 result (logs/narrow-import-*.log, 02:28-02:29 EDT, load average 7-12): rc 0 five times, 5.18, 1.69,
  5.75, 1.78, 1.70 s, **median 1.78 s**, peak RSS 1.2 GB. Inside my range's low end. The axioms line
  differs: `'clean' depends on axioms: [propext]` against `[propext, Classical.choice, Quot.sound]`
  with `import Mathlib`: the same tactic proof uses different lemmas when more of Mathlib is loaded.
- 2026-09-30 02:29:37 EDT prediction: one cold `lake env lean Measure/Clean.lean` (`import Mathlib`) right
  now, for a same-conditions comparison: 60-300 s.

- Result (logs/full-import-now.*): rc 0 in 146.6 s (load average 5-9), peak RSS 2.7 GB, axioms
  `[propext, Classical.choice, Quot.sound]`. So under the same conditions a narrow import checked the
  lemma about 80 times faster (1.78 s median against 146.6 s).

- 2026-09-30 02:32:16 EDT prediction, SafeVerify alone on SqMod4 (Mathlib), second try on a quieter machine
  (free disk 21 GB, load 5): pass, 2-6 min, peak memory 3-6 GB.

- Result: killed by the guard again after 139 s, free disk 15,793 MB (from 22,041 MB at 62 s; swap
  18.6 -> 22.8 GB in 60 s), SafeVerify still loading (logs/safeverify-mathlib-SqMod4-2.*). **SafeVerify
  on a Mathlib leaf needs more memory than this machine had free tonight**; I did not try it a third time.
  By its source (Main.lean) it builds four environments of the full import closure per run: two for
  its import-superset check and one for each file it replays.

- 2026-09-30 02:36:23 EDT prediction, gate.sh on the Mathlib layout, one leaf (SqMod4), GATE_JOBS=1,
  GATE_SAFEVERIFY=off, comparator local: (a) pass ~35 s, (b) pass 150-300 s, (c) pass 100-200 s, (d) pass
  100-200 s, comparator pass 200-500 s (two lean4export runs, each a Mathlib import, then a replay of
  the proof's closure). Total 10-20 min.

- Result (logs/gate-mathlib-pos-SqMod4.log, 02:36-02:45 EDT): gate: PASS (with a layer skipped).
  (a) 29.8 s; trusted build 13.7 s; (b) 153.4 s; (c) 9.3 s; (d) 37.2 s; SafeVerify skipped; comparator
  pass 299.9 s; total ~9 min. (c) and (d) were far below my range because they ran right after (b),
  while Mathlib's pages were still in memory: a Mathlib import costs seconds when its files are
  resident and minutes when they are not, which is most of the spread in tonight's numbers.
- 2026-09-30 02:45:56 EDT prediction, the negative (negatives/SqMod4.lean over ℕ, negatives/SumTwoSq.lean
  with an extra `Odd a`), same settings (GATE_JOBS=1, SafeVerify off): (a) pass, (b) pass, (c) FAIL
  "Type mismatch" for both, (d) pass, comparator FAIL "theorem statement do not match" for both;
  15-25 min.

- Result (logs/gate-mathlib-neg.log, logs/gate-mathlib-neg/; 02:46-03:06 EDT): (a) pass 32.4 s; trusted
  build 9.2 s; (b) pass 246.0 s; (c) **FAIL** 208.5 s, "Gate/SqMod4.lean:3:22: error: Type mismatch ...
  has type ∀ (n : ℕ), n ^ 2 % 4 = 0 ∨ n ^ 2 % 4 = 1 but is expected to have type S_sqMod4", and the
  same for sumTwoSq; (d) pass 219.0 s (as predicted: leanchecker does not compare statements);
  SafeVerify skipped; comparator reached its verdict on sqMod4, "uncaught exception: Challenge and
  solution theorem statement do not match: 'sqMod4'", and was still exporting sumTwoSq when my guard
  killed the run at 1210 s with free disk at 15.6 GB. Free disk then kept falling, to 11 GB, with swap
  at 29.9 GB, while three SafeVerify runs that were not mine (six processes counting their `lake env`
  wrappers; another agent's, on its own project, using my SafeVerify build) ran at once. The
  integrator stopped them at 03:09; free disk was back to 22 GB, swap 21 GB. Asked by the coordinator
  to, I then made gate.sh strictly sequential (one leaf and one `lake build` module at a time) and
  reran the four core cases with it: same verdicts (positive PASS; statements changed, sorry, and
  the proof that writes files FAIL at the same layers). Before that I had freed what I own (the two
  gate build directories, the REPL and LeanParanoia builds), told the orchestrator, and started nothing
  that loads Mathlib until the disk was back above the floor.

## P12. Warm checks with a new lemma name each time (is 0.011 s a cache of the same text?)
- 2026-09-30 03:09:22 EDT prediction: the REPL has no cache keyed by command text, so five differently
  named copies of the lemma take about what the identical ones did: first ~0.1-0.3 s, then ~0.01-0.05 s.
  With the narrow import (Mathlib.Tactic.NormNum.Basic) the REPL's import takes 1-10 s. Then the same
  with `import Mathlib` if the disk stays above 18 GB: import 60-350 s, then the same per-lemma times.

- Result, narrow import (logs/warm-narrow.log): the REPL's `import Mathlib.Tactic.NormNum.Basic` took
  5.20 s; five differently named lemmas (clean1..clean5) took 0.038, 0.008, 0.008, 0.009, 0.008 s,
  **median 0.008 s**, each with its own `#print axioms` line; REPL resident memory 1.9 GB after. So the
  0.011 s of the first run was not a cache of repeated text.
- Result, `import Mathlib` (logs/warm-mathlib.log): killed by my guard 85 s into the REPL's import:
  free disk fell from 23.3 GB to 18.2 GB in 25 s as swap grew. Not measured again; the first run's
  numbers (import 346.8 s, then 0.011 s median) stand, with the narrow run showing that distinct lemmas
  cost the same.

