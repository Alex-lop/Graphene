#!/usr/bin/env python3
"""The brief a stand-in person is given, printed rather than written by hand each time.

    docs/test/standin.py <task> <dense|tuesday> <prompt|graphene> <run-dir> <venv-bin> [--parallel]

One generator for both arms and both styles, so anyone auditing can diff the two briefs and see
that what differs between them is the method and the manner, and nothing else. The card is pasted
in whole at the end; it is the only thing the stand-in knows that the executor does not.

The stand-in is not told what is being measured. On 20 September every stand-in knew the
hypothesis and several said in their notes which way they thought a choice cut.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

FLAGS = (
    "--model sonnet --permission-mode acceptEdits --output-format json "
    "--allowedTools Read Edit Write Glob Grep 'Bash(graphene *)' 'Bash(python3 *)' "
    "'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)'"
)
# What `graphene run --with` takes: no prompt. Graphene appends `--session-id <uuid>` and then the
# prompt, so the prompt never lands inside the variadic --allowedTools.
EXECUTOR = f"claude -p {FLAGS}"
# What a person types themselves: the prompt goes straight after -p, for the same reason. Five of
# the 20 September runs lost their first call to --allowedTools eating the prompt.
BY_HAND = f'claude -p "$MSG" {FLAGS}'

STYLES = {
    "dense": """You are careful, and you type a lot. You think before you write and you say every
  constraint you can still remember, in full sentences, in your own words. You re-read a message
  before you send it. There is no length limit: say as much as you want to say. When you shape
  anything, you shape all of it, until each piece says what you actually mean.""",
    "tuesday": """It is Tuesday afternoon and you are on your way to something else. You give this
  under a minute. You type in under thirty words, lower case, no bullet points, no file names, no
  list of constraints — the thing you want, the way you would say it to someone at the next desk,
  trusting them to ask if it matters. You do not write long anything. You come back later, look at
  what happened, and if it is wrong you say so, briefly.

  Take that literally. Your opening message is under thirty words. Count them before you send it.""",
}

# Two lines were added to every brief between repetition 1 and repetition 2 of the 21 September
# run, because repetition 1 showed they were needed, and both arms of a repetition always got the
# same brief:
#
#   "Take that literally … count them"  — the tuesday stand-ins were writing a thousand characters
#                                          while being told to write thirty words.
#   "log the FULL text …"               — stand-ins were logging `graphene run --with claude -p …`
#                                          instead of the line they typed, understating their own
#                                          person_chars, which flatters the plan arm.
#
# So repetition 1 and repetition 2 are not quite the same instrument. The results file says so,
# and the per-repetition numbers are printed rather than only their median.

ARMS = {
    "prompt": """There is no plan. You work the way you always have: you type a message into a
  session, you read what came back and the diff, and if it is not what you wanted you say so.

  1. Send your opening message to the executor.  -> log as `prompt`
  2. Read its `result` and `git diff {base}`. Carry on in the same session with `--resume
     <session_id>`, as many messages as you like. A message that is new information or the next
     step is a `prompt`; a message that says "no, that is not what I meant" is a `correction`.
  3. The change of mind on your card is a follow-up message, once the first part works, and it
     costs you one of your three corrections. Log it as a `correction` with `--mandated`.
  4. Stop when the card is satisfied as far as you can tell, or the budget is gone.""",
    "graphene": """There is a plan, and it is a tree: the root is your goal in your words, its
  children are how it will be achieved, the leaves are work someone does. You say the goal, an
  agent proposes the tree, you prune and edit it, you accept it, and then it runs.

  1. as_me graphene plan goal "<why you want this, in your words>"        -> log as `shape`
  2. Ask an executor for a tree. Its message must contain, word for word: propose a plan with
     `graphene plan propose -`, reading the JSON on standard input. The `-` matters: it is how
     nobody ends up writing a scratch file anywhere.                      -> log as `prompt`
  3. Read what it proposed: `as_me graphene plan --all`. Shape it:
        as_me graphene node set n2 --scope 'a/**' --scope 'b/c.py' --check '<a command>' --goal '…'
        as_me graphene node add "<the one it missed>" --parent n1 --scope '…' --check '…'
        as_me graphene node drop n5
     Shaping is free and is not a correction.                             -> log each as `shape`
  4. as_me graphene plan accept                                           -> log as `accept`
  5. {runcmd}
                                                                          -> log as `run`
  6. If it stops on something that is yours, do it by hand through the gate:
     `as_me graphene node start <id>` … `as_me graphene node done <id>`   -> log as `handwork`
  7. The change of mind on your card is applied at the boundary: `as_me graphene node set` on a
     node that has not started, which is a `shape`. If no such node is left, it is a
     `graphene node add`, or a `graphene node reopen` — and a reopen is a correction.
  8. Review with `as_me graphene plan --all`, `as_me graphene plan log`, `git diff {base}`.
                                                                          -> log as `review`
  A correction in this arm is: editing a node that has already started, `graphene node reopen`, or
  a release that needs you.""",
}

BRIEF = """You are standing in for the person who wants a change made to a small codebase. Play
the person, not an assistant. You decide what good looks like; nobody is marking your work.

