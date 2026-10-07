# First light: the live record so far (practice)

**Practice, not a registered result.** Alex climbed rungs 1 and 2 of the ladder (`dev/test/practice.sh`)
by hand on 29 September 2026, on his own key, in his own terminal, before the first-light run began.
Nothing here enters a registered table. Each fact names the file it comes from. The files are in
Alex's checkout under `.graphene/practice/`, which git ignores; none is copied here. Each was read only
after a leak check that counted the key's and the project id's values in it: 0 in all five.

## The rungs

| rung | result | at (EDT) | seconds | this rung, list price | source |
|---|---|---|---|---|---|
| 1 access to Token Factory | PASS | 01:14 | 4.2 | $0.000844 | `progress.json` |
| 2 one leaf local on Nemotron | PASS | 01:16 | 6.9 | $0.000366 | `progress.json` |
| 3 to 7 | not run | | | | |

**Rung 1** (`rung-1.log`, `access.json`). Token Factory listed 25 models for the key. These are the
NVIDIA ones, with the roles `tokenfactory.roles` gave them:

| id | role | $ per million in / out |
|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | nano | 0.06 / 0.24 |
| `nvidia/Nemotron-3_5-Lightning` | none | 0.06 / 0.24 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | ultra | 1.00 / 3.00 |
| `nvidia/nemotron-3-super-120b-a12b` | super | 0.30 / 0.90 |

The three ids are spelled three ways, and `roles` reads them case-blind. The fourth model is NVIDIA's
Nemotron 3.5 Lightning, 30B with 3B active. NVIDIA says it "follows Nemotron 3 Nano"
(blogs.nvidia.com/blog/nemotron-lightning-switchyard-rtx-dgx, read 2026-09-29). Token Factory names it
as Nemotron-3-Nano-Omni's replacement from 31 August (docs.tokenfactory.nebius.com/august-2026-deprecation-notice).
Its id names no size, so no role and no default can fall to it. The sanitised list is
`tests/fixtures/tokenfactory-models-2026-09-29.json`.

Each model made one tool call as asked: `get_current_weather` with `{"city": "Dallas", "unit":
"fahrenheit"}`, answered in 0.9 s (Ultra), 1.1 s (Super) and 1.1 s (Nano).

Sandboxes answered `FAILED: ForbiddenError: You do not have permission to perform this action`
(`rung-1.log`). Rung 1 passed anyway, because it is Token Factory's rung.

**Rung 2** (`rung-2.log`). Feeds was built in `~/graphene-practice/2-local-20260929-011645` (base
`5cd0bd1`). `graphene init --planner nemotron --executor nemotron` wrote these from the live list:
- planner: `nemotron --model nvidia/Nemotron-3-Ultra-550b-a55b`
- executor: `nemotron --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B --model nvidia/nemotron-3-super-120b-a12b --placement sandbox`

The executor got `--placement sandbox` because ConTree's credentials were set. The rung runs its leaf
with `--with nemotron`, which places it on this machine. The practice leaf `hello` (create
`practice_hello.py` holding `VALUE = 42`) ended as: `hello attempt 1: the executor ended (exit 0)`,
`hello is done`, `run: 1 done; $0.0004 at list price`.

## The bill (`ledger.jsonl`, 12 rows, list price)

| rows | what | tokens in / out | $ |
|---|---|---|---|
| 3, at 00:55:59 | an access check: Ultra, Super, Nano | 373/81, 420/54, 338/165 | 0.00085048 |
| 3, at 01:05:17 | an access check: the same | 373/81, 420/55, 338/174 | 0.00085354 |
| 3, at 01:14:03 | rung 1's access check, the one `progress.json` keeps | 373/81, 420/54, 338/136 | 0.00084352 |
| 3, at 01:16:49 | rung 2's leaf, all on Nano | 1334/186, 1402/191, 1465/98 | 0.00036606 |
| **12** | | | **0.0029136** |

The bill is $0.0029 against the night's $10. Rung 2's three rows at the live list's Nano price are
$0.00012468, $0.00012996 and $0.00011142. They add up to $0.00036606, which `progress.json` rounds to
$0.000366. `tests/nemotron/test_tokenfactory.py` checks that arithmetic at the live list's prices, not the
fake's. One Nano call, at 01:05:30, took 11.9 s. Every other call took 0.9 to 1.4 s.

## The ForbiddenError

contree-sdk 0.3.6 raises `ForbiddenError` for a 403, with the text "You do not have permission to
perform this action". Rung 1's log does not say which call met it. The first call `sandbox.Contree`
makes is the image pull, which looks `python:3.12` up by tag and imports it when it is missing.
Nebius's API reference gives a 403 as "Token does not have sufficient permissions"
(docs.tokenfactory.nebius.com/api-reference/sandboxes/instances/spawn-a-new-container-instance.md).
Its CLI page says a key without the `list` permission "means sandboxes are disabled on this project"
(docs.tokenfactory.nebius.com/sandboxes/cli/commands/auth.md). contree.dev says: "Request access at
tokenfactory.nebius.com/sandboxes/about". All three were read 2026-09-29.

