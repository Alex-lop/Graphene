# What each layer of the gate costs, and where it should run

Measured 2026-09-30 on Alex's MacBook (Apple silicon, 11 cores, 18 GiB), Lean 4.34.1, Mathlib v4.34.1.
**The machine was short of memory all night** (swap 13.7 → 29.9 GB used, Docker's 8 GB VM resident,
other agents building Lean beside these runs, load average 3–15), so every number that involves
loading Mathlib is an upper bound for this hardware, not what Lean costs on an idle machine. The
core-Lean column is the same layout with no Mathlib, measured at the same time, and shows how much of
each cost is the Mathlib import. Logs: `../mechanics/logs/`.

**This machine (18 GiB of RAM) cannot run these layers in parallel with `import Mathlib`.** Three
Mathlib-loading checks at once took free disk under the 15 GB floor twice tonight (macOS swap lives on
the same disk, and grew to 29.9 GB), and even one SafeVerify run on one leaf grew swap by about 4 GB
in a minute (`../mechanics/README.md`, "The memory incident"). gate.sh therefore checks one leaf at
a time in every layer, and builds one module per `lake build`. The per-layer times below for
"three leaves" come from the one run that did fan out, before that change.

## Per layer

| Layer | What it catches (tonight's evidence) | Mathlib layout, this machine | Core layout | Memory |
|---|---|---|---|---|
| (a) trusted inputs: read-only files by `git show <trusted ref>:path`, trusted `.lake` cloned | an edited `Challenge.lean`, `Spec/`, `Gate/`, lakefile, manifest or toolchain (it fails and uses the trusted copy) | 29.8–33.8 s (the APFS clone of 144,200 files is nearly all of it; 28 s on its own) | 0.2–0.5 s | — |
| trusted build: `lake build Challenge Spec.*` | nothing; it proves the trusted `.lake` is current before candidate code runs | 13.7–14.5 s (up-to-date check of 8,928 jobs); ~3 min per module if the challenge changed | 0.2–0.3 s | — |
| (b) `lake build Proofs.<leaf>` under `sandbox-exec` | proofs that do not compile; a proof that writes files while it compiles | one leaf 153.4 s; three leaves 398.8 s (Lean: 255 s per leaf, two at once, then Root 136 s) | 0.4–4.6 s | 1.7–2.2 GB peak per Lean process (`time -l`) |
| (c) `Gate/<leaf>.lean`: `example : <approved type> := <leaf>` and `#print axioms` | a changed statement (Type mismatch); `sorry` (`sorryAx`); a declared axiom; `native_decide` (`<thm>._native.native_decide.ax_1_1`) | one leaf 9.3 s right after (b), with Mathlib's pages still in memory; three leaves at once 172.5 s | 0.3–0.6 s | as (b) |
| (d) `leanchecker Proofs.<leaf>` | environment hacking (per the verifiers notes; not attacked here); it passed a changed statement and a `sorry`, as designed | one leaf 37.2 s; three leaves at once 173.1 s; `--fresh`: not run (below) | 0.8–2.2 s; `--fresh` 39.8 s | as (b) |
| (e) SafeVerify, `Spec/<leaf>.olean` against `Proofs/<leaf>.olean` | a changed statement ("theorem type mismatch"), `sorry` ("uses disallowed axioms") | not measured: killed twice by my disk guard at 16 GB free (swap +4.2 GB in 60 s). By its source it builds four environments of the full import closure per run (two for its import-superset check, one per file it replays) | 1.9–3.9 s | the most of any layer |
| (e) comparator, fake-landrun, inside `sandbox-exec` | a changed statement ("theorem statement do not match") | one leaf 299.9 s: two `lake build`s that find everything built, two lean4export runs (each loads Mathlib), then the kernel replay of the proof's closure | 2.9–3.6 s | as (b) |
| (e) comparator, real landrun in Docker | the same, plus a proof that writes its challenge while it compiles ("permission denied") | not run: needs ~11 GB on Docker's disk (see `../mechanics/README.md`, finding 5) | 2.3–14.6 s per leaf + 15–43 s container setup | tmpfs of ~4 GB in the VM |
| warm REPL (not a gate layer) | nothing it can be trusted for; feedback only | `import Mathlib` 346.8 s once, then **0.011 s** median per lemma; with `Mathlib.Tactic.NormNum.Basic`: import 5.2 s, then 0.008 s median over five differently named lemmas | — | 711 MB resident after (full); 1.9 GB (narrow) |
| cold `lake env lean` of one lemma (reference) | — | **326.0 s** median of 5 (01:31–02:00); 146.6 s once at 02:30 | 0.25–0.28 s | 1.7–2.7 GB |
| the same lemma importing only `Mathlib.Tactic.NormNum.Basic` | — | **1.78 s** median of 5 (02:28) | — | 1.2 GB |

For scale on a server without memory pressure (not measured here): AXLE's paper reports a fresh Lean per
request at 5.14 s median against 0.75 s for a warm REPL pool (Kimina Lean Server), 8 vCPU, and
SafeVerify at 10.1 s and comparator at 95.7 s median per request, 16 vCPU (arXiv 2606.26442, Tables 2
and 3, read 2026-09-30).

## Where each layer should run

**Inside an agent's loop: a warm Lean, and nothing that claims to decide.** Every cold Lean process pays
the Mathlib import (a median of 326 s here, about 5 s on an idle server); a REPL that has imported the
challenge once checks an attempt in about 0.01 s. So the loop keeps one REPL (or a pool) per worktree
with `Challenge` imported, and for each attempt elaborates the leaf's proof, the Gate file's `example`
and `#print axioms` in that environment. The cheap automation (`decide`, `omega`, `simp`, `norm_num`,
`exact?`) belongs there too. This is feedback, not a verdict: the REPL is an elaboration front end with
known false accepts in tactic mode (repl issue #44, open; see `scratchpad/notes/verifiers.md`, A5), it
runs the agent's code with the agent's permissions, and in Lean 4.34.1 `#print axioms` reads an imported
module's axioms from that module's own .olean (`src/lean/Lean/Util/CollectAxioms.lean`).

**At the gate, once per leaf, as the check Graphene runs at `done`: all of gate.sh.** A fresh build
directory from the trusted commit and a trusted `.lake`, the build sandboxed, then (c), (d), SafeVerify
and comparator, one after another. Each costs one or more Mathlib imports, so the gate is minutes,
not seconds; that is affordable once per leaf and not per attempt. On a machine like this one, leaves
wait for each other at the gate too: `graphene run --parallel N` (HOW_IT_WORKS.md P4) runs up to N
leaves at once, so up to N gates can overlap, which is the fan-out that ran this machine out of
memory; with Mathlib, N = 1 here. Reasons for each piece:
- (a) is what makes "the statement did not change" true without trusting the candidate's tree, and it
  is nearly free except the `.lake` clone.
- The sandbox is not optional: without it a proof rewrote its own challenge while compiling
  (`../mechanics/README.md`, finding 6). On macOS gate.sh uses `sandbox-exec`; on Linux comparator's
  landrun is the tested sandbox.
- (c) is the cheapest layer that catches a changed statement and a disallowed axiom, and its message
  ("Type mismatch", "axiom not allowed: sorryAx") is the one a person can read. It is not the last
  word, because a proof's own .olean feeds `#print axioms`.
- SafeVerify re-checks the proof in the kernel from the .olean with its own axiom walk and compares the
  statement with the challenge's; on the core cases it agreed with comparator everywhere. With `import
  Mathlib` it did not fit in this machine's memory (above); with a narrow import it should, but I have
  not measured that.
- comparator is the gold standard only with its sandbox (Linux, landrun or, from Lean v4.35, bwrap per
  the verifiers notes). On this Mac it ran without landrun, inside gate.sh's sandbox: its comparison
  and kernel replay still count, its sandbox does not.
- (d) leanchecker is the weakest layer here: it passed every negative, and SafeVerify already replays
  the same module's declarations through the kernel (my reading of both sources, for files that do not
  use Lean's module system). Keep it while it is cheap relative to the rest; drop it first if the gate
  is too slow. `--fresh` on a Mathlib closure is a nightly job, not a per-leaf check; I did not run it
  on the Mathlib layout: it holds the loaded closure and a second, fresh kernel environment with every
  constant of it, roughly twice the memory of one import, on a night when single imports were already
  pushing the disk to its floor. On core Lean alone (Init) it took 39.8 s.

**What would make the gate cheaper.** Measured: import in `Challenge.lean` only the Mathlib modules
the statements and definitions need. One lemma checked cold in 1.78 s median with
`Mathlib.Tactic.NormNum.Basic` against 146.6 s with `import Mathlib` a minute later, about 80 times
less, with half the memory; every cold layer pays that import, so the whole gate would shrink by about
the same factor (inferred, not measured end to end). The tree's author, or a tool, has to choose the
imports, and a leaf's proof may need more of Mathlib than its statement does: the leaf's own file can
import more, since only `Challenge.lean` is fixed. Not measured: running (c), (d) and the two (e)
checks in one process per leaf (no tool does that today); a pool of warm workers for the gate as AXLE
and Kimina keep, which trades away the per-request isolation comparator is built on.

**Against Graphene's limits.** A check runs with a 30-minute cap, the making of its worktree included
(`docs/HOW_IT_WORKS.md` P2 step 3). One leaf's full gate took about 9 minutes here with SafeVerify
off (`gate-mathlib-pos-SqMod4.log`); the three-leaf run had spent 13 minutes on (a)–(d) alone before
it was stopped. That fits a leaf, not a whole tree in one check, and not SafeVerify with `import
Mathlib` on this machine. The root leaf's check builds every leaf's proof, since `Proofs/Root.lean`
imports them. A narrow import in `Challenge.lean` is what would move this from minutes to seconds.
