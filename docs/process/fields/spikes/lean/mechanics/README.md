# Lean mechanics and the gate: the spike

Run 2026-09-30, 00:59–03:15 EDT (the install before it, 00:46–00:52), on Alex's MacBook, no model or
prover of any kind. This directory is a Lake project in the layout under test (option 4 of the fields directive); `../gate/` holds the gate
built on it. Every measurement had a prediction written first: [`PREDICTIONS.md`](PREDICTIONS.md),
prediction and result side by side. Every command's output is in [`logs/`](logs/) (one file per
command, written by [`run.sh`](run.sh): time, load average, swap, the command, its output, exit code,
wall seconds, peak memory).

**Read the timings with this in mind.** The machine was short of memory for the whole run: swap grew
from 13.7 GB to 29.9 GB used, Docker Desktop's VM (8 GB) and a browser were resident, and other
agents were building Lean at the same time (up to 8 `lean` processes at once, load average 3–15 on
11 cores). A Lean process that imports Mathlib ran at ~12% CPU while it loaded, so the minutes below
are paging, not computation. The same Lean on the same machine at the same moment checks a leaf that
imports only core Lean in 0.25–0.3 s. The numbers are what this machine did tonight; they are an upper
bound, not what Lean costs on an idle machine, and I have not measured an idle machine.

## Versions

