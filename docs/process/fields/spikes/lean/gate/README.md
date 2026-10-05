# The gate for a Lean tree

`gate.sh` is the check command a leaf of a Lean tree would carry in Graphene: it exits 0 only when the
leaf's proof builds, proves exactly the statement the person approved, uses no axiom beyond `propext`,
`Classical.choice` and `Quot.sound`, survives a kernel replay, and matches its challenge in both
SafeVerify and comparator. Measurements, versions and what failed are in
[`../mechanics/README.md`](../mechanics/README.md); what each layer costs, and which belongs in an
agent's loop, is in [`cost.md`](cost.md).

## The layout it checks

| File | Who writes it | What it holds |
|---|---|---|
| `lean-toolchain`, `lakefile.toml`, `lake-manifest.json` | the tree (read-only) | Lean v4.34.1, Mathlib v4.34.1 |
| `Challenge.lean` | the tree (read-only) | every definition the statements use; each statement as `def S_<leaf> : Prop` |
| `Spec/<Leaf>.lean` | the tree (read-only) | `theorem <leaf> : S_<need> → … → S_<leaf> := sorry`, the challenge comparator and SafeVerify compare against |
| `Proofs/<Leaf>.lean` | the leaf (its whole scope) | imports `Challenge` only; proves `theorem <leaf> : S_<need> → … → S_<leaf>` |
| `Gate/<Leaf>.lean` | the tree (read-only) | `example : S_<need> → … → S_<leaf> := <leaf>` and `#print axioms <leaf>` |
| `Proofs/Root.lean` | the root leaf | imports the leaves' proofs, proves `theorem root : S_root` |

The `Spec/` stubs are an addition to the layout I was given: comparator and SafeVerify need a
challenge module holding a theorem of the same name with the approved type, and `Challenge.lean`
cannot hold it (the leaf's `theorem <leaf>` would then clash with it). Like `Gate/`, it is written
from the tree, never by a leaf.

## Run it

```sh
TOOLS_DIR=~/.cache/graphene-lean-tools ./install-tools.sh repl comparator safeverify   # ~40 s here

GATE_TRUSTED_REF=mathlib-trusted \
GATE_TRUSTED_LAKE=/path/to/trusted-checkout/.lake \
GATE_TOOLS=~/.cache/graphene-lean-tools \
./gate.sh PROJECT_DIR SqMod4 SumTwoSq Root
```

- `GATE_TRUSTED_REF`: the commit holding the approved tree. Layer (a) takes every read-only file from
  it with `git show <ref>:<path>`, never from the candidate, and fails if the candidate's copy differs.
  In Graphene this is the commit where the person approved the statements; the check's worktree
  (HOW_IT_WORKS.md P2 step 3) holds the same history, so `git show` works there.
- `GATE_TRUSTED_LAKE`: a `.lake` made from that commit alone (`lake exe cache get`, then `lake build
  Challenge Spec`), never touched by a candidate's build. It is cloned (APFS copy-on-write: 28–34 s
  for 144,200 files here), never written. Graphene's check worktree has no `.lake` (git ignores it),
  so a check must bring one.
- `GATE_COMPARATOR`: `local` (default: comparator on this machine through the fake-landrun shim its
  repository ships for macOS, so comparator's own sandbox is absent), `docker` (comparator with real
  landrun in a linux/arm64 container; only projects with no Lake dependencies, see below), or `off`.
- `GATE_SAFEVERIFY`: `on` (default) or `off`. SafeVerify builds four environments of the import
  closure per leaf; with `import Mathlib` it did not fit in this 18 GiB machine's memory tonight
  (`../mechanics/README.md`), so the Mathlib runs used `off`.
- `GATE_WORK`: keep the build and logs there. `GATE_ALLOW_SKIP=1`: accept a skipped layer (otherwise
  a skip fails the gate).

Every layer checks one leaf at a time, and (b) and the trusted build run one `lake build` per module
(Lake builds the modules it is given in parallel and has no jobs flag). This is on purpose: with
`import Mathlib`, parallel checks on this 18 GiB Mac ran it out of memory and disk
(`../mechanics/README.md`, "The memory incident").

As a leaf of a Graphene plan (the text form of HOW_IT_WORKS.md P1c; not run through `graphene plan
edit` here), one leaf would read:

```
- squares are 0 or 1 mod 4  [sqmod4]
  scope: lean/Proofs/SqMod4.lean
  check: GATE_TRUSTED_REF=lean-tree-approved GATE_TRUSTED_LAKE=$HOME/.cache/graphene-lean/v4.34.1/.lake bash tools/gate.sh lean SqMod4
```

On macOS every layer that loads candidate code (b–e) runs under `sandbox-exec` with no network and no
file writes except the proof modules' build outputs and a private tmp. Without it, a proof can rewrite
the files the later layers read while it is being compiled (shown in `../mechanics/README.md`, finding
6). `sandbox-exec` is deprecated by Apple but ships in macOS 26.5.2; nobody has reviewed this profile
for this use.

## Example runs (2026-09-30, this machine)

Core-Lean copy of the layout (`../mechanics/core/`, repository `gate-demo`, tag `core-trusted`):

