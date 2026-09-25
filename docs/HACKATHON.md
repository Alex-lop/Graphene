# Graphene for the Nebius × NVIDIA Global AI Hackathon (a draft)

*A draft for Alex, written 2026-09-25 by the agent that ran the Nemotron directive. Put it in your own
words before it goes anywhere. Every number in it says where it came from. The ones that need a live
Token Factory key are marked, and are empty until that run exists. Track: Coding and Agentic
Engineering.*

## What Graphene is

You tell your coding agents what you want in a paragraph, the way you always have. Graphene shows you
what they understood, as a tree: the goal at the top, then the pieces of work, each with the files it
may change and the command that proves it done. You prune the tree, press `R`, and agents do the
leaves in parallel. Each leaf is held to its files and its check, and a leaf that finds it needs more
comes back with the fix already written. The problem is a real one for anyone who lets agents work on a
repository for hours: today the only ways to steer them are a paragraph at the start and a diff at the
end. Graphene is where you see the agent's guess before anything is spent, and correct it with a
keystroke instead of a restart.

## How it uses Token Factory, Sandboxes and Nemotron

- **Nemotron 3 Ultra plans.** `graphene ask` (or `:ask` in the screen) calls Ultra through Token
  Factory's OpenAI-compatible API. It reads the repository with read-only tools (list, glob, grep,
  read) that run on your machine, and answers with the tree in Graphene's plan text
  (`src/graphene_map/planner.py`).
- **Nemotron Nano, then Super, do the leaves.** `graphene run --parallel N` starts one Nemotron
  executor per ready leaf (`src/graphene_map/executor.py`). The loop runs on your machine and calls
  Token Factory, and every tool call it makes (view, edit, write, run) runs in the leaf's Token Factory
  Sandbox. When a leaf's attempt is refused, the next attempt steps up to Super. `--forks N` runs N
  conversations from one sandbox checkpoint and lets the check pick the first that passes.
- **Sandboxes make a cheap model safe to use in bulk.** Each leaf gets a sandbox from the same
  checkpoint of the repository. Inside it the executor's commands run as a user who can write only
  the files the leaf's scope covers (`src/graphene_map/sandbox.py`). The executor's own write tools
  refuse a path outside the scope before writing it. A leaf is done only when Graphene runs the leaf's
  check itself, in a fresh fork of the sandbox, and git shows nothing outside the scope. What a
  command made outside the scope is never brought back. An escape test tries every way out: a
  redirect, `sed -i`, `python open(w)`, `mv`, `rm`, git, a symlink, `chmod`. Each fails, and every
  write inside the scope succeeds (`tests/test_escape.py`).
- **Model ids and prices come from Token Factory itself.** No model id is written in the code:
  `GET /v1/models` names the Nemotron Ultra, Super and Nano, and its `pricing` prices every call's
  `usage`. Each leaf's bill (dollars at list price, calls, tokens) is in its record, on the screen's
  status line and on the run's last line.

**Tonight's numbers:**
- **Every live number is still to come.** Share of leaves landed, accept and quality, cost per
  landed leaf, per task: (none yet: this run had no Token Factory key; `docs/test/bench.py` produces
  them in one command).
- **What was measured without a key.** The escape test, above. The placement decision between the
  loop here with its tools in the sandbox, and a harness such as OpenCode inside the sandbox:
  - the loop here refused an out-of-scope write in Graphene's words before it happened in 3 of 3
    runs, where the harness there left Graphene blind to it in 3 of 3;
  - the harness there put the key where model-written code could read it;
  - it sent 5 to 6 times the input per leaf.
  `docs/test/spikes/harness_there/RESULTS.md` has all of it.

## What changed during the Submission Period

The repository's first commit is 10 August 2026. The Submission Period opened on 26 August at 09:00
Pacific (16:00 UTC).

- **Before the period** (the last commit before it: `cc50a62`, 26 August 06:32 EDT), the repository
  was a different product, *Graphene Taskmaster*: "a terminal-native workflow playground for coding
  agents", with its model path on Gemini through Vertex AI. It was 66,042 lines of Python in
  `backend/` and 47,493 in `tests/`. 181 commits predate the period.
