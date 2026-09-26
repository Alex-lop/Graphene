# Graphene for the Nebius × NVIDIA Global AI Hackathon: the Devpost fields (a draft)

*A draft for Alex, written 2026-09-26 by the agent that ran the winning directive. Put it in your own
words before it goes anywhere. Track: Coding and Agentic Engineering. Every sentence is meant to be
true and traceable, and every number names its source. **No number here comes from a live run.**
The session that wrote this had no Token Factory key, so the Nemotron path has run only against a
scripted stand-in for Token Factory (`tests/fake_tokenfactory.py`) and a Docker stand-in for
Sandboxes. The fields that need the evidence run say so and are left empty until it exists.*

## Inspiration

The limit on building software with agents will not be tokens or their price. It will be the human
intervention the work takes. Token Factory sells tokens cheap enough to spend in bulk, but a cheap
model you cannot trust does not save your attention. It spends it: on reading diffs, and on cleaning
up after them. So the question a Token Factory customer is really asking is *how do I hand real work
to a cheap model and trust what comes back?*

Graphene is our answer. The person and their agents share a plan, as a tree. The person prunes it
before anything is spent. Every leaf is held to the files it may change and a check that proves it
done, and the check, not the model, decides what lands.

## What it does

You tell Graphene what you want in a paragraph. Nemotron 3 Ultra, through Token Factory, reads the
repository and proposes a tree: the goal at the top, sub-goals under it, and leaves, each with the
files it may change (its scope) and the command that proves it done (its check). You read the tree
in `graphene watch`, a terminal screen with vim keys, and prune it: drop a leaf you did not mean,
take a path out of a scope, accept the rest. Then you press `R`.

Each ready leaf gets a Nemotron Nano executor, in a Token Factory Sandbox forked from one checkpoint
of your repository. `--forks N` runs N attempts at the same leaf from that checkpoint, and the first
whose check passes lands. When an attempt is refused, the next one steps up to Nemotron Super.
A leaf that needs a file outside its scope comes back with the reason and the fix already written:
one key widens its scope, another makes a sibling leaf for the file. When the tree is green,
`git log --graph` reads as the tree, one merge per leaf with its why in the message. Each leaf's bill
is priced from Token Factory's own usage at list price.

On screen, each fork is a row under its leaf, with its model and state. A step up the ladder is named
on the bottom line. The leaf's pane shows its sandbox and its bill, and its record says which fork
won and why the others did not (`docs/process/winning/screens/`, taken against the scripted
stand-in).

A person who already has an agent never has to sign up for anything: `graphene init` lists what it
finds (Claude Code, Codex, a Token Factory key), each with what it needs, and none comes first.

## How we built it

- **Token Factory's API.** Two endpoints, called from the Python standard library
  (`src/graphene_map/tokenfactory.py`). No model id is written in the code: `GET
  /v1/models?verbose=true` names the Nemotron Ultra, Super and Nano, and its `pricing` prices every
  call's `usage`. When a model is retired, a stale id falls back to the nearest listed Nemotron, and
  one line says which was used instead of which. A 429, a 5xx and a timeout are retried, then
  reported with what to do. A ledger can cap the night's spend, refusing the next call before it is
  sent.
- **Nemotron's roles.** Ultra is the planner (`planner.py`). It has read-only tools (list, glob, grep,
  read) that run on the person's machine and read only what git shows, and it answers in Graphene's
  plan text. Nano, then Super, is the executor (`executor.py`). Graphene's own loop asks for one tool
  call at a time: view, edit, write, run, done, or release. The reasoning budget is each call's
  `max_tokens`, doubled up to 32,768 when a reply is cut off at the limit. Any other model parameter
  passes through with `--param`. Nemotron's `<TOOLCALL>` text and common tool-name spellings are read
  as the calls they mean.
- **Sandboxes' checkpoints and forks.** A clean commit is uploaded and set up once, as a checkpoint
  (`sandbox.py`, contree-sdk 0.3.6). Every leaf at that commit forks it and adds only its own
  permissions, and `--forks N` forks one leaf's sandbox N times. The executor's commands run there
  as a user who can write only the files the leaf's scope covers, through `setpriv`. What a command
  changes outside the scope is never brought back. The leaf's check runs in a fresh fork, on only
  what came back. At most fifty sandbox operations run at once from one machine, the beta's cap.
