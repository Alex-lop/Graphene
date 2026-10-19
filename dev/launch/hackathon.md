# The hackathon entry: what to paste

For the Nebius × NVIDIA Global AI Hackathon on Devpost, track Coding and Agentic Engineering. **Submissions close
Friday 30 October 2026, 10:00 PT.** Three pieces in my words, to paste as they are or change: the form's
description, its Built with list, and the README section the rules ask for, on how Nemotron is used and where
Token Factory sped the work up. The long fields, the feedback and every number's source are in
`docs/HACKATHON.md`; the video's script is `dev/demo/STORYBOARD.md`. Nothing here may say what `claims.md` rules
out.

## Tagline

The plan you and your coding agents share: NVIDIA Nemotron plans and does the work on Nebius Token Factory, and you
steer every agent from one screen.

## The description

The limiting factor for software won't be the next model or harness. It's going to be you, the human, and the
direction you give it. Graphene is the plan you and your coding agents share. You say what you want in a
paragraph; NVIDIA Nemotron 3 Ultra reads the repository on Nebius Token Factory and proposes tasks, each with the
files it may change and a check that proves it done, and it asks first where the code can't tell it what you
meant. Nemotron 3 Nano agents then do the tasks, with Super on a retry, and one screen, `graphene watch`, shows
every one of them: what needs you on top, a task that came back with its reason, one key to widen it, tell it
something or try it again. A task is done only when Graphene has run its check itself, and every task has its own
bill from Token Factory's usage. It works with Claude Code and Codex too.

## Built with

python · textual · rich · typer · sqlite · git · nvidia-nemotron (3 Ultra, Super, Nano) · nebius-token-factory ·
token-factory-sandboxes (contree-sdk) · claude-code · codex · github-actions

## The README section

For the README, under its own heading, as it is:

```markdown
## Nemotron on Token Factory

Graphene works with the agent you already use, Claude Code or Codex. For the Nebius × NVIDIA Global AI Hackathon I
built a third way to run it, on NVIDIA Nemotron through Nebius Token Factory:

    uv tool install --python 3.12 'graphene-map[nemotron]'
    graphene key set                                     # or NEBIUS_API_KEY
    graphene init --planner nemotron --executor nemotron

**How Nemotron is used.** Nemotron 3 Ultra is the planner: it reads your repository with read-only tools and
answers in a strict JSON schema, so what it proposes is tasks Graphene can hold, each with its files and its check.
Nemotron 3 Nano does the tasks, in Graphene's own tool loop, whose write tools refuse a file outside the task; when
an attempt is refused, the next one steps up to Nemotron 3 Super.

**Where Token Factory sped it up.** One API key and one OpenAI-style endpoint, called from Python's standard
library, with no SDK to learn. The same model family in three sizes, so each role gets the size it needs: the large
one plans once, the small cheap one does the bulk, the middle one takes a retry. A model list that carries each
model's price, so every call's tokens become a bill per task, shown in the cockpit: a night of 408 calls on 2
October came to $1.80 at list price, $1.70 of it the planner. And Sandboxes, in beta, which run each task in a
fork of one checkpoint of the repository, where the operating system refuses a write outside the task's files;
without them the tasks run in git worktrees on your machine.

**What ran live.** Practice on 29 September and 2 October, then 31 demo takes on two small repositories and 80
asks of the planner on 7 to 9 October; on the build of 9 October, Ultra's answer became a plan in 35 of 40 asks.
Two of those runs replay in the cockpit with no key (`graphene demo tests/recordings/loop-nemotron-take-2.jsonl`,
from a clone). The rest of this path is tested against a scripted stand-in. Every number's source is in
[docs/HACKATHON.md](docs/HACKATHON.md).
```