One more 403 came from a harness slip, not from the ladder and not practice. At about 02:00 a first
draft of a test in lane A placed its leaves in Sandboxes by mistake. The real ConTree was sent the
scripted fake's key (`fake-key`) and a made-up project id, and it answered 403, not 401. No log of
that run was kept. Its only record is the message of commit e5efb4f, and it has not been repeated on
purpose. So a 403 alone may not tell a key without the grant from a `NEBIUS_PROJECT_ID` that is not
the key's project.

Graphene now says this once, in the same words, in `access.py`, on the ladder, for a leaf placed in a
sandbox and in `plan precheck`: "Sandboxes refused this project (403): its key may not use them there,
or NEBIUS_PROJECT_ID is not its project; request access at tokenfactory.nebius.com/sandboxes/about". When
ConTree's whoami lists the key's grants, the message names the grants it lacks. It is tested against a
stub raising the SDK's own class.

Rung 2's `graphene init` placed the leaves in Sandboxes a minute after rung 1's 403, because it asked
only whether a key and a project id were set. `init` now asks whoami first. whoami is a read, not an
operation. When whoami refuses, `init` places the leaves on this machine and says why in one line.

## Sandboxes: free in the beta, by Nebius's page

Nebius's Sandboxes page, as the search index quoted tokenfactory.nebius.com/sandboxes on 2026-09-29,
says: "Sandboxes are free while in beta—runs don't consume your credits". The page draws only in a
browser, and a direct read returned its title alone. No Nebius page states a price:
- docs.tokenfactory.nebius.com/sandboxes/overview says "Sandboxes are currently in Beta".
- contree.dev says "Pay per execution, not idle", with no rate.

No bill has shown a Sandbox line yet.

## What the ladder now checks live

- **Every rung** counts the key's and the project id's values in each file it wrote. A count above 0
  fails the rung. The values are never shown.
- **Rung 4** gives a `sleep 600` five seconds in the Sandbox. It needs exit 124 and the next command
  to run.
- **Rung 5** counts its recording for the key, the project, a home path and key-shaped words, then
  prints the command that makes `tests/recordings/` and copies the recording there. CI replays every
  recording in it.

## 2 October: the live half (practice)

An agent climbed the rest of the ladder in a Claude Code session Alex started with
`GRAPHENE_AGENT_LIVE_USD=10`. Every call went on one night ledger
(`~/.graphene/night/2026-10-01.jsonl`). The plan was `dev/process/directives/PRACTICE_PLAN.md`. This
is practice; nothing here enters a registered table. Times are EDT; the logs are in the night's worktree
under `.graphene/practice/`, git-ignored, and every rung counted the key's and the project's values in
the files it wrote: 0 each time.

| rung | result | at | seconds | list price |
|---|---|---|---|---|
| 2 one leaf local on Nano | PASS | 00:47 | 12.1 | $0.0005 |
| 3 one leaf in a Sandbox | PASS, hollow (below) | 00:49 | 78.2 | $0.0021 |
| 4 the escape test in ConTree | FAIL, twice | 00:49, 00:52 | 19.0, 18.7 | $0 |
| 4 again, after the fix | PASS: 10 ways out failed or were refused, 2 ways in came back, exit 124 at its 5 s limit in 6 s; 33 operations | 01:02 | 27.2 | $0 |
| 3 again, after the fix | PASS: the leaf's check ran inside ConTree and exited 0; 7 operations | 01:02 | 18.2 | $0.0004 |
| 5 a recorded leaf | PASS: replays "as it ran, live", `demo.leaks` 0 | 01:03 | 8.5 | $0.0003 |

**The ConTree break.** On ConTree (kernel 7.0.6, coreutils 9.7 in `python:3.12`), a `cat` whose output
is a file leaves that file unwritable: `{ cat FILE; echo after; } > OUT` fails at the echo with an I/O
error, while `$(cat FILE)` and `cat FILE | cat` write whole. Docker does not do this, so the dry ladder
passed. The sandbox's list of files began with `cat /tmp/graphene.code`, so no command's list came back,
and every command read as exit 1. Rung 3's first PASS was hollow: all 7 of its executor's commands came
back that way, even `echo hello`. The leaf landed because its one file was pushed and its check ran in a
fresh ConTree fork, whose output does not pass through a file. Fixed in a09435d: the list takes the code
through `$(...)`. A leaf's placement record counts its lost lists, and rungs 3 and 7 fail on any. Six
small diagnostic scripts in ConTree found it, in 57 operations with no model call, as a deliberate
exception to the plan's "ladder only" rule. Their output was read in the session and not kept.

