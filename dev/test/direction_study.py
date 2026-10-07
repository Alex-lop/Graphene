#!/usr/bin/env python3
"""The direction study (results-2026-09-29-direction.md): can a person answer "what is waiting on me,
what is running, what is next" faster from the direction than from morning.md?

    dev/test/direction_study.py fixture RUN_DIR direction|morning   build one run's state, just before it
    dev/test/direction_study.py brief RUN_DIR SEAT                  the stand-in's brief for that run
    dev/test/direction_study.py run RUN_DIR -- COMMAND ...          what a stand-in runs: printed and logged
    dev/test/direction_study.py answer RUN_DIR waiting|running|next "id, id"
    dev/test/direction_study.py table RUN_DIR ...                   the registered table and the verdict

Both arms read one state. The direction arm reads it from a repository whose store and
``.graphene/direction.txt`` Graphene's own code built (the plan proposed by a session, accepted,
leaves started and finished, sessions recorded through the hook's own ``ingest_hook_event``); the
morning arm reads ``morning.md``, the brief of the same state, written to the brief's contract.
The running sessions' last calls are stamped 15 minutes after the build, so they read running for
a run's length; a run starts within 5 minutes of its build.

Every command a stand-in runs goes through ``run``, which refuses what its arm does not allow, and
logs the characters typed and the words printed. Everything printed counts as read, in both arms.
The model is attention.py's: K s a typed character, M s an act (a command), reading at WPM.
"""

from __future__ import annotations

import json
import os
import shlex
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from attention import WPM, K, M  # noqa: E402
from direction_key import KEY  # noqa: E402  (not in the file the brief names)

SEATS = {
    "first": "a first-time user. You installed Graphene yesterday; you know from its README what a plan, "
    "a leaf, a session and the direction are, and nothing more",
    "alex": "Alex, who built Graphene. You know its commands and its words, and you want the answers in "
    "as few looks as you can",
    "judge": "a hackathon judge. You have a few minutes for this repository, and you take nothing on "
    "trust that the screen does not say",
}
ALLOWED = {
    "direction": "graphene direction (with --width N if you like), graphene plan, graphene board, "
    "graphene watch --once, each run in the repository",
    "morning": "cat, head, sed -n and grep, each on morning.md",
}
S1, S2, S3, S4 = (
    "5a1e0c3b-0000-4000-8000-000000000001",
    "b7c24d1e-0000-4000-8000-000000000002",
    "c3d4e5f6-0000-4000-8000-000000000003",
    "d9e8f7a6-0000-4000-8000-000000000004",
)
HELPER = "a1b2c3d4e5f6a7b8"
UNMARK = (
    "CLAUDECODE",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_ENTRYPOINT",
    "AI_AGENT",
    "GRAPHENE_NODE",
    "GRAPHENE_PLANNER",
)  # newrun.sh's list
DIRECTION = """\
- invoices that get paid on time  [invoices]
    customers see, download and pay what they owe
  - customers download their invoices as PDF  [pdf]
  - billing runs itself every month  [billing]
  ? a mobile view of the invoices  [mobile]
  - the old CSV export goes away  [csv-sunset]
"""
PLAN = """\
goal: customers download their invoices as PDF
question: A4 or US Letter by default?  [q-paper]
    default: A4
    option: US Letter
- embed the fonts  [fonts]
    scope: src/fonts.py
    check: true
- render one invoice to PDF bytes  [render]
    scope: src/render.py
    check: true
    signoff: yes
    needs: fonts
- the invoice template  [template]
    scope: templates/invoice.html
    check: true
- a download button on the invoice page  [download]
    scope: src/download.py
    check: true
    needs: render
- attach the PDF to the monthly email  [email]
    scope: src/email.py
    check: true
"""
MORNING = """\
# morning.md — the invoices run

## The brief

**Watch first**
- Nothing to watch this run: no recording was made.

**What ran** — no live calls, $0.00
- The PDF plan (customers download their invoices as PDF): 1 of 5 leaves done (fonts).
- render passed its check and stops in review for your sign-off (`graphene node signoff render`).

**New tonight**
- template, the invoice template, is being built now by session 5a1e0c3b.
- Session c3d4e5f6 is making the monthly billing job idempotent, with its subagent a1b2c3d4 writing
  the job's docs. Both are working now.

**Decide**
1. A4 or US Letter by default? It is q-paper on the board; my default is A4 (`graphene board`).
2. Sign off render, or send it back.
3. The direction has a new proposal, mobile (a mobile view of the invoices): accept it or drop it.

**Broken or risky**
- Session b7c24d1e (the flaky billing test) stopped and waits for your answer.
- Session d9e8f7a6 (the invoice list on a phone) has done nothing for 20 minutes.

---

(Everything below the brief: what was decided, the evidence, the state of every branch.)

## What was decided

- The PDF plan hangs from pdf (customers download their invoices as PDF) in the direction; the
  billing sessions, b7c24d1e and c3d4e5f6, are attached to billing (billing runs itself every
  month).
- fonts was finished first because render needs it; its check passed at the boundary.
- The download button (download) waits on render, so it cannot start until you sign render off.

## What comes next

- email, attaching the PDF to the monthly email, is ready: it is the leaf `graphene run` starts
  next. download follows once render is signed off.
- csv-sunset (the old CSV export goes away) has no plan yet.

## Evidence

- fonts: done, its check `true` passed; the change is in src/fonts.py.
- render: review, its check `true` passed; the change is in src/render.py.
- template: running, held by session 5a1e0c3b, writing templates/invoice.html.
- The sessions are read from what the hooks recorded; an older session, quiet for two days, is not
  listed.

## Branches

- One checkout, on its default branch, with the finished leaves committed.
"""