- **27 and 28 August:** runtime-recovery work on that product (PRs #7, #10, #11). On 28 August it was
  tagged `hackathon-2026`.
- **17 September:** the repository was reset to an empty package (`c8a8f6c`, "start rebuild from
  empty package (hackathon code tagged hackathon-2026)"). **Everything in `src/` today was written
  after the period opened.** None of `backend/` survives.
- **19 September:** 0.2.0, a local record of what coding agents did.
- **20 September:** 0.3.0, the plan a person and their agents share, with a gate: Graphene runs the
  check itself.
- **21 September:** 0.4.0, the plan is a tree and leaves run in parallel, a worktree each.
- **23 September:** paragraph in, tree out, prune, run: the plan as text, the screen
  (`graphene watch`), the planner (`graphene ask`).
- **24 September:** polish.
- **25 September** (this branch): the Nemotron executor and planner on Token Factory, the sandbox
  placement with the escape test, `graphene init` offering Nemotron first, the check in a clean tree,
  folding, the bill, the benchmark, and the demo page.
- **Size.** 295 commits since the period opened. `src/` is 13,919 lines of Python in 24 files (0 on
  26 August).

Commands: `git log --first-parent main --until='2026-08-26T16:00:00Z'`,
`git rev-list --count --since='2026-08-26T16:00:00Z' HEAD`, and `git grep -c '' <rev> -- 'src/*.py'`.

## Feedback on the tools

Written from what this run actually hit. Where a thing is merely unverified, it says so.

1. **The Sandboxes SDK's Getting Started describes an API no release has.** It says `Contree` and
   `ContreeSync` "just take an already-constructed `contree_client` client". On PyPI (checked
   2026-09-25), both `contree-sdk` 0.3.6 and 0.4.0.dev5 take `(config=None, *, base_url, token)`.
   We pinned 0.3.6 and built its auth from the environment.
2. **`contree-sdk` 0.4.0.dev5 and `contree-cli` cannot be installed together.** The SDK needs
   `contree-client~=0.2.1` and the CLI `~=0.4.0`, so a project that wants both gets an unsolvable
   resolution.
3. **The project variable has three names.** The CLI's auth page reads `NEBIUS_AI_PROJECT`. The SDK's
   `IAMAuth` reads `NEBIUS_PROJECT_ID`, and so does the mini-swe-agent page. The token is
   `NEBIUS_API_KEY` in both, which is good.
4. **The mini-swe-agent integration page's example is a stub** that raises "mini-swe-agent's
   ContreeEnvironment does not support user-provided contree_client clients". The page says so
   honestly, but the one integration an agent builder would copy does not run.
5. **There is no run-as-user option.** For an agent sandbox the useful default is "the agent's commands
   are not root". Graphene drops privileges with `setpriv` inside the image, which works, but a
   `user=` on `run` (or a documented pattern) would make the safe thing the easy thing.
6. **Pricing in the verbose model list is excellent.** `GET /v1/models?verbose=true` returns a price
   per token for every model, so every call's `usage` can be priced exactly, per leaf, with nothing
   hard-coded. We would like the docs to say whether those prices are the list prices billed.
7. **The rate-limit headers are well documented.** Per-model limits for the Nemotron models were not
   visible without a key. *Not verified:* whether Nemotron's function calling is reliable enough at
   Nano size to do without a text fallback. The executor has one (`--protocol text`) in case.
8. **An agent reading the rules gets a 403.** The Devpost pages answered a plain HTTP client with
   403 and needed a browser user agent. That matters for an agent reading the rules on a person's
   behalf.

## The demo

- `docs/proof/nemotron.sh`: from nothing to the end on the feeds task (needs a key).
- `docs/demo/STORYBOARD.md`: the three-minute video.
- `docs/demo/README.md`: the static, read-only demo page and the Pages workflow. It runs only when
  started by hand.