- **The boundary, three layers deep.** Layer one: the executor's write tools refuse a path outside
  the scope before touching it, in the same words the Claude Code hooks use. Layer two: in a
  sandbox, the operating system refuses it too. Layer three: a leaf is done only when Graphene runs
  the check itself and git shows nothing outside the scope. An escape test tries every way out (a
  redirect, `sed -i`, `python open(w)`, `mv`, `rm`, git, a symlink, `chmod`). Each fails, and every
  write inside the scope succeeds. So far that test has run in the Docker stand-in, not in ConTree
  (`tests/test_escape.py`).
- **The rest of the product.** `graphene watch` is built with Textual, and the plan is a SQLite store
  in the repository, ignored by git. The plan has a text form that round-trips through `$EDITOR`.
  Leaves run in parallel, each in a git worktree of its own, and are merged `--no-ff`. The
  exported page (`graphene ui --export`) is React. The test suite runs in CI on Linux and macOS, on
  Python 3.12, 3.13 and 3.14.

## Challenges we ran into

- **Where the agent loop runs decides what can be refused.** We spiked both placements
  (`docs/test/spikes/harness_there/RESULTS.md`, against the stand-ins). With our own loop on the
  person's machine and the tools in the sandbox, an out-of-scope write was refused in Graphene's
  words before it happened, 3 runs of 3. With a harness inside the sandbox (OpenCode 1.18.31),
  Graphene never heard of it in 3 of 3. That harness also put the key where model-written code could
  read it, and sent 5.2 to 6.1 times the characters per leaf.
- **POSIX grants "may create" per directory, not per file.** So a sandboxed command can create a
  file the scope does not name, in a directory where the scope names another. Graphene never brings
  that file back, logs it as a breach, and removes it before the next command (decision 57 in
  `docs/DIRECTION.md`).
- **The judging period outlives model ids.** Judges may test until 15 December, and Token Factory
  retires models on notice. So roles come from the live list, and a retired id falls back within
  the family (decision 71).
- **A beta service, from the outside.** The SDK's docs describe an API no release has (below).
- **The one honest comparison we have did not favour the tree.** On 23 September, eight stand-in
  runs of the feeds task compared a plain paragraph with the tree, both on a frontier agent. The
  paragraph also passed 20 of 20 hidden acceptance checks and 12 of 12 held-out checks, and it cost
  less of the person's modelled time: 2,626 modelled person-seconds against 3,869, medians of two
  runs (`docs/test/results-2026-09-23.md`). A frontier agent does not need a tree to get a small task
  right. That is why this submission's claim is about a *cheap* model.

## Accomplishments that we're proud of

- A complete product, not a demo. It has a terminal screen with vim keys, a plan as text that
  round-trips, parallel leaves in worktrees, hand-backs that offer their own fix, a record for each
  leaf, a read-only web page, and docs that list what does not bind.
- Containment that is tested, not asserted. The escape test above holds in the Docker stand-in, and
  running it in ConTree is the first thing a key is for.
- Failure that reads as a sentence. A 429 storm, a 5xx, a timeout, a model that stops calling tools,
  a sandbox killed mid-leaf and a check that hangs each bring the leaf back with its cause and what
  to do. The run goes on, and nothing is left running (`tests/test_faults.py`, against the
  stand-ins).
- A replay for judges with no key. `graphene demo` plays a recorded run in the real screen with no
  key, no Docker and no network. It runs no model-written code, and it says on screen what it is
  replaying.

## What we learned

(The evidence run fills this in: the same paragraph, the same model, with the tree and without it,
counting correctness, the person's attention and dollars. The table is pre-registered before the
first run. Until it exists this field says only what the challenges above say.)

## What's next for Graphene

- The evidence run and its chart, in the README, the video, the demo page and here, whatever it says.
- The escape test live in ConTree, and a live leaf recorded and replayed in CI.
- A real open-source repository's issue done through the tree, with the patch offered upstream by a
  person.
- The same containment around any executor in a Sandbox: Claude Code or Codex, held to a leaf's scope
  on the sponsor's service.

## Built with

python · textual · rich · typer · sqlite · git · nvidia-nemotron (3 Ultra, Super, Nano) ·
nebius-token-factory · token-factory-sandboxes (contree-sdk) · react · vite · github-actions

## What changed during the Submission Period

The Submission Period opened on 26 August 2026 at 09:00 Pacific (16:00 UTC). The repository's first
commit is 10 August 2026.

- **Every line in `src/` was written after the period opened.** `git blame` over the 14,474 lines of
  Python in `src/` at `0334168` dates none of them before 2026-08-26 16:00 UTC (checked at the end of
  the run of 26 September; at its start, `94ce837`, it was 13,540 lines, also none).
- **Before the period** (last commit `cc50a62`, 26 August 06:32 EDT), the repository was a different
  product, *Graphene Taskmaster*, with its model path on Gemini through Vertex AI. It was reset to an
  empty package on 17 September (`c8a8f6c`), and none of that code survives.
