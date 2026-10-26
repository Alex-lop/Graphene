# The hackathon entry: what to paste

For the Nebius × NVIDIA Global AI Hackathon on Devpost, track Coding and Agentic Engineering. **Submissions close
Friday 30 October 2026, 10:00 PT.** Three pieces in my words, to paste as they are or change: the form's
description, its Built with list, and the README section the rules ask for, on how Nemotron is used and where
Token Factory sped the work up. The long fields, the feedback and every number's source are in
`docs/HACKATHON.md`; the video's script is `dev/demo/STORYBOARD.md`. Nothing here may say what `claims.md` rules
out.

## Tagline

A team of coding agents on one repo, each held to its own files: NVIDIA Nemotron plans and races the work on Nebius
Token Factory, and your tests decide what lands.

## The description

The limiting factor for software won't be the next model or harness. It's going to be you, the human, and the
direction you give it. Graphene turns one goal into tested commits, with the direction kept yours. You set an
envelope once: a budget, how many tasks, how many fix rounds, the files no task may touch. NVIDIA Nemotron 3 Ultra,
on Nebius Token Factory, plans the goal as small tasks that can run at once, each with the files it may change and
a check that proves it done. Graphene accepts what fits your envelope, and three Nemotron 3 Nano agents race each
task, each in its own copy and refused before any write outside its files. A rule written before any fork ran
keeps one by test evidence, what passes lands, and then the goal's own check runs on the result: when it is red,
Ultra plans the fix. One screen, `graphene watch`, or VS Code, shows every agent and its model as it works, and
every task has its own bill from Token Factory's usage. It works with Claude Code, Codex and any OpenAI-compatible
host too.

## Built with

python · textual · rich · typer · sqlite · git · nvidia-nemotron (3 Ultra, Super, Nano) · nebius-token-factory ·
token-factory-sandboxes (contree-sdk) · claude-code · codex · github-actions · typescript · vscode-extension-api

## The README section

For the README, under its own heading, as it is:

```markdown
## Nemotron on Token Factory

For the Nebius × NVIDIA Global AI Hackathon, Graphene runs on NVIDIA Nemotron through Nebius Token Factory, from
one goal to tested commits:

    uv tool install --python 3.12 'graphene-map[nemotron]'
    graphene key set                                     # or NEBIUS_API_KEY
    graphene init --planner nemotron --executor nemotron
    graphene auto "what you want" --budget 2 --forks 3

**How Nemotron is used.** Nemotron 3 Ultra is the planner: it reads your repository with read-only tools and
answers in a strict JSON schema, so what it proposes is tasks Graphene can hold, each with its files and its check,
planned so the tasks that run at once share no file. Nemotron 3 Nano does the tasks, in Graphene's own tool loop,
whose write tools refuse a file outside the task; in auto mode three Nanos race each task and a rule written before
any of them ran keeps one by test evidence; when an attempt is refused, the next one steps up to Nemotron 3 Super.
When the goal's own check is still red after the tasks land, Ultra plans the fix.

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
from a clone). The rest of this path, auto mode included (`graphene demo --auto`), is tested against a scripted
stand-in. Every number's source is in
[docs/HACKATHON.md](docs/HACKATHON.md).
```