Your card is at the bottom. It is what you want, and nobody else has a copy. You may never paste
it into anything, and you may not read any other file under docs/test/.

WHERE THINGS ARE
  repo          {repo}
  base commit   {base}
  run log       {runlog}
  your TMPDIR   {tmp}          every temporary file anything makes goes in here
  notes         {run}/notes.md

BEFORE YOU TYPE ANYTHING

  export PATH="{venv}:$PATH"
  export TMPDIR="{tmp}"
  cd {repo}
  as_me() {{ env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT -u GRAPHENE_NODE \\
             GRAPHENE_AS="person:$(id -un)" "$@"; }}

  `graphene init` has already been run for you. Check `command -v graphene` prints a path under
  {venv}. If it does not, stop and say so: the wrong build is on PATH and the run is void.

THE RULE THAT MAKES THIS FAIR

  You have not opened this repository in a year and you do not know its layout. Write your first
  message from the card alone: do not list the files, do not grep, do not read one file in the
  repo before that first message is sent. Afterwards, look at whatever you like.

HOW YOU WRITE

  {style}

WHAT YOU DO

  {arm}

LOGGING — as you go, never afterwards from memory

  python3 {here}/logline.py {runlog} person shape "as_me graphene plan accept"
  printf '%s' "$MSG" | python3 {here}/logline.py {runlog} person prompt
  python3 {here}/logline.py {runlog} person correction "no, the other one" --mandated
  python3 {here}/logline.py {runlog} executor result --from-json "$TMPDIR/e1.json"

  IMPORTANT: log the FULL text of every command you run as the person and every message you send,
  not an abbreviation of it. If you ran a long `graphene run --with "…"`, the logged text is that
  whole line. Pipe anything with quotes or newlines in it on stdin. Never log a `result` for an
  executor that `graphene run` started: its cost is read out of `.graphene/runs/` and logging it
  as well would count it twice.

THE EXECUTOR — the same command, the same tools, in both arms

  env -u GRAPHENE_AS {by_hand} < /dev/null > "$TMPDIR/e1.json"

  Its `result` field is what it said back; `session_id` is how you carry on:
  `--resume <session_id>` after the other flags. Your message goes straight after `-p` and nowhere
  else: `--allowedTools` takes a list and will eat a prompt that comes after it.

  Two pieces of grit, both found the hard way, both the same for every arm. Write the whole
  invocation — your message in a quoted heredoc, then the command — into one script under
  $TMPDIR and run `bash that-script.sh`: a Bash call that merely contains the string `git` is
  refused here, and a file written in one call is not reliably there in the next. Each executor
  call takes minutes; give the Bash call a 900000 ms timeout.

YOUR BUDGET

  Three corrections, and no more. A correction is a message that says "no, not that", in any form
  however polite. A fourth ends the run and it is reported as abandoned with the three it spent.
  The change of mind at the bottom of your card is not optional: ask for it, once the first part
  works.

WHAT YOU MUST NOT DO

  - read docs/test/tasks/*/accept.py, quality.py or intent_globs.txt. They exist. They are not
    yours, there is no hidden checklist you are allowed to see, and looking voids the run.
  - write anything outside {repo} and {tmp}
  - tune anything once you have started. If it goes wrong, let it go wrong and write it down.
  - `git commit` by hand.

  You may run the repository's own tests. That is ordinary work.

WHEN YOU ARE FINISHED

  Log a `review`. Write {run}/notes.md: what you did in order, what surprised you, what you still
  think is wrong with the result, and how much of your own attention the whole thing took. Be
  blunt; a run that went badly is worth more written down than tidied up. Then hand back a report
  of at most fifteen lines.

================================ YOUR CARD ================================

{card}
"""


def main(argv: list[str]) -> int:
    if len(argv) < 6:
        sys.stderr.write(__doc__)
        return 2
    task, style, arm, run_dir, venv = argv[1], argv[2], argv[3], Path(argv[4]), argv[5]
    parallel = "--parallel" in argv[6:]
    if style not in STYLES or arm not in ARMS:
        sys.stderr.write(f"style is one of {', '.join(STYLES)}; arm is one of {', '.join(ARMS)}\n")
        return 2
    base = (run_dir / "base.sha").read_text().strip()
    runcmd = (
        'as_me graphene run --parallel 2 --with "{e}"\n     Two leaves at once, each in its own '
        "worktree, merged here when the merge is clean."
        if parallel
        else 'as_me graphene run --with "{e}"'
    ).format(e=EXECUTOR)
    print(
        BRIEF.format(
            repo=run_dir / "repo",
            base=base,
            runlog=run_dir / "runlog.jsonl",
            tmp=run_dir / "tmp",
            run=run_dir,
            venv=venv,
            here=HERE,
            style=STYLES[style],
            arm=ARMS[arm].format(base=base, runcmd=runcmd),
            by_hand=BY_HAND,
            card=(HERE / "tasks" / task / "intent.md").read_text(encoding="utf-8"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
