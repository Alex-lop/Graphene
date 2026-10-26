"""`graphene auto`: from a goal to tested commits inside the envelope the person set once.

The envelope is the person's settings (settings.py): `auto: on`, a `budget` in dollars, how many `tasks` it
may accept for them and how many fix `rounds` it may take, with the standing protected/readonly/never/forks/
review settings. ``fits`` says why a proposal waits for the person; ``take`` accepts one that fits, as the
person's stand-in, so `graphene plan undo` takes it back. ``drive`` is the command: the planner drafts the
tree under a root sub-goal that carries the goal's check, Graphene accepts what fits, runs it with forks,
lands what its check passes, then the root's own check runs (`plan.roll_up`); when that is red the planner
proposes the fix under the root, for at most settings.rounds rounds. Each stage is a node_log row of kind
KIND on "*", whose detail is what ``state`` returns.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import board as B
from . import plan as P
from . import settings as S

KIND = "auto"  # node_log kind of a round's progress, actor "graphene auto"
ACTOR = "graphene auto"
STAGES = ("planning", "running", "checking", "fixing", "done", "waits")
TASKS = 12  # tasks the envelope accepts for the person when `tasks:` is unset and auto is on
WAITS = "waits for you: "  # how every reason a proposal is not taken begins
# where the agents' own settings and hooks live, and the CI that runs with the repo's secrets: a held task
# whose scope names one may write it (the hooks' settings are written so on purpose), so only the person
# accepts it
GUARDED = (".claude/", ".codex/", ".cursor/", ".gemini/", ".github/workflows/")


def state(store) -> dict | None:
    """The newest round's progress, or None when `graphene auto` never ran on this plan: a dict with
    round (1 is the first plan), rounds (the most fix rounds), stage (one of STAGES), spent and budget
    (dollars, budget None when unset), check ("pass", "fail" or None while not yet run) and why (a line
    for the person when stage is waits; while fixing, the line the goal's check failed on; else "")."""
    rows = store.node_log("*", (KIND,))
    return dict(rows[-1]["detail"]) if rows else None


def log(store, k: int, stage: str, spent: float, budget: float | None, check: str | None = None,
        why: str = "", **more) -> dict:  # fmt: skip
    """One row of the round's progress, in the shape ``state`` returns (``more``: root, goal), with a ``note``
    `graphene plan log` and the record show: "round 2: fixing · $0.0400 of $2.00 · the goal's check: fail"."""
    note = f"round {k}: {stage} · ${spent:.4f}" + (f" of ${budget:.2f}" if budget is not None else "")
    note += f" · the goal's check: {check}" if check else ""
    detail = {"round": k, "rounds": S.rounds(store), "stage": stage, "spent": round(spent, 4),
              "budget": budget, "check": check, "why": why, "note": note, **more}  # fmt: skip
    store.log_node("*", P._now(), KIND, ACTOR, None, None, detail)
    return detail


def spent(store, since: str) -> float:
    """Dollars the agents' usage rows say since ``since``, as `graphene run --max-usd` counts them."""
    return sum((r["detail"] or {}).get("dollars") or 0
               for r in store.node_log(None, ("usage",)) if r["timestamp"] >= since)  # fmt: skip


def accepted(store, since: str) -> int:
    """How many tasks the envelope accepted for the person since auto went on (a sub-goal is no task)."""
    under = P.kids(P.nodes(store), drawn=True)
    rows = store.node_log(None, ("accepted",))
    return len({r["node_id"] for r in rows if (r["detail"] or {}).get("by") == "auto"
                and r["timestamp"] >= since and not under.get(r["node_id"])})  # fmt: skip


def envelope(store) -> str:
    """The envelope in a few words: 'auto on since 00:31 · $2.00 · 12 tasks'."""
    at = S.auto_since(store)
    when = ""
    if at:
        when = f" since {datetime.fromisoformat(at.replace('Z', '+00:00')).astimezone().strftime('%H:%M')}"
    budget = S.budget(store)
    dollars = f"${budget:.2f}" if budget is not None else "no budget"
    return f"auto on{when} · {dollars} · {S.tasks(store) or TASKS} tasks"


def width(nodes: list[P.Node], files: list[str]) -> int:
    """How many ready leaves can run at once: each counts when its scope can meet none counted before it,
    the rule `graphene run` starts them by (one writer a path)."""
    chosen: list[P.Node] = []
    for n in P.ready(nodes, P.Caller("agent", False)):
        if not any(P.may_collide(n.scope, o.scope) or P.overlap(n.scope, o.scope, files) for o in chosen):
            chosen.append(n)
    return len(chosen)


def runs_as_check(check: str, allowed: list[str]) -> bool:
    """Whether the envelope runs ``check`` without the person reading it: one command (no `;`, `&&`, `||`,
    `|`, redirect, `$(…)` or backtick outside quotes), and, once `checks:` names commands, one of them, alone
    or with more words after it. A planner's check is code the person's machine runs."""
    if "`" in check or "$(" in check or "\n" in check:
        return False
    try:
        lex = shlex.shlex(check, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:  # an unclosed quote: not a command the person would take as read
        return False
    if not words or any(set(w) <= set("();<>|&") for w in words):
        return False
    said, named = " ".join(check.split()), [" ".join(c.split()) for c in allowed]
    return not named or any(said == a or said.startswith(a + " ") for a in named)


def fits(store, added: list[P.Node], files: list[str]) -> list[str]:
    """Why these proposals wait for the person, a reason each; empty: they fit the envelope. They fit when
    auto is on; every new task has a scope and a check (a sign-off alone is the person's); the tasks the
    envelope accepted since auto went on plus these stay within `tasks`; nothing on the board waits for the
    person (a question with no default, an executor's note, a default that drops a task); none of them
    splits a task someone holds; and no scope reaches GUARDED (a task that could rewrite the hooks that hold
    it). `review: every` still holds each proven task for the sign-off."""
    if S.auto(store) != "on":
        return ["auto is off (`graphene config set auto on`, or `graphene auto`, turns it on)"]
    everything = P.nodes(store)
    by_id, under = {n.id: n for n in everything}, P.kids(everything, drawn=True)
    new = [n for n in added if n.state == P.PROPOSED]
    leaves = [n for n in new if not under.get(n.id)]
    why = [f"{n.id} has no scope" for n in leaves if not n.scope]
    why += [f"{n.id} has no check" for n in leaves if n.scope and not n.check]
    allowed = S.checks(store)
    runs = f"one of {', '.join(' '.join(c.split()) for c in allowed)}" if allowed else "one plain command"
    for n in leaves:
        if n.check and not runs_as_check(n.check, allowed):
            why.insert(0, f"{n.id}'s check is not one your envelope runs ({runs}, `checks:` in graphene "
                          f"config): `{n.check[:60]}`; you read it and accept it yourself")  # fmt: skip
        if hit := next((g for g in GUARDED if P.may_collide(n.scope, [f"{g}**"])), None):
            why.insert(0, f"{n.id}'s scope reaches {hit}, where the agents' own settings and hooks live "
                          "(or the CI that runs with your secrets): you accept that yourself")  # fmt: skip
    most, had = S.tasks(store) or TASKS, accepted(store, S.auto_since(store) or "")
    if had + len(leaves) > most:
        why.append(f"your envelope accepts {most} tasks and this makes {had + len(leaves)}")
    for it in [it for it in B.items(store) if B.reads(it) == "open" and not B.has_default(it)]:
        drops = B.drops(it)
        said = f"its default drops {', '.join(drops)}" if drops else "it has no default"
        why.append(f"{it['id']} on the board needs your answer: {said}")
    for n in new:
        parent = by_id.get(n.parent or "")
        if parent is not None and parent.state == P.RUNNING:
            why.append(f"{n.id} would split {parent.id}, which {parent.executor} holds")
    return why


def take(store, added: list[P.Node], files: list[str], root: Path, round: int | None = None) -> str | None:
    """Accept the proposals that fit the envelope as the person's stand-in, the way a one-line ask is
    (`plan undo` takes it back; the board's defaults are taken as at a whole-plan accept), and return the
    line to print: what was accepted and under which envelope, or the one reason it waits (WAITS). None
    while auto is off: the proposal waits as any does. ``round``: `graphene auto`'s round, else the one
    going (``state``), on each `accepted` row as `round`."""
    if S.auto(store) != "on":
        return None
    why = fits(store, added, files)
    if why:
        more = f" (and {len(why) - 1} more: `graphene board`, `graphene plan`)" if len(why) > 1 else ""
        return f"{WAITS}{why[0]}{more}"
    if round is None:
        going = state(store)
        round = going["round"] if going and going["stage"] in ("planning", "fixing") else None
    me = P.Caller(P.person_name(), True, None, stand_in=True)
    new = {n.id for n in added if n.state == P.PROPOSED}
    tops = [n.id for n in added if n.id in new and n.parent not in new]
    told: list[str] = []
    detail = {"by": "auto", **({"round": round} if round is not None else {})}
    try:
        with P.undoable(store, me, f"accepted inside your envelope: {', '.join(tops)[:40]}"):
            chosen = P.accept(store, tops, me, files=files, told=told, **detail)
            took = B.took(B.defaults(store, me, files, told), B.left(store))
    except P.Refused as no:
        return f"{WAITS}{no}"
    everything = P.nodes(store)
    under = P.kids(everything, drawn=True)
    leaves = [n.id for n in chosen if not under.get(n.id)]
    wide = width(everything, files)
    lines = [f"accepted inside your envelope ({envelope(store)}): {', '.join(leaves)}. `graphene run` runs "
             f"them; {wide} task{'s' if wide != 1 else ''} can run at once"]  # fmt: skip
    lines += [took] if took else []
    return "\n".join([*lines, *told])


# -- the command ---------------------------------------------------------------------------------------


def metering(template: str) -> str:
    """How the executor's cost is known: "stream" (Claude Code, Codex: the run's --max-usd holds each
    attempt's worst case), "rows" (Nemotron bills each call after it ends: the budget is read between
    rounds), or "none" (a plain command reports no cost: attempts are counted instead)."""
    import shlex

    from . import meter as M
    from .run import label

    argv = shlex.split(template)
    return "stream" if M.kind(argv) else "rows" if label(template) == "nemotron" else "none"


def run_cap(store, template: str, given: float | None) -> tuple[float | None, str]:
    """What any run may start while auto is on (an agent's `graphene run` after its plan was taken, the
    cockpit's `R`): the envelope's budget left, as `--max-usd`, for an executor whose stream says what it
    spent (Claude Code, Codex); for one billed after each call (Nemotron) or with no meter, the budget is
    read before the run only. Refused, with what to do, once it is spent. Returns the cap and the line to
    say, or (``given``, "") while auto is off or has no budget."""
    budget = S.budget(store)
    if S.auto(store) != "on" or budget is None:
        return given, ""
    paid = spent(store, S.auto_since(store) or "")
    left = budget - paid
    if left <= 0:
        raise P.Refused(f"nothing starts: your envelope's budget is spent (${paid:.2f} of ${budget:.2f}); "
                        "`graphene config set budget N` widens it")  # fmt: skip
    if metering(template) != "stream":
        return given, f"your envelope's budget: ${left:.2f} of ${budget:.2f} left, read before this run"
    cap = left if given is None else min(given, left)
    return cap, f"your envelope's budget: ${left:.2f} of ${budget:.2f} left; this run starts nothing past it"


def goal_check(store, root_id: str, own: str | None) -> str:
    """The root's check: the goal's own (--check), else every task's check under it run together, in the
    plan's order (what passes alone and breaks together is caught here)."""
    if own:
        return own
    everything = P.nodes(store)
    under = P.kids(everything, drawn=True)
    leaves = [n for n in P.order(P.below(root_id, everything)) if n.check and not under.get(n.id)
              and n.state not in P.GONE]  # fmt: skip
    return " && ".join(f"( {n.check} )" for n in leaves)


def _failing(output: str) -> str:
    """The line of a red check's tail that says what failed: the first that names a failing test (unittest's
    `FAIL: test_x (…)`, pytest's `FAILED tests/…::test_x`), else the last that names an error or a failure
    (Python's `AssertionError`), else the last line. ponytail: a word match, not a parser per test runner."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    named = [line for line in lines if re.match(r"(?:FAIL|ERROR): |FAILED \S", line)]
    if named:  # unittest's `FAIL: test_x (tests.test_y.TestY.test_x)`: the test's name says it
        return re.sub(r"^((?:FAIL|ERROR): \S+) \([\w.]+\)$", r"\1", named[0])[:200]
    said = [line for line in lines if re.search(r"Error|FAILED|failed|assert", line)]
    return (said or lines or ["no output"])[-1][:200]


def _ended(store, since: str, k: int, verdict: str) -> str:
    """The last line: rounds, tasks landed, came back, forks raced, dollars, the goal's check."""
    rows = [r for r in store.node_log() if r["timestamp"] >= since]
    landed = {r["node_id"] for r in rows if r["kind"] == "landed"}
    back = {r["node_id"] for r in rows if r["kind"] == "released"
            and not (r["detail"] or {}).get("person") and not (r["detail"] or {}).get("stopped")}  # fmt: skip
    forks = sum(len((r["detail"] or {}).get("forks") or []) for r in rows if r["kind"] == "forked")
    tries = sum(1 for r in rows if r["kind"] == "attempt")
    usage = any(r["kind"] == "usage" for r in rows)
    cost = f"{tries} attempt{'s' * (tries != 1)}, no meter"
    cost = f"${spent(store, since):.4f} at list price" if usage else cost
    return (f"auto: {k} round{'s' * (k != 1)}, {len(landed)} task{'s' * (len(landed) != 1)} landed, "
            f"{len(back)} came back, {forks} fork{'s' * (forks != 1)} raced, {cost}; the goal's check "
            f"{verdict}. `graphene plan log` has the whole history")  # fmt: skip


def drive(open_store: Callable, root: Path, goal: str | None, say: Callable[[str], None], planner: str | None,
          withs: list[str], parallel: int, forks: int | None, check: str | None, attempts: int,
          plan_only: bool = False) -> int:
    """`graphene auto`'s rounds, as the person (the command is theirs). Returns the exit code: 0 the goal's
    check passed; 1 it is still red after the rounds, the budget is spent, or the run was stopped; 3 something
    waits for the person (a proposal outside the envelope, a sign-off, a planner that proposed nothing)."""
    from . import plan_text as T
    from .ask import ask, named, talking
    from .run import Forks, run_parallel, summary
    from .run import named as executor_named

    me = P.caller()
    P._person_only(me, "`graphene auto`")
    with open_store(root) as store:
        at = S.auto_since(store) or ""
        budget, rounds = S.budget(store), S.rounds(store)
        files = P.tracked(root)
        spec = planner or store.meta("planner")
        template = named(spec)  # refused with what to do when none is chosen
        executor = executor_named(withs[0] if withs else store.meta("executor"))
        how = metering(executor)
        going = state(store)
        if goal is None:  # go on with the plan in force: the next round
            root_row = store.node_row(going["root"]) if going and going.get("root") else None
            if root_row is None or root_row.get("state") in P.GONE:
                raise P.Refused("no goal is in force for `graphene auto` here: graphene auto '<what you "
                                "want>' starts one")  # fmt: skip
            root_id, goal = going["root"], P.goal(store)
            k = going["round"] + (0 if going.get("planned") else 1)  # a round planned with --plan runs now
            check = check or store.meta("auto:check")  # the goal's own check, as the person first gave it
        else:
            was = P.goal(store)
            open_ = [n for n in P.nodes(store) if n.state in (P.PROPOSED, P.OPEN, P.RUNNING, P.REVIEW)]
            same = going and going.get("goal") == goal and going.get("root") in {n.id for n in open_}
            if was and was != goal and open_ and not same:
                raise P.Refused(
                    f"the plan here is for another goal ({was!r}) and {len(open_)} of its nodes are still "
                    "open: `graphene auto` with no goal goes on with it; `graphene plan archive` ends it"
                )
            if same:
                root_id, k = going["root"], going["round"] + (0 if going.get("planned") else 1)
                check = check or store.meta("auto:check")
            else:
                if was != goal:
                    P.set_goal(store, goal, me)
                root_id = T.slug(goal, {n.id for n in P.nodes(store)}, "goal")
                store.set_meta("auto:check", check)  # a new goal: its own check, or none (every task's)
                P.propose(store, [{"id": root_id, "title": goal}], me, files=files)  # the root: open, bare
                k = 1
        # this goal's own rows, for the last line: the budget counts from auto on, the summary from the goal
        rows = store.node_log("*", (KIND,))
        mine = [r["timestamp"] for r in rows if (r["detail"] or {}).get("root") == root_id]
        began_goal = mine[0] if mine else P._now()
        lines = [f"envelope: {envelope(store)} · {rounds} fix round{'s' * (rounds != 1)}"
                 f" · {forks or S.forks(store)} fork{'s' * ((forks or S.forks(store)) != 1)} a task"
                 f" · {parallel} at once"]  # fmt: skip
        if budget is not None and how == "rows":
            lines.append("nemotron bills each call after it ends: the budget is read between rounds")
        if budget is not None and how == "none":
            lines.append("this executor reports no cost, so the budget cannot hold it: attempts are counted")
        lines.append("`graphene watch` in another terminal follows it; Ctrl-C here stops it")
        for line in lines:
            say(line)
        logs = root / ".graphene" / "runs"
        verdict: str | None = None
        red: str | None = None  # the goal check's last verdict, on every row until it passes
        fix: tuple[str, str] | None = None  # the red check's command and tail, for the next round's planner
        back: list[P.Node] = []
        planned = bool(going and going.get("planned") and going.get("root") == root_id)  # by --plan, to run
        unplanned = not [n for n in P.below(root_id, P.nodes(store))
                         if n.id != root_id and n.state not in P.GONE]  # fmt: skip
        if unplanned and going and going.get("root") == root_id:  # its planner failed or was stopped: again
            k, planned = going["round"], False
        try:
            while True:
                paid = spent(store, at)
                if (k == 1 and not planned) or unplanned or fix or back:
                    stage = "planning" if k == 1 else "fixing"
                    said = _failing(fix[1]) if fix and stage == "fixing" else ""  # what the fix is for
                    log(store, k, stage, paid, budget, red, said, root=root_id, goal=goal)
                    say(f"round {k}: " + ("planning" if k == 1 else "planning the fix"))
                    # the whole tree (round 1); the fix for a red goal check, under the root; and what to do
                    # about each task that came back, beside it (the next run takes them again)
                    asks = [(goal, None, None)] if k == 1 else []
                    if fix:
                        talk = talking(store, "fix", [root_id], command=fix[0], output=fix[1])
                        asks.append((goal, root_id, talk))
                    asks += [(f"{n.id} came back", n.id, None) for n in back]
                    for sentence, about, talk in asks:
                        try:
                            for line in ask(store, root, sentence, template, about, say=say, talk=talk,
                                            planner=spec, base_parent=root_id):  # fmt: skip
                                say(line)
                        except P.Refused as no:
                            # a planner that could not work at all (exit 3: no key, a cap) says why, alone
                            cannot = re.search(r"\(exit 3\): stopped: (.+)", str(no))
                            why = (f"the planner could not start: {cannot.group(1)}" if cannot
                                   else f"the planner proposed nothing: {no}")  # fmt: skip
                            paid = spent(store, at)
                            log(store, k, "waits", paid, budget, red, why, root=root_id, goal=goal)
                            say(f"{WAITS}{why}")
                            return 3
                    fix, back = None, []
                    pending = P.nodes(store, (P.PROPOSED,))
                    if pending:
                        why = (fits(store, pending, files) or ["a proposal waits for your accept"])[0]
                        log(store, k, "waits", spent(store, at), budget, red, why, root=root_id, goal=goal)
                        say(f"{WAITS}{why}. `graphene watch` shows it; `graphene auto` goes on once you have")
                        return 3
                    want = goal_check(store, root_id, check)
                    if want and P.get(store, root_id).check != want:
                        P.edit(store, root_id, {"check": want}, me, files=files)
                    if plan_only:  # the cautious first try: the tree is in, nothing runs until auto goes on
                        why = "planned with --plan: `graphene auto` runs it"
                        log(store, k, "waits", spent(store, at), budget, red, why, root=root_id, goal=goal,
                            planned=True)  # fmt: skip
                        say(f"auto: planned round {k} inside your envelope and ran nothing: `graphene plan` "
                            "shows it, `graphene auto` runs it")  # fmt: skip
                        return 0
                planned = unplanned = False
                paid = spent(store, at)
                if budget is not None and paid >= budget:
                    why = f"the budget is spent: ${paid:.4f} of ${budget:.2f}"
                    log(store, k, "waits", paid, budget, red, why, root=root_id, goal=goal)
                    say(f"{WAITS}{why}; `graphene config set budget N` widens it")
                    return 1
                log(store, k, "running", paid, budget, red, root=root_id, goal=goal)
                began, since = P._now(), len(store.node_log())
                cap = max(0.0, budget - paid) if budget is not None and how == "stream" else None
                raced = Forks(forks or 0, False, list(withs))
                try:  # named the root: its leaves, the ones that came back too (a run not told leaves them)
                    run_parallel(lambda: open_store(root), root, root, max(parallel, 1), executor, attempts,
                                 [root_id], say, logs, True, cap, raced)  # fmt: skip
                except KeyboardInterrupt:
                    say(summary(store, since, stopped=True))
                    why = "stopped by you: what was running went back to the plan; `graphene auto` goes on"
                    log(store, k, "waits", spent(store, at), budget, red, why, root=root_id, goal=goal)
                    say(f"auto {why}")
                    return 1
                say(summary(store, since))
                paid = spent(store, at)
                log(store, k, "checking", paid, budget, red, root=root_id, goal=goal)
                everything = P.nodes(store)
                under = P.kids(everything, drawn=True)
                leaves = [n for n in P.below(root_id, everything)
                          if n.state not in P.GONE and not under.get(n.id)]  # fmt: skip
                back = [n for n in leaves if P.came_back(store, n)]
                review = [n.id for n in leaves if n.state == P.REVIEW]
                if review:
                    why = (f"{', '.join(review)} passed and wait for your sign-off (review: every): "
                           "`graphene node signoff ID` lands each, then `graphene auto` goes on")  # fmt: skip
                    log(store, k, "waits", paid, budget, red, why, root=root_id, goal=goal)
                    say(f"{WAITS}{why}")
                    return 3
                if P.get(store, root_id).state == P.DONE and leaves:
                    log(store, k, "done", paid, budget, "pass", root=root_id, goal=goal)
                    say(_ended(store, began_goal, k, "passed"))
                    return 0
                failed = [r for r in store.node_log(root_id, ("check_failed",)) if r["timestamp"] >= began]
                if failed:
                    out = failed[-1]["detail"].get("output", "")
                    first = _failing(out)
                    fix, verdict = (failed[-1]["detail"].get("command", ""), out), f"is still red: {first}"
                    red = "fail"
                    say(f"the goal's check failed: {first}")
                elif back:
                    verdict = f"did not run: {', '.join(n.id for n in back)} came back"
                else:  # nothing under the root, proposals you never accepted, or tasks that could not start
                    pending = [n.id for n in leaves if n.state == P.PROPOSED]
                    idle = [n.id for n in leaves if n.state == P.OPEN]
                    why = (
                        f"the planner's proposal put no task under {root_id}: `graphene plan` shows it"
                        if not leaves
                        else f"{', '.join(pending)} still wait for your accept (`graphene plan accept`)"
                        if pending
                        else f"{', '.join(idle)} did not start: `graphene plan` says what each waits on"
                    )
                    log(store, k, "waits", paid, budget, red, why, root=root_id, goal=goal)
                    say(f"{WAITS}{why}")
                    return 3
                if k > rounds:
                    why = f"the goal's check {verdict} after {rounds} fix round{'s' * (rounds != 1)}"
                    log(store, k, "waits", paid, budget, red, why, root=root_id, goal=goal)
                    say(f"{WAITS}{why}; `graphene config set rounds N` allows more, `graphene auto` goes on")
                    say(_ended(store, began_goal, k, verdict))
                    return 1
                k += 1
        except KeyboardInterrupt:
            why = "stopped by you before anything ran this round; `graphene auto` goes on from here"
            log(store, k, "waits", spent(store, at), budget, red, why, root=root_id, goal=goal)
            say(f"auto {why}")
            return 1