def _stamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _graphene() -> list[str]:
    return [str(Path(sys.executable).parent / "graphene")]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=s@example.com", "-c", "user.name=S", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def build_direction(repo: Path, now: datetime) -> None:
    """The state, made by Graphene's own code paths, stamped around ``now``."""
    from graphene_map import direction as D
    from graphene_map import plan as P
    from graphene_map.hooks import ingest_hook_event
    from graphene_map.store import Store

    alex, s1 = P.Caller("alex", True), P.Caller("claude:5a1e0c3b", False, S1)
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    for path in (
        "src/fonts.py",
        "src/render.py",
        "src/download.py",
        "src/email.py",
        "templates/invoice.html",
    ):
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("")
    (repo / "README.md").write_text("invoices\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "start")
    with Store.open(repo) as store:
        D.write(repo, D.parse(DIRECTION))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEBIUS_", "GRAPHENE_AS"))}
    env |= {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": S1}
    said = subprocess.run(
        [*_graphene(), "plan", "propose", "-"], cwd=repo, input=PLAN, env=env, capture_output=True, text=True
    )
    assert said.returncode == 0, said.stderr
    with Store.open(repo) as store:
        P.accept(store, [], alex)
        for leaf in ("fonts", "render"):
            P.start(store, leaf, s1, repo)
            (repo / f"src/{leaf}.py").write_text(f"# {leaf}\n")
            P.finish(store, leaf, s1, checkout=repo)
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", leaf)
        P.start(store, "template", s1, repo)
        d = D.read(repo)
        D.hang(store, d, "pdf", alex)

        def event(name: str, sid: str, at: datetime, **more) -> None:
            ingest_hook_event(store, {"hook_event_name": name, "session_id": sid, **more}, repo, _stamp(at))

        ahead = now + timedelta(minutes=15)
        event(
            "UserPromptSubmit", S1, now - timedelta(minutes=29), prompt="take the next leaf of the PDF plan"
        )
        event(
            "PostToolUse",
            S1,
            ahead,
            tool_name="Edit",
            tool_input={"file_path": str(repo / "templates/invoice.html")},
        )
        event("UserPromptSubmit", S2, now - timedelta(minutes=10), prompt="fix the flaky billing test")
        event(
            "PostToolUse",
            S2,
            now - timedelta(minutes=5),
            tool_name="Bash",
            tool_input={"command": "pytest tests/billing -q", "description": "Run the billing tests"},
        )
        event("Stop", S2, now - timedelta(minutes=4))
        event(
            "UserPromptSubmit",
            S3,
            now - timedelta(minutes=8),
            prompt="make the monthly billing job idempotent",
        )
        event(
            "PostToolUse",
            S3,
            now - timedelta(minutes=6),
            tool_name="Agent",
            tool_use_id="spawn",
            tool_input={"description": "docs for the billing job"},
            tool_response={"agentId": HELPER},
        )
        event("SubagentStart", S3, now - timedelta(minutes=6), agent_id=HELPER)
        event(
            "PostToolUse",
            S3,
            ahead,
            tool_name="Edit",
            agent_id=HELPER,
            tool_input={"file_path": str(repo / "docs/billing.md")},
        )
        event(
            "PostToolUse",
            S3,
            ahead,
            tool_name="Bash",
            tool_input={"command": "python -m billing --twice", "description": "Run the billing job twice"},
        )
        event(
            "UserPromptSubmit", S4, now - timedelta(minutes=25), prompt="look at the invoice list on a phone"
        )
        event(
            "PostToolUse",
            S4,
            now - timedelta(minutes=20),
            tool_name="Read",
            tool_input={"file_path": str(repo / "templates/invoice.html")},
        )
        event(
            "UserPromptSubmit", "e1e2e3e4-0000-4000-8000-000000000005", now - timedelta(days=2), prompt="old"
        )
        for sid in (S2, S3):
            D.attach(store, d, sid[:8], "billing", alex)


def fixture(run_dir: Path, arm: str) -> None:
    run_dir.mkdir(parents=True)
    now = datetime.now(UTC)
    if arm == "direction":
        build_direction(run_dir / "repo", now)
    else:
        (run_dir / "morning.md").write_text(MORNING, encoding="utf-8")
    (run_dir / "arm.json").write_text(json.dumps({"arm": arm, "built": _stamp(now)}))


def brief(run_dir: Path, seat: str) -> str:
    run_dir = run_dir.resolve()
    arm = json.loads((run_dir / "arm.json").read_text())["arm"]
    me = f"{sys.executable} {Path(__file__).resolve()}"
    where = (
        f"The repository is {run_dir / 'repo'}."
        if arm == "direction"
        else f"The brief is {run_dir / 'morning.md'}."
    )
    return f"""\
You are standing in for {SEATS[seat]}.

You have just sat down at your machine. Answer three questions about the state of the work, the way
this person would, reading only what you need to:
  1. waiting: what is waiting on you?
  2. running: what is running?
  3. next: what is next (the work that starts next)?
Each answer is a list of ids: a node's or a leaf's id, a board item's id, or a session's or a
subagent's 8-character id, as the text you read names them.

{where} The commands you may run: {ALLOWED[arm]}.
Every command goes through this, which prints what the command printed (all you may read) and logs it:
  {me} run {run_dir} -- <command>
Open no file yourself, this command's own script included, and read nothing in {run_dir} any
other way. When you know an answer, log it:
  {me} answer {run_dir} waiting "id, id, ..."
  {me} answer {run_dir} running "id, ..."
  {me} answer {run_dir} next "id"
Then stop. Say in one line what, if anything, was hard to find.
"""


# the read forms of the direction arm: each command, and the only flags it may carry (with how many
# values each takes). Nothing that writes: no subcommand, so no accept, drop, edit or attach
READS = {
    ("graphene", "direction"): {"--width": 1, "--text": 0, "--json": 0},
    ("graphene", "plan"): {"--view": 1, "--width": 1, "--height": 1, "--all": 0, "--text": 0, "--json": 0},
    ("graphene", "board"): {},
    ("graphene", "watch"): {"--once": 0, "--all": 0},
}


def _allowed(run_dir: Path, arm: str, argv: list[str]) -> bool:
    """Only a read of the arm's own material: the direction arm's graphene reads (watch only with
    --once), the morning arm's cat, head, sed -n and grep of morning.md and of no other file."""
    if arm == "morning":
        rest = argv[1:-1]
        other_file = any("/" in a or a.endswith(".md") or (run_dir / a).exists() for a in rest)
        verb = argv[:1] in (["cat"], ["head"], ["sed"], ["grep"]) and (argv[0] != "sed" or "-n" in rest)
        return verb and argv[-1] == "morning.md" and not other_file
    flags = READS.get(tuple(argv[:2]))
    if flags is None or (argv[1] == "watch" and "--once" not in argv):
        return False
    k = 2
    while k < len(argv):
        if argv[k] not in flags:
            return False
        k += 1 + flags[argv[k]]
    return k == len(argv)


def run(run_dir: Path, argv: list[str]) -> int:
    arm = json.loads((run_dir / "arm.json").read_text())["arm"]
    ok = _allowed(run_dir, arm, argv)
    if arm == "direction":
        cwd, argv = run_dir / "repo", [*_graphene(), *argv[1:]] if ok else argv
    else:
        cwd = run_dir
    typed = len(shlex.join(["graphene", *argv[1:]] if arm == "direction" and ok else argv))
    if ok:  # in the person's seat, as newrun.sh's as_me runs a stand-in's commands
        env = {k: v for k, v in os.environ.items() if not k.startswith("NEBIUS_") and k not in UNMARK}
        env |= {"GRAPHENE_AS": "person:alex"}
        env |= {"COLUMNS": env.get("COLUMNS", "100"), "LINES": env.get("LINES", "40")}
        said = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, env=env)
        shown = said.stdout + said.stderr
    else:
        shown = f"refused in this arm: the commands you may run are {ALLOWED[arm]}\n"
    sys.stdout.write(shown)
    _log(run_dir, {"act": "command", "typed": typed, "words": len(shown.split()) if ok else 0, "allowed": ok})
    return 0


def _log(run_dir: Path, row: dict) -> None:
    with open(run_dir / "runlog.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), **row}) + "\n")


def answer(run_dir: Path, question: str, ids: str) -> int:
    if question not in KEY:
        sys.exit(f"the questions are {', '.join(KEY)}")
    _log(
        run_dir,
        {
            "act": "answer",
            "question": question,
            "ids": [i.strip(" []`") for i in ids.split(",") if i.strip()],
        },
    )
    return 0


def score(run_dir: Path) -> dict:
    rows = [json.loads(line) for line in (run_dir / "runlog.jsonl").read_text().splitlines() if line.strip()]
    commands = [r for r in rows if r["act"] == "command"]
    answers = {r["question"]: [i.lower()[:8] for i in r["ids"]] for r in rows if r["act"] == "answer"}
    right = false = 0
    for question, items in KEY.items():
        said = answers.get(question, [])
        right += sum(any(i[:8] in said for i in item) for item in items)
        false += sum(all(a != i[:8] for item in items for i in item) for a in said)
    typed, words = sum(c["typed"] for c in commands), sum(c["words"] for c in commands)
    seconds = K * typed + M * len(commands) + words / WPM * 60
    return {
        "arm": json.loads((run_dir / "arm.json").read_text())["arm"],
        "run": run_dir.name,
        "typed": typed,
        "acts": len(commands),
        "words": words,
        "seconds": round(seconds, 1),
        "right": right,
        "false": false,
        "answered": len(answers),
    }


def table(run_dirs: list[Path]) -> str:
    runs = [score(d) for d in run_dirs]
    of = sum(len(v) for v in KEY.values())
    out = [
        "| run | arm | person-s, MODELLED | typed | acts | words read | right (of 8) | false | answered |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    out += [
        f"| {r['run']} | {r['arm']} | {r['seconds']} | {r['typed']} | {r['acts']} | {r['words']} "
        f"| {r['right']} | {r['false']} | {r['answered']}/3 |"
        for r in runs
    ]
    arms = {a: [r for r in runs if r["arm"] == a] for a in ("direction", "morning")}
    out += [
        "",
        "| arm | n | median person-s | median words read | mean right (of 8) | mean false |",
        "|---|---|---|---|---|---|",
    ]
    for a, rs in arms.items():
        if rs:
            out.append(
                f"| {a} | {len(rs)} | {statistics.median(r['seconds'] for r in rs)} | "
                f"{statistics.median(r['words'] for r in rs)} | "
                f"{statistics.mean(r['right'] for r in rs):.2f} | "
                f"{statistics.mean(r['false'] for r in rs):.2f} |"
            )
    if all(arms.values()):
        d, m = arms["direction"], arms["morning"]
        faster = statistics.median(r["seconds"] for r in d) < statistics.median(r["seconds"] for r in m)
        as_right = statistics.mean(r["right"] for r in d) >= statistics.mean(r["right"] for r in m)
        verdict = (
            "the direction answered faster, as correctly"
            if faster and as_right
            else "no advantage shown for the direction"
            if not faster
            else "the direction was faster but less correct: no advantage shown"
        )
        out += ["", f"By the registered rule ({of} items): {verdict}."]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.exit(__doc__)
    what, run_dir = argv[1], Path(argv[2])
    if what == "fixture":
        fixture(run_dir, argv[3])
    elif what == "brief":
        print(brief(run_dir, argv[3]))
    elif what == "run":
        return run(run_dir, argv[argv.index("--") + 1 :] if "--" in argv else argv[3:])
    elif what == "answer":
        return answer(run_dir, argv[3], argv[4])
    elif what == "table":
        print(table([Path(a) for a in argv[2:]]))
    else:
        sys.exit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
