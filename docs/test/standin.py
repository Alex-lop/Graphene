#!/usr/bin/env python3
"""The brief a stand-in person is given, printed rather than written by hand each time.

    docs/test/standin.py <task> <dense|tuesday> <prompt|tree> <run-dir> <venv-bin>

One generator for both arms and both styles, so anyone auditing can diff the two briefs and see
that what differs between them is the method and the manner, and nothing else. The card is pasted
in whole at the end; it is the only thing the stand-in knows that the executor does not.

The stand-in is not told what is being measured. On 20 September every stand-in knew the
hypothesis and several said in their notes which way they thought a choice cut.

23 September: the `tree` arm replaces the `graphene` arm (git has the old brief). The person types
their paragraph to a session in the repo, whose hooks turn it into a proposed tree, and prunes it
only with the commands `graphene watch`'s keys run. Every shell sources the run's env.sh (newrun.sh
writes it), and everything the person reads is logged as `read`, in both arms, so attention can be
modelled from the log rather than guessed.
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
    "tree": """There is a plan, and it is a tree: the root is what you want, its children are
  how it will be done, the leaves are work an agent does. You say what you want to a session in
  the repo, the way you always have; the repo's hooks make that session propose a tree instead of
  writing code; you read the tree, prune it, and let it run. The key in brackets is the key that
  runs the same command in `graphene watch`; here you type the command.

  1. Send your opening message to the executor, in the repo: it is the session that proposes.
                                                                          -> log as `prompt`
  2. Read its `result` and the tree: `seen as_me graphene plan --text` (a proposal is marked).
     Carry on in the same session with `--resume <session_id>`, as many messages as you like. A
     message that is new information or the next step is a `prompt`; a message that says "no,
     that is not what I meant" is a `correction`.
  3. Prune the tree with these, and nothing else:
       did accept "as_me graphene plan accept <id>"      [y] it, what is above it and under it
       did drop "as_me graphene node drop <id>"          [d] it, and everything under it
       did edit "as_me graphene node set <id> --title '…' --goal '…' --scope '…' --check '…'"
                                                         [e] one node's contract, any of those
     or [E], the tree as text, changed in your own editing tool and saved back:
       as_me graphene plan --text > "$TMPDIR/before.txt"; cp "$TMPDIR/before.txt" "$TMPDIR/after.txt"
       … change after.txt …
       as_me env EDITOR="cp $TMPDIR/after.txt" graphene plan edit
       log edit --edit "$TMPDIR/before.txt" "$TMPDIR/after.txt"
     A proposal nobody accepts never runs.
  4. did run "as_me graphene run --parallel 4 --with \\"{executor}\\" > \\"\\$TMPDIR/run-1.txt\\" 2>&1"
                                                         [R] four leaves at once, each in its own
     worktree, merged here when the merge is clean (run-2.txt the next time, and so on). Then
     `seen as_me graphene plan --text`.
  5. A leaf that came back: `seen as_me graphene node show <id>` says why, and what it offers:
       did widen "as_me graphene node widen <id>"        [w] its scope, to the paths it wanted
       did sibling "as_me graphene node sibling <id>"    [b] a leaf beside it, for those paths
     Take an offer or not, and run again (step 4).
  6. The change of mind on your card is a follow-up message to the same session, once the first
     part works, and it costs you one of your three corrections. Log it as a `correction` with
     `--mandated`. What it proposes, you prune and run as above.
  7. A finished leaf that is wrong: did reopen "as_me graphene node reopen <id> --note '…'"
     [x], then run again. A reopen is a correction.
  8. Stop when the card is satisfied as far as you can tell, or the budget is gone.""",
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

  Every shell you open, and every script you write, starts with this line:

    source {run}/env.sh

  It puts {venv} first on PATH, sets TMPDIR, goes to the repo, and gives you:

    as_me <command>            run a command as you, the person
    did <type> "<command>"     run a command as you, log the whole line as that act, and
                               what it printed as read
    log <type> [text]          log something you did (the text on stdin when it has quotes)
    seen <command>             run a command, show you what it printed, and log that as read
    reply <file.json>          print what an executor said back, logged as read

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

  printf '%s' "$MSG" | log prompt
  printf '%s' "$MSG" | log correction --mandated
  python3 {here}/logline.py "$R" executor result --from-json "$TMPDIR/e1.json"
  reply "$TMPDIR/e1.json"
  seen git diff {base}

  Read everything through `seen` or `reply`, including a file you open, so what you read is in
  the log; a read is not an act and costs you nothing.

  IMPORTANT: log the FULL text of every command you run as the person and every message you send,
  not an abbreviation of it. If you ran a long `graphene run --with "…"`, the logged text is that
  whole line. Pipe anything with quotes or newlines in it on stdin. Never log a `result` for an
  executor that `graphene run` started: its cost is read out of `.graphene/runs/` and logging it
  as well would count it twice.

THE EXECUTOR — the same command, the same tools, in both arms

  as_me env -u GRAPHENE_AS {by_hand} < /dev/null > "$TMPDIR/e1.json"

  Its `result` field is what it said back; `session_id` is how you carry on:
  `--resume <session_id>` after the other flags. Your message goes straight after `-p` and nowhere
  else: `--allowedTools` takes a list and will eat a prompt that comes after it.

  Three pieces of grit, all found the hard way, all the same for every arm. Write the whole
  invocation — your message in a quoted heredoc, then the command — into one script under
  $TMPDIR and run `bash that-script.sh`: a Bash call that merely contains the string `git` is
  refused here, and a file written in one call is not reliably there in the next. Put the
  message in a file of its own and read it back, `cat > "$TMPDIR/m1.txt" <<'EOF'` … `EOF`, then
  `MSG=$(cat "$TMPDIR/m1.txt")`: this bash (3.2) misreads an apostrophe in a heredoc written
  inside `$( )`, and the script dies before it sends anything. Each executor
  call takes minutes; give the Bash call the longest timeout it takes, and if a call can outlast
  that, run it in the background and wait for it to finish.

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
    if style not in STYLES or arm not in ARMS:
        sys.stderr.write(f"style is one of {', '.join(STYLES)}; arm is one of {', '.join(ARMS)}\n")
        return 2
    base = (run_dir / "base.sha").read_text().strip()
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
            arm=ARMS[arm].format(base=base, executor=EXECUTOR),
            by_hand=BY_HAND,
            card=(HERE / "tasks" / task / "intent.md").read_text(encoding="utf-8"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