| What | Version / revision |
|---|---|
| macOS | 26.5.2 (25F84), Apple silicon, 11 cores, 18 GiB |
| elan | 4.2.4 (227caca13 2026-08-25) |
| Lean | 4.34.1, commit 5045d0056413266e57c625dcd7c365b10e377c52 (macOS arm64 and Linux aarch64 builds report the same commit) |
| Lake | 5.0.0-src+5045d00 |
| Mathlib | tag v4.34.1 = d13f23b723b8a846827a245b89c10fc7d3f11612 (plausible 118aa17e, LeanSearchClient ddf04cf3, importGraph e928b725, proofwidgets 106ff4fa, aesop 355695d5, Qq 6a489d9a, batteries f2effa3d, Cli e92c9f15; `lake-manifest.json`) |
| leanchecker | ships with the toolchain (`bin/leanchecker`); lean4checker's repository is archived and says so |
| REPL | leanprover-community/repl tag v4.34.0 = 193cf4bb9a22bb3fc6d25774f0fe6a70db1fd6ee, toolchain set to v4.34.1 (no v4.34.1 tag exists) |
| comparator | leanprover/comparator tag v4.34.0 = d03acab154d269c06e60e4de7e4cc85deebff94b, toolchain set to v4.34.1; lean4export 076e8e57707e813375e8f9da8bf989799ace9680 (comparator's manifest) |
| SafeVerify | GasStationManager/SafeVerify main = b291b588a53999a7e837dda61c7dbfe8c550c814 (2026-04-22), pinned v4.27.0; set to v4.34.1, its unused Mathlib requirement dropped, Cli v4.34.0, and a four-line source port (below) |
| LeanParanoia | oOo0oOo/LeanParanoia main = 11c2385ade3cc417d69ce837bfda9d2c5b1d61ab (2025-11-27), pinned v4.25.0; set to v4.34.1 with a two-line port (below) |
| landrun | Zouuup/landrun 811cfff51ceaf3d9843708aa6d22e9b84ccac8b4 (v0.1.18), built with Go 1.24 in `golang:1.24-bookworm` |
| Docker | Docker Desktop, engine 29.6.1, VM kernel 6.12.76-linuxkit aarch64, 11 CPUs, 7.75 GiB; image `graphene-comparator:v4.34.1` (Debian bookworm-slim, 291 MB) |

## Results

| # | Measurement | Result | Log |
|---|---|---|---|
| 1 | Install (earlier tonight, not rerun) | toolchain 17 s, 2.7 GB; `lake update` with the Mathlib cache 81 s, 8,908 files, `.lake/packages` 7.6 GB, `~/.cache/mathlib` 448 MB; first `lake build` of a one-file project 260 s, the next 4.8 s | `install/` (copied from the scratchpad; see Install) |
| 2 | Clone of that `.lake` (144,200 files) with APFS copy-on-write | 28.0 s, 82 MB of disk | PREDICTIONS P1 |
| 3 | `lake build` of a one-lemma file importing Mathlib | 193.5 s clean, 183.7 s with `sorry`; rc 0 both | `build-clean.log`, `build-sorry.log` |
| 4 | The `sorry` warning | `warning: Measure/Sorry.lean:3:8: declaration uses \`sorry\`` | `build-sorry.log` |
| 5 | `lake build --wfail` on the built sorry module | rc 1, 5.6 s: "Some required targets logged failures: - Measure.Sorry / error: build failed" (Lake fails on a *replayed* warning too); on the clean module rc 0, 3.8 s | `wfail-*.log` |
| 6 | `#print axioms` | clean `[propext, Classical.choice, Quot.sound]`; sorry `[sorryAx]`; native_decide `[propext, withNative._native.native_decide.ax_1_1]`; declared axiom `[cheat]` | `build-*.log` |
| 7 | One-lemma check, cold: 5 fresh `lake env lean` | 398.6, 412.4, 326.0, 325.0, 256.1 s; **median 326.0 s** | `cold_warm-run1.log` |
| 8 | Same lemma, warm: one REPL, `import Mathlib` once | import 346.8 s once; then 0.263, 0.011, 0.010, 0.011, 0.010 s; **median 0.011 s**; REPL RSS 711 MB after | `cold_warm-run1.log` |
| 8a | Warm again, five *differently named* copies (to rule out a cache of repeated text), REPL importing `Mathlib.Tactic.NormNum.Basic` | import 5.20 s; then 0.038, 0.008, 0.008, 0.009, 0.008 s, **median 0.008 s**; RSS 1.9 GB. The same with `import Mathlib` was stopped by my disk guard 85 s into the import | `warm-narrow.log`, `warm-mathlib.log` |
| 8b | The same lemma, cold, importing only `Mathlib.Tactic.NormNum.Basic` | 5.18, 1.69, 5.75, 1.78, 1.70 s; **median 1.78 s**, peak RSS 1.2 GB; `import Mathlib` a minute later: 146.6 s, 2.7 GB | `narrow-import-*.log`, `full-import-now.log` |
| 9 | The same layout without Mathlib (`core/`) | whole `lake build` 2.6 s; one leaf's `Gate` check 0.25–0.28 s cold | `core-*.log` |
| 10 | leanchecker on `core/` Proofs.SqMod4 | default 2.2 s; `--fresh` (replays all of Init too) 39.8 s | `leanchecker-core*.log` |
| 11 | Tools built for v4.34.1 | REPL 12.4 s, comparator + lean4export 10.7 s, SafeVerify 13.0 s (after the port), LeanParanoia 12.2 s (after the port) | `install-*.log` |
| 12 | comparator, real landrun in Docker, `core/` layout | positive: sqMod4 pass 14.6 s, sumTwoSq pass 2.3 s; negative (mod 3; extra hypothesis): both FAIL "Challenge and solution theorem statement do not match" in 4.5 s and 3.9 s; container setup 15.3 s (43 s the first time, with the 582 MB toolchain download and the comparator build) | `comparator-core-*.log` |
| 13 | comparator on a proof that writes its own challenge while it compiles | real landrun: FAIL, "error: Proofs/SqMod4.lean:7:0: permission denied (error code: 13)"; fake-landrun (no sandbox): "Your solution is okay!" and `Spec/SqMod4.lean` rewritten on disk; the next run fails on the rewritten stub | `comparator-core-writes*.log` |
| 14 | LeanParanoia on `core/` | default options: rejects the correct proof (false failure in its replay of Init); with `--trust-modules Init,Std,Lean`: correct proof passes 1.8 s, sorry fails 1.0 s ("Theorem 'sqMod4' contains sorry"), mod-3 proof passes 0.5 s (no reference statement) | `paranoia-*.log` |
| 15 | gate.sh on `core/` | positive PASS, every layer ≤ 3.1 s; statements changed, sorry, `Challenge.lean` edited, and a proof that writes files: each FAIL at the layer expected | `../gate/README.md` |
| 16 | gate.sh on the Mathlib layout | three leaves: (a)–(d) pass in 13 min, then stopped at the disk floor during SafeVerify; one leaf, SafeVerify off: PASS in ~9 min (comparator 299.9 s); negative: see below | `gate-mathlib-*.log`, `gate-mathlib-*/` |

### Install (not rerun; `install/install.sh`, its logs and the predictions written before it, copied here)

`install/install.sh` ran, with times from its log: download `elan-init.sh` 0.3 s; `sh elan-init.sh -y
--default-toolchain none --no-modify-path` 1.2 s; `elan toolchain install leanprover/lean4:v4.34.1`
16.9 s, `~/.elan/toolchains` 2.7 GB; in a project with `rev = "v4.34.1"` for Mathlib, `lake update`
80.9 s (clones Mathlib and 8 dependencies, then its post-update hook downloads and unpacks 8,908 cache
files), `.lake/packages` 7.6 GB, `~/.cache/mathlib` 448 MB; `lake exe cache get` again 6.7 s ("No files
to download"); first `lake build` 259.9 s (`Built Spike.Basic (148s)`, `Built Spike (106s)`); second
4.8 s (`Replayed`). The predictions written before it (`install/predictions-install.md`) had
the toolchain at 0.8–1.6 GB and 1–3 min (it was 2.7 GB in 17 s), the cache at 4–7 GB in 2–6 min (7.6 GB
in 81 s) and the first build at 10–40 s (260 s).

## Findings

1. **`native_decide` no longer shows `Lean.ofReduceBool` in Lean 4.34.1.** `#print axioms` reports an
   auxiliary axiom named after the theorem, `withNative._native.native_decide.ax_1_1`. A gate that
   rejects a deny-list of axiom names would pass it; an allow-list of exactly `propext`,
   `Classical.choice`, `Quot.sound` rejects it. gate.sh uses the allow-list.
2. **`#print axioms` trusts the imported .olean.** Reading `src/lean/Lean/Util/CollectAxioms.lean` in
   the v4.34.1 toolchain: for an imported constant, `collectAxioms` returns the axiom list that the
   imported module's .olean recorded about itself when it was written ("axiom collection never crosses
   module boundaries"). So a Gate file's `#print axioms <leaf>` reports what the leaf's own .olean
   says. This is from reading the source, not from an attack I ran. It is one more reason layer (c) is
   the fast check and not the last word: SafeVerify walks the replayed proof itself, and comparator
   walks the exported proof.
3. **Every Mathlib import is paid again, and it dominates everything.** Each module that imports
   Mathlib, each `lake env lean`, each leanchecker, SafeVerify and lean4export run loads Mathlib's
   ~5 GB of .olean files. Tonight that was 2.5–7 minutes each, whatever the file did; without Mathlib
   the same checks take a fraction of a second. A warm REPL paid it once (347 s) and then checked the
   lemma in 0.011 s median. And the same lemma with `import Mathlib.Tactic.NormNum.Basic` instead of
   `import Mathlib` checked cold in 1.78 s median (5 runs), against 146.6 s for `import Mathlib` a
   minute later on the same machine (`narrow-import-*.log`, `full-import-now.log`). Two consequences:
   the check inside an agent's loop has to be warm (a REPL or a Lean server kept running), and the
   challenge should import only the Mathlib modules its statements and definitions need, which makes
   every cold layer of the gate about 80 times cheaper here. One caution: the axioms of the same tactic
   proof changed with the import (`[propext]` with the narrow import; `[propext, Classical.choice,
   Quot.sound]` with all of Mathlib), because tactics find different lemmas; both are allowed.
4. **The macOS-built Mathlib `.lake` works on Linux unchanged.** In the linux/arm64 container,
   `lake build --no-build Mathlib` on an APFS clone of the macOS `.lake` said "All targets up-to-date
   (8923 jobs)" (63.2 s). Both toolchains report commit 5045d0056413. One trusted `.lake` can serve
   both platforms, with no second 7.6 GB download.
5. **comparator's sandbox cannot see Docker Desktop's bind mounts.** Under landrun (Landlock), every
   read, write and exec of a file on the bind-mounted host directory was denied, even with an explicit
   `--ro`/`--rwx`/`--rox` rule for it (`/work` is a `fakeowner` filesystem: `mount` shows
   `/run/host_mark/private on /work type fakeowner`); the same probes on the container's own filesystem
   behaved as specified, including a write outside the allowed directory refused with "Permission
   denied". The first comparator run on the Mathlib project therefore stopped with "[landrun:error]
   permission denied" for every leaf (`comparator-pos.log`). The fix is to put the toolchain (3 GB) and
   the project with its `.lake` (7.6 GB) on the container's own disk. With 18–20 GB free on the host,
   and swap files growing, that would have crossed the 15 GB floor I was given, so I did not; comparator
   with real landrun ran on the core-Lean copy of the layout, entirely in a tmpfs, and on the Mathlib
   project it ran natively with the fake-landrun shim. Docker's default seccomp profile does allow
   Landlock (a first probe that failed was my flags: `--ro /` without `-add-exec` cannot exec).
6. **Without a sandbox, a proof can rewrite the challenge the checker reads.** A correct proof whose
   file runs `#eval IO.FS.writeFile "Spec/SqMod4.lean" ...` passed comparator with the fake shim (the
   challenge had already been exported) and left the stub rewritten on disk, so the next check read a
   different challenge. Under real landrun its build failed with "permission denied". The same holds
   for gate.sh's own layers: anything that loads candidate code can edit the Gate files, Spec .oleans
   or logs the next layer reads, unless it is sandboxed. gate.sh therefore runs layers (b)–(e) under
   macOS `sandbox-exec` (no network; writes only to the proof modules' outputs and a private tmp),
   and the same proof then fails at (b) with "operation not permitted". A Graphene check that is just
   `lake build && …` would not have stopped this.
7. **SafeVerify and LeanParanoia need ports; LeanParanoia's is not enough.** SafeVerify failed to build
   on v4.34.1 with `Unknown identifier CollectAxioms.collect` (now private); switching to the public
   `Lean.collectAxioms` (four lines, in `../gate/install-tools.sh`) builds and behaves correctly on
   every case here. It inherits finding 2 for imported constants only. LeanParanoia built after
   swapping the archived lean4checker's `Replay` for core's `Lean.Replay`, but its replay then
   rejected a correct proof on a core declaration (my unverified reading: it reads one .olean part per
   module, while Lean 4.34 splits Init's modules into parts that core's leanchecker reads together);
   it works only with `--trust-modules Init,Std,Lean`, and it has no reference statement, so it
   passed the changed statement. I would not put it in the gate.
8. **`--wfail` fails on replayed warnings.** `lake build --wfail` fails a module whose `sorry` warning
   was recorded in an earlier build, so it is a cheap sorry check; it also fails on any linter warning,
   so gate.sh relies on the axiom allow-list for `sorry` and counts the warnings only.
9. **leanchecker is a replay, not a judge.** It passed every negative here (changed statement, `sorry`),
   as its own source says ("not an external verifier, simply a tool to detect environment hacking").
   Its place is under comparator and SafeVerify, not instead of them.

## The gate on the Mathlib layout

A scratch repository (`$S/gate-demo`) holds this project's `Challenge.lean`, `Spec/`, `Gate/`, lakefile,
manifest and toolchain with `sorry` stubs in `Proofs/`, committed and tagged `mathlib-trusted`; its
trusted `.lake` is a clone of this project's, confirmed current for that commit by `lake build
--no-build Challenge Spec.*` ("All targets up-to-date (8928 jobs)", 12.6 s). The candidate is the
working tree with `Proofs/` replaced by this directory's proofs.

Positive, leaves `SqMod4 SumTwoSq Root`, all leaves at once (`gate-mathlib-pos.log`, 02:10 EDT):

```
(a) trusted inputs   pass     33.8s  10 files from mathlib-trusted; none differed; .lake cloned
    trusted build    pass     14.5s  Challenge, Spec.* (reused from the trusted .lake when unchanged)
(b) lake build       pass    398.8s  Proofs.SqMod4 Proofs.SumTwoSq Proofs.Root (sandboxed; sorry warnings: 0)
(c) type + axioms    pass    172.5s  sqMod4: [propext, Classical.choice, Quot.sound]; sumTwoSq: [propext, Quot.sound]; root: [propext, Classical.choice, Quot.sound];
(d) kernel replay    pass    173.1s  leanchecker Proofs.SqMod4 Proofs.SumTwoSq Proofs.Root
```

Lean's own times inside (b): SqMod4 and SumTwoSq 255 s each (in parallel), then Root 136 s. The run
did not reach its end: during SafeVerify (three processes at once, each loading Mathlib several times)
free disk fell from 16 GB to 14 GB within five seconds as macOS grew its swap, and my guard killed it.
A second try, SafeVerify alone on one leaf, was killed the same way after 76 s with free disk at
16.0 GB, while another agent's Lean process held 10 cores. After that I made gate.sh check one leaf
at a time (a `GATE_JOBS` setting, since removed: gate.sh is now sequential throughout) and waited
for a quieter machine before starting anything that loads Mathlib.

Positive, one leaf, SafeVerify off (`GATE_JOBS=1` was then a setting; one at a time is now the only mode;
`gate-mathlib-pos-SqMod4.log`, 02:36 EDT, load average 4–8):

```
$ GATE_JOBS=1 GATE_SAFEVERIFY=off GATE_ALLOW_SKIP=1 GATE_TRUSTED_REF=mathlib-trusted \
  GATE_TRUSTED_LAKE=$S/gate-trusted-mathlib/mathlib/.lake GATE_TOOLS=$S/tools gate.sh mathlib SqMod4
(a) trusted inputs   pass     29.8s  10 files from mathlib-trusted; none differed; .lake cloned
    trusted build    pass     13.7s  Challenge, Spec.* (reused from the trusted .lake when unchanged)
(b) lake build       pass    153.4s  Proofs.SqMod4 (sandboxed; sorry warnings: 0)
(c) type + axioms    pass      9.3s  sqMod4: [propext, Classical.choice, Quot.sound];
(d) kernel replay    pass     37.2s  leanchecker Proofs.SqMod4
(e) SafeVerify       skip      0.1s  GATE_SAFEVERIFY=off
(e) comparator       pass    299.9s  no landrun (fake-landrun shim; sandboxed by this script)
gate: PASS (with a layer skipped)
```

(c) and (d) ran right after (b), with Mathlib's files still in memory: an import costs seconds when
they are resident and minutes when they are not, which is most of the spread in tonight's numbers.

Negative, `negatives/SqMod4.lean` (over ℕ) and `negatives/SumTwoSq.lean` (an extra `Odd a`), same
settings (`gate-mathlib-neg.log`, 02:46 EDT):

```
(a) trusted inputs   pass     32.4s  10 files from mathlib-trusted; none differed; .lake cloned
    trusted build    pass      9.2s  Challenge, Spec.* (reused from the trusted .lake when unchanged)
(b) lake build       pass    246.0s  Proofs.SqMod4 Proofs.SumTwoSq (sandboxed; sorry warnings: 0)
(c) type + axioms    FAIL    208.5s  sqMod4: type: Gate/SqMod4.lean:3:22: error: Type mismatch; sumTwoSq: type: Gate/SumTwoSq.lean:3:35: error: Type mismatch;
(d) kernel replay    pass    219.0s  leanchecker Proofs.SqMod4 Proofs.SumTwoSq
(e) SafeVerify       skip      0.0s  GATE_SAFEVERIFY=off
```

Lean's message in `gate-mathlib-neg/gate.SqMod4` is the one a person reads: "sqMod4 has type ∀ (n :
ℕ), n ^ 2 % 4 = 0 ∨ n ^ 2 % 4 = 1 but is expected to have type S_sqMod4". comparator rejected sqMod4
("Challenge and solution theorem statement do not match: 'sqMod4'",
`gate-mathlib-neg/comparator.SqMod4`) and was still exporting sumTwoSq when my guard stopped the run at
free disk 15.6 GB; the disk then fell to 11 GB while another agent ran three SafeVerify runs at once
(see "The memory incident" below). So on the Mathlib layout tonight: the negative was caught by (c)
and by comparator, leanchecker passed it as designed, and SafeVerify did not run.

## The memory incident

This machine has 18 GiB of RAM, and macOS keeps its swap files on the same disk as everything else,
so every gigabyte of new swap is a gigabyte less free disk. I was told to keep free disk above 15 GB,
and from 02:10 I ran every Mathlib job under `guard.sh`, which kills it below 16 GB (polling every 5 s,
then every 2 s). What happened, from the guard lines in the logs and `df`/`vm.swapusage` readings:

| Time (EDT) | What was running | Free disk | Swap used | Outcome |
|---|---|---|---|---|
| 00:59–01:03 | before this spike's first build | 38.9 GB | 13.9 GB | — |
| 01:44 | after Docker's Linux toolchain (3.0 GB, later deleted) and other agents' builds | 18–20 GB | 20.3 GB | — |
| 02:10–02:24 | gate.sh, three leaves: (b)–(d) each ran the leaves' Lean processes side by side (guard saw up to 4.1 GB resident for mine) | 18 → 16 GB | 19.8 → 22.6 GB | (a)–(d) passed; then three SafeVerify runs at once: free disk 16 → 14 GB within 5 s; killed at 884 s |
| 02:25 | SafeVerify alone, one leaf; another agent's Lean on 10 cores, load 12 | 18,051 → 16,003 MB in 45 s | 21.7 → 22.7 GB | killed at 76 s, before SafeVerify printed past its header |
| 02:32 | SafeVerify alone, one leaf, load 5–8 | 22,041 → 15,793 MB in 77 s | 18.6 → 22.8 GB in 61 s | killed at 139 s, same point |
| 02:36–02:45 | gate.sh, one leaf, SafeVerify off | ≥ 17.8 GB | 20.8–22.0 GB | PASS in ~9 min |
| 02:46–03:06 | gate.sh, two negatives, SafeVerify off; from ~03:00 another agent ran three SafeVerify runs at once on its own project with my SafeVerify build | 19.7 → 15.6 GB, then 11 GB after my kill | 20.6 → 29.9 GB (swap total 30.7 GB) | mine killed at 1210 s; I freed my build directories and told the orchestrator; the integrator stopped the other runs at 03:09 |
| 03:09–03:11 | the REPL importing `Mathlib` for row 8a, alone (guard line 18 GB) | 23,291 → 18,170 MB in 25 s | 20.6 GB at 60 s | killed at 85 s; up to 4.6 GB resident |
| 03:13 | nothing of mine running | 22 GB | 21 GB | — |

What I take from it. Each process that loads Mathlib held 1.2–2.7 GB resident here (peak RSS from
`time -l`); SafeVerify, which by its `Main.lean` builds four environments of the full import closure
per run, is the heaviest single step I ran, and one SafeVerify run on one Mathlib leaf grew swap by
about 4 GB within a minute on a machine that already had Docker's 8 GB VM, a browser and other agents
resident. Three of anything that loads Mathlib at once, on this machine tonight, was enough to take the
disk under the floor, and even a single process (SafeVerify at 02:32, the REPL's import at 03:10) could
eat 5–6 GB of free disk in under a minute. So gate.sh now runs strictly one leaf, and one module build,
at a time; SafeVerify with `import Mathlib` stays unmeasured here; and a machine that runs this gate
with Mathlib needs either more memory than this one had free tonight or narrow imports (row 8b). My own mistakes in it: the first three-leaf run
fanned out every layer, which I had chosen for speed without measuring memory; and my guard polled
every 5 s, which let the disk fall 2 GB past its line before it acted.

## What did not work, and what I tried

- comparator with real landrun on the Mathlib project: blocked by finding 5; the disk it needs is
  ~11 GB inside Docker's disk image. Tried: explicit Landlock rules for the bind mount (denied), the
  default and unconfined seccomp profiles (Landlock itself works in both; the bind mount is the
  problem). Not tried: Docker volumes (they would hold the same 11 GB), a Linux machine.
- leanchecker `--fresh` on the Mathlib layout: not run. It holds the loaded closure and a second,
  fresh kernel environment with every constant of it, roughly twice the memory of one import, on a
  night when single imports were already pushing the disk to its floor. On core Lean alone it took
  39.8 s.
- SafeVerify on a Mathlib leaf: killed twice by my guard at the 16 GB disk line (swap grew 4 GB in a
  minute), once with three leaves at once and once with one leaf alone on a quieter machine. By its
  Main.lean it builds four environments of the import closure per run. Not measured tonight; the
  narrow-import measurement (row 8b) suggests how to make it fit.
- Kimina Lean Server and AXLE: skipped. AXLE is a hosted service with API keys (its paper, arXiv
  2606.26442, §4: "Authentication is by API key. No local Lean 4 installation is required"), which the
  rules forbid. Kimina Lean Server is a pool of the same leanprover-community REPL measured in row 8,
  behind a REST API; its default image pins Lean v4.26.0 (scratchpad notes, verifiers.md A6), so it would
  need its own Mathlib build for v4.34.1, and it would measure the REPL again. AXLE's paper reports
  Kimina at 0.75 s median latency against 5.14 s for a fresh Lean per request (Table 2, 8 vCPU), and
  SafeVerify at 10.1 s and comparator at 95.7 s median per request (Table 3, 16 vCPU).
- A mistake of mine, recorded: I edited `gate.sh` while a Mathlib gate run was executing it; bash
  reads a script as it goes, so I killed that run (`gate-mathlib-pos-killed.log`) and reran it from a
  snapshot copy.

## Rerun

Everything below assumes `S=<scratchpad>` with the base project at `$S/lean/base` (made by running
`install/install.sh` in `$S/lean`) and `export PATH=$HOME/.elan/bin:$PATH`. `run.sh NAME CMD...` only
logs; drop it to see output directly.

```sh
M=docs/process/fields/spikes/lean/mechanics; G=docs/process/fields/spikes/lean/gate
# this project: config files from the base project, then its .lake as an APFS clone (28 s, ~0 disk)
cp $S/lean/base/lake-manifest.json $M/   # then set its "name" to "mechanics"
cp -cR $S/lean/base/.lake $M/.lake
cd $M
./run.sh build-clean lake build Measure.Clean        # also Measure.Sorry, Measure.Native, Measure.Axiom
./run.sh wfail-sorry-replayed lake build --wfail Measure.Sorry
./run.sh build-layout lake build                     # Challenge, Spec.*, Proofs.*
lake env lean Gate/SqMod4.lean                       # the Gate check by hand
# tools (REPL, comparator + lean4export, SafeVerify, LeanParanoia), ~50 s together
TOOLS_DIR=$S/tools ../gate/install-tools.sh repl comparator safeverify paranoia
# cold against warm
python3 cold_warm.py $S/tools/repl/.lake/build/bin/repl 5 > logs/cold_warm.log   # 5 cold + 5 warm
python3 cold_warm.py $S/tools/repl/.lake/build/bin/repl 5 0 Mathlib.Tactic.NormNum.Basic  # warm only
# core-Lean copy of the layout
(cd core && lake build && lake env lean Gate/SqMod4.lean && lake env leanchecker --fresh Proofs.SqMod4)
# comparator with real landrun in Docker (core layout; the negatives are core/negatives/*.lean)
docker build --platform linux/arm64 -t graphene-comparator:v4.34.1 ../gate/docker
DOCKER_WORK=$S/docker ../gate/docker/comparator.sh core SqMod4 SumTwoSq
# comparator natively, no sandbox, in a built project directory
T=$S/tools/comparator
COMPARATOR_LANDRUN=$T/scripts/fake-landrun.sh \
COMPARATOR_LEAN4EXPORT=$T/.lake/packages/lean4export/.lake/build/bin/lean4export \
  lake env $T/.lake/build/bin/comparator cfg.json   # cfg.json: see ../gate/gate.sh
# SafeVerify and LeanParanoia by hand, in a built project directory
lake env $S/tools/SafeVerify/.lake/build/bin/safe_verify \
  .lake/build/lib/lean/Spec/SqMod4.olean .lake/build/lib/lean/Proofs/SqMod4.olean
lake env $S/tools/LeanParanoia/.lake/build/bin/paranoia --trust-modules Init,Std,Lean Proofs.SqMod4.sqMod4
```

The gate runs (a scratch repository with the tree committed and tagged as the trusted commit):

```sh
D=$S/gate-demo; git -C $D init
# copy lakefile.toml (without the Measure lib), lean-toolchain, lake-manifest.json, Challenge.lean,
# Spec/, Gate/ into $D/mathlib, Proofs/*.lean as `sorry` stubs; commit; git tag mathlib-trusted
git -C $D worktree add $S/gate-trusted-mathlib mathlib-trusted
cp -cR $M/.lake $S/gate-trusted-mathlib/mathlib/.lake      # then remove its Proofs/Measure/Gate outputs
(cd $S/gate-trusted-mathlib/mathlib && lake build Challenge Spec)   # "All targets up-to-date"
cp $M/Proofs/*.lean $D/mathlib/Proofs/                     # the candidate
cd $D && GATE_TRUSTED_REF=mathlib-trusted GATE_TRUSTED_LAKE=$S/gate-trusted-mathlib/mathlib/.lake \
  GATE_TOOLS=$S/tools $M/guard.sh 16 9000 $G/gate.sh mathlib SqMod4 SumTwoSq Root
```

`guard.sh MIN_FREE_GB MAX_SECONDS CMD` kills the command if free disk falls under the limit or it runs
too long (macOS has no GNU `timeout`; this polls every 2 s). The core runs use `core-trusted` and
`$S/gate-trusted-core/core/.lake` the same way.

## Files

- `Challenge.lean`, `Spec/`, `Proofs/`, `Gate/`: the layout, a three-node tree (`root` needs
  `sumTwoSq`, which needs `sqMod4`: squares are 0 or 1 mod 4, so a sum of two squares is never 3 mod
  4, so no n ≡ 3 mod 4 is a sum of two squares).
- `negatives/`: drop-in `Proofs/` files whose statements differ (ℕ for ℤ; an extra `Odd a`).
- `core/`: the same layout with no Mathlib (and its `negatives/`, including the proof that writes its
  own challenge).
- `Measure/`: the files for rows 3–6 and 8b (`Narrow.lean`).
- `install/`: the install script, its two logs and the predictions written before it (row 1).
- `cold_warm.py`, `run.sh`, `guard.sh`, `PREDICTIONS.md`, `logs/` (the gate runs' per-layer logs are
  in `logs/gate-mathlib-*/`).