```
$ GATE_TRUSTED_REF=core-trusted GATE_TRUSTED_LAKE=$S/gate-trusted-core/core/.lake GATE_TOOLS=$S/tools \
  ./gate.sh core SqMod4 SumTwoSq
(a) trusted inputs   pass      0.3s  8 files from core-trusted; none differed; .lake cloned
    trusted build    pass      0.3s  Challenge, Spec.* (reused from the trusted .lake when unchanged)
(b) lake build       pass      1.8s  Proofs.SqMod4 Proofs.SumTwoSq (sandboxed; sorry warnings: 0)
(c) type + axioms    pass      0.5s  sqMod4: [propext]; sumTwoSq: [propext, Quot.sound];
(d) kernel replay    pass      1.0s  leanchecker Proofs.SqMod4 Proofs.SumTwoSq
(e) SafeVerify       pass      2.9s  Spec.<leaf>.olean against Proofs.<leaf>.olean
(e) comparator       pass      3.1s  no landrun (fake-landrun shim; sandboxed by this script)
gate: PASS
```

The same with the two statements changed (`../mechanics/core/negatives/`: mod 3 for mod 4; an extra
hypothesis):

```
(b) lake build       pass      4.6s  Proofs.SqMod4 Proofs.SumTwoSq (sandboxed; sorry warnings: 0)
(c) type + axioms    FAIL      0.6s  sqMod4: type: Gate/SqMod4.lean:3:22: error: Type mismatch; sumTwoSq: type: Gate/SumTwoSq.lean:3:35: error: Type mismatch;
(d) kernel replay    pass      1.0s  leanchecker Proofs.SqMod4 Proofs.SumTwoSq
(e) SafeVerify       FAIL      3.9s  rejected SqMod4 SumTwoSq: Found a problem in .lake/build/lib/lean/Proofs/SqMod4.olean with declaration sqMod4: theorem type mismatch
(e) comparator       FAIL      2.9s  rejected SqMod4 SumTwoSq: uncaught exception: Challenge and solution theorem statement do not match: 'sqMod4'
gate: FAIL
```

A `sorry`: (c) FAIL `sqMod4: axiom not allowed: sorryAx`, SafeVerify FAIL `uses disallowed axioms`,
comparator FAIL `Illegal axiom detected: 'sorryAx'`, leanchecker passes. An edit to `Challenge.lean`: (a) FAIL `differ from core-trusted (the trusted
copies are used): Challenge.lean`. A proof that writes `Spec/SqMod4.lean` while it compiles: (b) FAIL
`error: Proofs/SqMod4.lean:7:0: operation not permitted`. With `GATE_COMPARATOR=docker` the positive
run's comparator line reads `pass 37.8s landrun in Docker: comparator SqMod4: pass 4.5s comparator
SumTwoSq: pass 4.8s`. These runs were made before gate.sh became strictly sequential; at 03:12 the
positive, the changed statements, the `sorry` and the file-writing proof were rerun with the sequential
gate.sh and gave the same verdicts at the same layers, every layer in ≤ 5.3 s. The Mathlib runs are in
`../mechanics/README.md`.

## What this says about today's Graphene

With this layout, the statement is protected by what Graphene already has: the leaf's scope is its one
`Proofs/<Leaf>.lean` (a write to `Challenge.lean`, `Spec/`, `Gate/` or the lakefile is refused at
`done`, HOW_IT_WORKS.md P2 step 2), and gate.sh is its check command. Two things the check has to bring
itself, because Graphene's check worktree holds only what git tracks (decision 62): a trusted `.lake`
(7.6 GB, cloned in 28–34 s here) and a sandbox. The sandbox is the part a plain `lake build && …`
check lacks: compiling a proof runs the proof's code with the person's permissions, and a proof that
wrote its own challenge file passed comparator without one (`../mechanics/README.md`, finding 6).
Layer (a) repeats the scope rule inside the check, so the gate means the same thing when it is run
outside Graphene. Nothing here needed a new Graphene feature; the tests are the core runs above and the
Mathlib runs in `../mechanics/README.md`.

## Limits I know of

- The trusted `.lake` lives outside the repository, where an agent running as the same user can write.
  The gate never writes it and sandboxes candidate code while it runs, but nothing stops an executor
  from editing it between runs. The same holds for `GATE_TOOLS`. This is the gap HOW_IT_WORKS.md P5
  already names for what git ignores; closing it needs another user, a read-only mount, or checking
  the `.lake` against Mathlib's cache hashes before each gate. Not done.
- Layer (c) parses the text `lean` prints. A proof module can run code when it is imported (an
  `initialize` block) and print anything; the sandbox keeps it from writing files, not from printing.
  SafeVerify and comparator do not read that text.
- comparator runs here without its own sandbox (fake-landrun), inside `sandbox-exec`. Its real sandbox
  was exercised only on the core-Lean layout, in Docker.
- The profile allows every read, so a proof can read the machine while it compiles; it cannot write
  outside its build outputs or open a network connection.
- Only the layout's naming convention ties a leaf to its theorem (`SqMod4` → `sqMod4`) and its needs
  to its type; the Gate and Spec files are what the person approves, and they must be generated from
  the tree, not written by hand per leaf.

## Files

- `gate.sh`: the gate.
- `install-tools.sh`: builds REPL, comparator + lean4export, SafeVerify and LeanParanoia at pinned
  revisions for v4.34.1, with the source patches SafeVerify and LeanParanoia need.
- `docker/`: the image (landrun built from source) and `comparator.sh`, which runs comparator with real
  landrun. On Docker Desktop, Landlock denies every read, write and exec on a bind-mounted host
  directory, so the toolchain and the project are copied into a tmpfs inside the container, and a
  project that needs Mathlib's 7.6 GB `.lake` does not fit: `comparator.sh` refuses it.
- `cost.md`: what each layer costs and where it should run.
