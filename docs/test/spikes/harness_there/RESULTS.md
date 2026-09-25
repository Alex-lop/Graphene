# Placement B, "the harness there": the spike and its numbers against placement A

2026-09-25, on Alex's Mac (arm64, Docker Desktop 29.6.1), with no Token Factory key and no ConTree access.
The sandbox is the Docker stand-in (`sandbox.Docker`, `GRAPHENE_SANDBOX=docker`) and the model is the
recorded fake (`tests/fake_tokenfactory.py`) on this machine. Other agents were running during every
measurement (load average 6 to 10), so the seconds are noisy.

## What was built

- `Dockerfile`: `python:3.12` (the leaf sandbox's base, as `sandbox.IMAGE`) plus OpenCode **1.18.31**,
  the version `kreuzhofer/nebius-token-factory-sandboxes-demos` pins in
  `examples/python/codingagent_demo/build_image.py`. It is installed the same way: the platform binary from
  npm's registry (`opencode-linux-arm64` here, `opencode-linux-x64-baseline` on amd64), checked against
  the sha512 npm publishes for it, plus ripgrep. Image `graphene-harness-there:opencode-1.18.31`, 465 MB
  (the base is 400 MB). Only the arm64 build was made.
- `wrapper.py`: the command given to `--with`. For the leaf in `GRAPHENE_NODE` it makes a
  `graphene_map.sandbox.Sandbox` from the leaf's checkout (layer 2 included) on that image. It runs
  `opencode run --format json --auto --title leaf <contract>` there once, as the leaf's unprivileged
  user, with Token Factory (in this spike, the fake) as OpenCode's only provider. `Sandbox._bring_back`
  brings back what the scope covers. Then the wrapper says `graphene node release` when OpenCode's last
  message has a `RELEASE:` line, and `graphene node done` otherwise. It does both through
  `executor.Leaf`, the same code the Nemotron executor uses.
- `test_harness_there.py`: two tests that drive a real `run_plan` with the wrapper (they are skipped
  without Docker or the image), and `measure()`, which produced the numbers below.
- `tests/fake_tokenfactory.py`: the fake now answers with server-sent events when a request asks for
  `stream: true`. OpenCode streams through the AI SDK every time. Nothing else changed.

OpenCode's scripted conversation with the fake worked on the first attempt. What OpenCode 1.18.31 sends
(read from the fake's request log):

- `stream: true` with `stream_options.include_usage`, `tool_choice: auto` and `max_tokens: 32000`, and no
  temperature.
- Tool arguments `filePath`, `oldString`, `newString` and `command`.
- A first request with no tools that asks for a session title. `--title` stops it.
- `tools: {"webfetch": false}` in the config did **not** take webfetch out of the tools the model is
  offered. `permission: {"webfetch": "deny"}` did.

From a container, `host.docker.internal` reaches a server bound to the Mac's `127.0.0.1` (checked with a
throwaway server). A Linux host would need `--add-host` and a non-loopback bind. That was not tested.

## Commands

```
docker build -t graphene-harness-there:opencode-1.18.31 docs/test/spikes/harness_there
uv run pytest docs/test/spikes/harness_there -q            # 2 passed
uv run python docs/test/spikes/harness_there/test_harness_there.py 3
```

## The leaf

A tiny repo has `app.py` (`greet()` returns `"hi"`) and `other.py`. Leaf `greet` has scope `app.py` and
the check `python3 -c 'import app; assert app.greet() == "hello"'`. Each placement is scripted in its own
tools, with the same steps:

- **land**: read app.py, edit it, write `other.py` (outside the scope), run the shell command
  `echo x > stray.txt` (a new file outside the scope), run a shell probe for the key, run the check, then
  finish. A finishes with its `done` tool. B finishes with a last message, and then the wrapper says `done`.
- **handback**: read app.py, write `other.py`, then hand back naming `other.py`. A uses its `release`
  tool. B writes a last message with `RELEASE:` and `WANTS:` lines.

A runs `nemotron --model nvidia/Nemotron-3-Nano-fake --placement sandbox`. B runs
`python wrapper.py --model nvidia/Nemotron-3-Nano-fake`. Both run through `run_plan`, with one attempt.

## Numbers

Final configuration, 3 runs of each cell, measured 02:26 to 02:28:

|                                          | A land            | B land            | A hand-back       | B hand-back       |
|------------------------------------------|-------------------|-------------------|-------------------|-------------------|
| landed                                   | 3/3               | 3/3               | 0/3 (handed back) | 0/3 (handed back) |
| wall per leaf, median (runs), s          | 9.64 (9.31, 10.05, 9.64) | 8.89 (8.89, 9.11, 8.29) | 2.84 (2.95, 2.83, 2.84) | 7.25 (6.18, 7.60, 7.25) |
| sandbox made, s                          | 1.9, 2.0, 1.9     | 2.77, 2.66, 2.47  | 2.5, 2.4, 2.3     | 1.2, 2.26, 1.61   |
| OpenCode's one run in the sandbox, s     | n/a               | 5.25, 5.43, 4.80  | n/a               | 4.60, 4.89, 5.20  |
| model calls                              | 7                 | 7                 | 3                 | 3                 |
| characters sent to the model, whole leaf | 32,265            | 168,111 (5.2x)    | 11,497            | 69,897 (6.1x)     |
| characters per call, median              | 4,639             | 23,995            | 3,733             | 23,317            |

**Latency per tool call.** For A, the seconds come from the executor's log lines. For B, they come from
`part.state.time` in OpenCode's own JSON events, which time the tool inside the sandbox.

- A: `view`, `edit` and `write` take 0.00 s (they run in the checkout on this machine; n=3 each). `run`,
  a shell command in the sandbox, has a median of **2.32 s** (n=9, range 1.57 to 3.53). Every command is
  one sandbox round trip: create a container, copy files in, start it, commit it, write the manifest, and
  bring back what changed. `done` takes 0.38 s and `release` 0.16 s.
- B: `read` takes 0.03 s, `edit` 0.02 s, `write` 0.01 s, and `bash` has a median of **0.02 s** (n=9,
  range 0.02 to 0.13).

**Where B's time goes.** B's tools are almost free once OpenCode is running. But every leaf pays a fixed
cost of about 4.6 to 5.4 s for OpenCode's run, even the hand-back with only two tool calls. That cost is
one sandbox round trip plus OpenCode's own start-up. A pays about 2.3 s for each shell command instead.
On this Docker stand-in the two break even at about 2 to 3 commands a leaf. The tiny landing leaf has 3
commands, and its two walls are within noise of each other. The hand-back has no shell command, and there
A takes 2.8 s against B's 7.3 s.

**Two earlier samples** were taken at a different load, before `--title` and the trimmed tool set, so
each B run had 10 tools and one extra call. Median wall in seconds:

| cell        | sample 1 | sample 2 |
|-------------|----------|----------|
| A land      | 9.65     | 10.61    |
| B land      | 9.21     | 12.44    |
| A hand-back | 2.39     | 2.91     |
| B hand-back | 7.62     | 9.27     |

Between samples the seconds move by up to 3 s. That is as large as the gap between A and B when a leaf
lands. The gap on the hand-back holds in every sample.

**What these numbers do not contain:**

- **Model latency.** The fake answers in milliseconds, and a real Nano or Super call takes seconds. Both
  placements made the same number of calls here, but each B call carries about 5 times the input, which
  means more prefill time and more billed input tokens per call.
- **Token counts.** The fake's `usage` is characters/4 of the messages, not a tokenizer. The characters
  in the table are what the fake received, tool schemas included.
- **ConTree's round trip.** The ratio between A's cost per command and B's fixed cost depends entirely on
  it, and it has not been measured.
- **A real task, parallel leaves, and more than one attempt.**

## Does a hand-back carry its reason and an offered fix?

Yes, in both placements, in 3 of 3 runs, with identical results. The reason recorded is `the greeting is
also set in other.py`. `plan.offers` gives `widen greet's scope to other.py` and
`a sibling leaf for other.py; greet waits on it`. The two get there differently:

- **A:** `release(why, wants)` is a tool in the model's schema. The refused write was also logged as
  `denied` before it happened, so a hand-back that forgot `--wants` still offers the path.
- **B:** OpenCode has no Graphene tool. The wrapper adds a convention to the prompt (end the last message
  with `RELEASE: <why>` and `WANTS: <path>` lines), parses those lines, and adds the paths of writes that
  OpenCode reported as failed. A model that ignores the convention is sent to `done`. `done` then refuses
  and a second attempt is spent. An OpenCode custom tool could replace the convention. It was not built.

## What the gate can see

|                                             | A (the loop here)                  | B (the harness there)              |
|---------------------------------------------|------------------------------------|------------------------------------|
| a write tool outside the scope              | Refused by Graphene before the write, in the hook's words: `other.py is outside the scope of the node you hold (greet: app.py). …`, with the way out. Logged as `denied` on the leaf (1 in each of 3/3 runs). | Refused by layer 2 (Linux permissions) at the write. The model reads `PermissionDenied: FileSystem.writeFile (/work/other.py)`. **Nothing reaches Graphene's store** (`denied` = 0 in 3/3). Graphene learns of the path only from OpenCode's output after the run, and uses it only on a hand-back. |
| a new file outside the scope, made by a shell command | Caught after that command: not brought back, logged as `breach`, the model told in that command's result, and the file removed before the next command. | Caught once, after OpenCode exits: not brought back, logged as `breach`. **The model is never told.** The file stays in the sandbox for the rest of the run, so the model's own checks in the sandbox ran with it there. |
| in-scope edits                              | Each write passes Graphene's scope check, and the final diff is checked too. | Only the final diff. |
| while it works                              | Every step is streamed into the run log as it happens, so `graphene watch` can tail it. | Nothing appears until OpenCode exits, because the wrapper's one `Sandbox.run` returns only at the end. The events are printed afterwards. |
| `done`'s check                              | Runs in the checkout on this machine (item 6 is not built). | The same. |

## Where the key lives

- **A:** in the Graphene process on this machine only. The model's probe in the sandbox printed
  `no-key-in-env` and `no-key-file` in 3 of 3 runs. The local placement also strips the key from a
  command's environment (`tests/test_executor.py`).
- **B:** inside the sandbox for the whole of OpenCode's run. The wrapper puts it in `/tmp/graphene/key`
  and removes it before the checkpoint. OpenCode reads it through `{file:…}` in its config, so the key is
  not in any process's environment. The model's probe printed `no-key-in-env` and `key-file-readable` in
  3 of 3 runs, so **a command the model writes can read the key.** The sandbox also needs a route to Token
  Factory, so that command could use the key, or send it anywhere. On ConTree the run would need
  networking turned on, and `sandbox.Contree` does not request it today. After the run, the key is not in
  the checkpoint image: one run was checked, and a grep of `/home/leaf`, `/tmp`, `/work` and `/root` for
  it found nothing. OpenCode's session database (2.7 MB, the whole conversation) is in the checkpoint.
- This cost is structural. Any harness that calls the model from inside the sandbox needs the key there.
  The only way round it is a proxy outside the sandbox that holds the key, which is more infrastructure.
  It was not built.

## Found along the way

- **Affects both placements.** A file that the check itself writes outside the scope is logged as a
  `breach`. Here that file is `__pycache__/app.cpython-312.pyc`, which the repo's `.gitignore` already
  ignores. `plan.wanted` reads `breach` events, so a leaf that runs its check and then hands back offers
  `widen greet's scope to __pycache__/app.cpython-312.pyc`. This was reproduced with A (run the check,
  then release). `Sandbox._bring_back` does not consult `.gitignore`. It is not fixed here: `src/` is
  outside this spike.
- **Also affects both placements.** Every sandbox command keeps its checkpoint as a dangling Docker image,
  and nothing prunes them.

## Recommendation: A, "the loop here, the tools there"

1. **Held before the write.** Only A refuses in Graphene's words before the write, and logs the refusal
   where the offers are read from (`denied` in 3/3 runs, against 0/3 for B). In B the refusal comes from
   the operating system, and Graphene's store never sees it. Item 3's layer 1 cannot exist in B without an
   OpenCode plugin, and the directive calls such a plugin a courtesy, never the gate.
2. **The key.** A keeps it out of the sandbox (both probes negative, 3/3). B puts it where model-written
   commands can read it (3/3), and needs a network route out.
3. **Input size.** Each leaf in B sends 5.2 times (landing) and 6.1 times (hand-back) the characters that
   A sends. Every call carries OpenCode's 9,000-character system prompt and 12,500 characters of tool
   schemas. The thesis is cheap models in bulk, and there input tokens are the bill.
4. **Hand-back.** The offers came out the same here. A's hand-back is a tool in the schema, while B's
   depends on the model following a text convention.
5. **Visibility.** A shows each step as it happens. B shows nothing until OpenCode exits, and never tells
   the model about a breach.
6. **Wall time is B's only advantage, and it did not show here.** B's tool calls take about 0.02 s against
   2.3 s for each of A's shell commands on Docker. OpenCode's fixed cost of about 5 s a leaf offsets that:
   the two tie on the 3-command landing (within noise), and A is 2.5 times faster on the hand-back.

**What would change the call:** a measured ConTree round trip (run plus checkpoint) of many seconds, on
real leaves that run many commands. B's saving grows with the number of commands times the round trip.
So the first thing to measure once ConTree access arrives is its time per operation. Even then, cutting
A's round trips looks cheaper than giving up the gate and the key. That is untested.
