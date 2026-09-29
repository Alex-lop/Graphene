# First light: the live record so far (practice)

**Practice, not a registered result.** Alex climbed rungs 1 and 2 of the ladder (`docs/test/practice.sh`)
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
$0.000366. `tests/test_tokenfactory.py` checks that arithmetic at the live list's prices, not the
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

## Not yet run live

- Rungs 3, 4, 6 and 7 wait for Sandboxes access. Rung 5 needs none.
- The Nemotron planner has not run live. Rung 1's tool calls went through `access.py`, not the
  planner.