The closing review found the same shape one step further in. An executor's own command wrote its output
to a file opened with `>`, so `cat app.py; echo after-cat` exited 1 and lost the echo, as probed live. An
output opened for append (`>>`) gives rc=0 and the whole output, for root and the leaf user alike. That
fix is a7ee473. A done-check in a fork already came back whole, since its output is ConTree's own. The
review's probes took 20 more operations.

**The prototypes** (`practice.sh prototypes`, 01:04 and 01:06). cover passed twice. precheck passed
twice; its third check ran in a Sandbox fork, and each red was read for the right reason. note asked
about two notes, each twice, and routed one of them once:
- the first note: Nano put every field into `target`, then on the second run it was routed to its
  leaf's goal;
- the cents note: Nano wrote the string `"null"` as a glob (fixed in 222b678), then on the second run
  the answer was cut off at note's 2,048-token cap.

On the ten prototype calls Nano used 174 to 2,048 completion tokens (cover 1,116 and 1,334; note 1,247,
1,002, 920 and 2,048; precheck 263, 236, 174 and 458), each for a JSON answer of about 100 tokens. That
suggests it reasons before it answers. The reasoning text was not read, and ten calls are not a measure.

## Rung 7, five takes on one code state (222b678)

Each take is `dev/proof/nemotron.sh` on feeds with its own public paragraph. Nemotron 3 Ultra plans,
Nano executes (Super on a second attempt), and the leaves run in Token Factory Sandboxes. The prune is
scripted: `cli/main.py` leaves every scope, and a leaf that comes back for it is widened.

| take | at | result | seconds | planner | executors | leaves | board |
|---|---|---|---|---|---|---|---|
| 1 | 01:07 | PASS | 265 | $0.3733 (60 calls) | $0.0090 | 3 of 3 landed; one came back for `cli/main.py` and was widened | none |
| 2 | 01:12 | FAIL at the planner | 83 | $0.3321 | — | — | — |
| 3 | 01:14 | PASS | 624 | $0.3036 (30 calls) | $0.0779 | 2 of 3 landed; one came back and was widened; one released | 2 questions, 1 risk |
| 4 | 01:25 | FAIL at the planner | 109 | $0.3393 | — | — | — |
| 5 | 01:28 | FAIL at the planner | 97 | $0.3543 | — | — | — |

- **Neither passing take built everything asked.**
  - Take 1's landed code reads the feed's prices, already in cents, as dollars: NW-1's `1299` comes out as
    `"price_cents": 129900` (rerun from its repo, `python3 -m cli.main load samples/prices.xml --source
    xml`). Ultra's checks for its three leaves printed or ran the command, and asserted nothing about a
    price, so each passed.
  - Take 3's landed code does not skip price 0, because the leaf that would have was released.

  A check that cannot fail on the wrong work is the gap Graphene exists to show the person.
- **The planner wrote a tree Graphene could read on 2 of 9 asks** (each take asks twice at most):
  - 3 asks used all 30 steps without proposing;
  - 2 put prose or markdown lines where a node's lines go (`'**normalize/fields.py** (in …' is not
    indented under …`);
  - 1 named a `needs:` id that is not a node;
  - 1 answered in prose with no tree.

  Ultra is 95% of the night's bill ($1.70 of $1.80).
- **Take 3's board:** should price 0 be rejected for every source (`validate/rules.py`), the XML field
  map, and a regression risk. The defaults were taken. None was the legacy-feed question Claude Code
  asked of the same paragraph.
- **Take 3's leaf that did not land** asked for `python3 -m pytest tests/test_xmlfeed.py -q`.
  - The leaf's own executor installed pytest in its Sandbox with pip (the Sandbox reaches the
    internet), and its test passed there.
  - Graphene runs the check in a fresh fork of the image the leaf started from, which has no pytest. So
    `done` was refused three times, and the leaf was released with that reason. Before Super took over,
    Nano called `str_replace_editor` (which Graphene reads as `edit`) with `command: view` 34 times in its
    40 steps, 32 of them running, and gave up.
- **Recordings:** take 1's is kept as `tests/recordings/first-light-rung-7.jsonl`. Its actor is the
  login name, as a person's run records it. Take 3's names `/home/leaf/…`, the Sandbox user's home, which
  `demo.leaks` counted as a home path until ff76809. It was not kept.

The bill for the night: $1.7950 at list price. Ultra was 244 calls and $1.7026, Super 28 calls and
$0.0544, Nano 136 calls and $0.0381, 408 calls in all. Sandboxes: 311 operations and 4.8 minutes,
diagnostics included, priced at $0 because no price is published.

## Not yet run live

- Rung 6 and the registered runs: Alex's, with him there.
- A filmed take (`dev/demo/build.sh`): Alex's; `build.py` refuses an agent.