- **Since then:** 0.2.0 (19 September), a local record of what coding agents did. 0.3.0 (20
  September), the shared plan with a gate. 0.4.0 (21 September), the plan as a tree, run in parallel.
  23 September: paragraph in, tree out, prune, run. 24 September: polish. 25 September: Nemotron on
  Token Factory and the sandbox placement. 25 to 26 September: failure paths, forks on screen, the
  replay, and the front door.
- 181 commits predate the period, and 421 were made after it opened, at `0334168`.

Commands: `git rev-list --count --until='2026-08-26T16:00:00Z' HEAD`, `git rev-list --count
--since='2026-08-26T16:00:00Z' HEAD`, and `git blame --line-porcelain` over `git ls-files 'src/*.py'`,
counting `author-time` before 1787760000 (2026-08-26 16:00 UTC).

## Feedback on Token Factory, Sandboxes and Nemotron

Written from what we actually hit. Where a thing is only unverified, it says so. (Checked
2026-09-25, before any live call: this session had no key, so nothing below was observed on the
service itself.)

1. **The Sandboxes SDK's Getting Started describes an API no release has.** It says `Contree` and
   `ContreeSync` "just take an already-constructed `contree_client` client". On PyPI, both
   `contree-sdk` 0.3.6 and 0.4.0.dev5 take `(config=None, *, base_url, token)`. We pinned 0.3.6
   and built its auth from the environment.
2. **`contree-sdk` 0.4.0.dev5 and the latest `contree-cli` (0.9.4) cannot be installed together.** The
   SDK needs `contree-client~=0.2.1`, and the CLI `~=0.4.0`. `contree-cli` 0.9.3 installs beside it.
3. **The project variable has three names.** The CLI's auth page reads `NEBIUS_AI_PROJECT`, and the
   SDK's `IAMAuth` and the mini-swe-agent page read `NEBIUS_PROJECT_ID`.
4. **The mini-swe-agent integration page's example is a stub.** It raises "mini-swe-agent's
   ContreeEnvironment does not support user-provided contree_client clients". The page says so, but
   the one integration an agent builder would copy does not run.
5. **There is no run-as-user option.** For an agent sandbox, the useful default is that the agent's
   commands are not root. We drop privileges with `setpriv` inside the image. A `user=` on `run`
   would make the safe thing the easy thing.
6. **Pricing in the model list, as documented, is exactly what an agent needs**, because every
   call's usage can be priced per leaf. *Not yet observed:* the field's presence and its units, and
   whether those are the prices billed.
7. **The SDK has no way to delete a checkpoint.** An agent that keeps each command's image
   (`disposable=False`) leaves one image per command, and the overview says untagged images are kept
   180 days.
8. **Model retirement needs a machine-readable signal.** An agent that writes model ids into a
   repository's config can fall back when an id disappears from `/v1/models`, which is what we built.
   A `deprecated_at` or `replaced_by` field in the list would let it warn *before* the id goes.

## Every number, and where it comes from

| Number | Source |
| --- | --- |
| 20/20 and 12/12, 2,626 against 3,869 modelled person-seconds | `docs/test/results-2026-09-23.md` (stand-in runs, frontier agent) |
| 3 of 3 against 0 of 3; 5.2 to 6.1 times the characters | `docs/test/spikes/harness_there/RESULTS.md` (stand-ins) |
| fifty operations at once; a peak of 50, or 56 without the slots | `tests/test_faults.py`, the thirty-leaf test (a counting fake box); 56 with `sandbox.CAP` raised to 1000, which is 8 executors × 7 forks |
| 14,474 lines, none before the period; 181 and 421 commits | git, the commands above, at `0334168` |
| the tree against the paragraph with Nemotron | none yet: the evidence run's ledger |

## Testing instructions

No key, no Docker, and no model is called:

```
uv tool install git+https://github.com/Alex-lop/Graphene
graphene demo              # a recorded run, replayed in graphene watch
graphene demo --once       # its last state, printed
git clone https://github.com/Alex-lop/Graphene && cd Graphene
SHOW_DEMO=1 uv run pytest -s tests/test_demo_script.py   # nemotron.sh against a scripted stand-in
```

With a key for Token Factory (it spends at list price, and prints the bill at the end):

```
export NEBIUS_API_KEY=…    # for Sandboxes, NEBIUS_PROJECT_ID too, and install with [sandbox]
docs/proof/nemotron.sh     # in the clone: the feeds task, from nothing to git log --graph
```
