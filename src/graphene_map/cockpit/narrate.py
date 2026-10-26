"""The narrator: a row of the plan's log in words, as the replay's news line and `graphene state --json` say
it. No Textual here, so a snapshot for an editor reads it without loading a screen."""

from __future__ import annotations

import json

from .lines import fit
from .read import OURS, fork_why
from .rows import FORK_WORD, kept_said

# a row of the plan's log as a narrator says it of its task, the task's title in {}; a kind in none of these
# tables (precheck, usage, model, attempt, ended, a run's summary) is bookkeeping and says nothing
MILESTONES = {
    "proposed": "proposed: {}", "accepted": "you accepted {}", "started": "{} started",
    "check_passed": "{}: its check passed", "check_failed": "{}: its check failed",
    "finished": "{} is proven", "rolled_up": "{} is proven",  # the screen's word; overruled stays "done"
    "signed_off": "you signed off {}", "landed": "{} landed",
    "reopened": "{} reopened", "dropped": "{} dropped", "overruled": "{} is done over its check",
    "added": "{} added",
    "auto": "auto · {}",  # a round of `graphene auto`: its words are `auto_said`'s, not a task's title
}  # fmt: skip
GOALS = {"asked": "you asked", "goal_proposed": "proposed goal", "goal": "your goal"}  # its note is the words
ASKS = {"question": "asks", "assume": "assumes", "risk": "flags a risk", "leave out": "leaves out",
        "note": "a note"}  # fmt: skip
TAKES = {"question": "you took the default", "assume": "you confirmed", "risk": "you noted",
         "leave out": "you agreed to leave out"}  # fmt: skip
LISTS = {"scope": ("may now write", "may no longer write"), "needs": ("now waits on", "no longer waits on")}
FIELDS = {"goal": "it should now achieve"}  # in a task's own terms: "goal" is the headline's word for yours


def words(text) -> str:
    """What someone wrote, on one line, cut with an ellipsis to leave room for the rest of the news."""
    return fit(" ".join(str(text or "").split()), 60)


def item(text) -> str:
    """A fork's words as one item of the news, which ` · ` parts: its own ` · ` (the rule's reason has one)
    reads as a comma, so one verdict does not read as two."""
    return words(text).replace(" · ", ", ")


def auto_said(d: dict) -> str:
    """A round of `graphene auto` as the news says it (its row's detail is `auto.state`'s): `round 2 of 3:
    fixing`, a round being the first plan or a fix round after the goal's check failed; or why it waits."""
    where = f"round {d.get('round') or 1} of {int(d.get('rounds') or 2) + 1}"
    if d.get("stage") == "waits":
        return f"{where} waits: {item(d.get('why') or 'needs you')}"
    if d.get("stage") == "fixing" and d.get("why"):
        return f"{where}: the goal's check failed ({item(d['why'])}), so it plans the fix"
    return f"{where}: {d.get('stage') or 'on'}"


def news(
    line: dict, titles: dict[str, str] | None = None, names: dict[str, str] | None = None,
    models: dict[str, dict[str, str]] | None = None,
) -> str:
    """One recorded change as a narrator says it, each task by its title (``titles``): what an agent did or
    said, a write the gate stopped, why a task came back, what the board asks and what you answered, what
    an edit changed, what was accepted, proven and landed. A fork's row names the fork as the rows do, the
    agent's number (``names``) and its letter, and its model when known (``models``, a task's letters to
    their names): "agent 3b (Nano): editing app.py", its check's verdict, which was kept. Bookkeeping
    (precheck, usage, model, attempt, ended, an executor's output, the settings, the
    agent's own `graphene node` commands) says nothing, so the last news stays up. Three at most, in the
    order they happened: the latest of the rest before an agent's moves, so a hand-back is not crowded out
    by the edits that came before it; and your answer before the edits it made, which the log has first.
    Tasks accepted together are one item, their count: the last three of six accepts read as if two tasks
    were, and a sub-goal comes with its tasks."""
    titles, names, models = titles or {}, names or {}, models or {}
    items = {it["id"]: it for it in json.loads((line.get("plan_meta") or {}).get("board") or "[]")}
    parents = {json.loads(n.get("data") or "{}").get("parent") for n in (line.get("nodes") or {}).values()}
    accepted: list[int] = []  # where the accepts' one item is, once per accepted task
    said: list[str] = []
    moves: set[int] = set()  # which of them are an agent's own moves: what it did or said
    first: dict[int, int] = {}  # an answer that edited the plan -> where the edits it made begin
    edits = 0  # where the edits said just before this row begin
    ends = ("finished", "overruled", "refused")  # a check that passed with none of these was not done yet
    ended = {r["node_id"] for r in line.get("node_log") or [] if r["kind"] in ends}
    for row in line.get("node_log") or []:
        d, kind = json.loads(row.get("detail") or "{}"), row["kind"]
        title = titles.get(row["node_id"], row["node_id"])
        fork = d["fork"] if isinstance(d.get("fork"), str) else ""  # a run's fork (Nemotron's are numbered)
        who = title  # a fork's row: its agent's number and its letter, as its row says it, and its model
        if fork and row["node_id"] in names:
            who = f"agent {names[row['node_id']]}{fork}"
        elif fork:
            who = f"{title} fork {fork}"
        if fork and (model := (models.get(row["node_id"]) or {}).get(fork)):
            who += f" ({model})"
        if kind == "did" and not OURS.search(str(d.get("target") or "")):
            moves.add(len(said))
            said.append(f"{who}: {d.get('verb', '')} {words(d.get('target'))}")
        elif kind == "said":
            moves.add(len(said))
            said.append(f"{who}: {words(d.get('text'))}")
        elif kind == "denied" and d.get("path"):
            said.append(f"{who}: stopped writing {d['path']}" + (" in another copy" if d.get("copy") else ""))
        elif kind == "forked":
            said.append(f"{title} forked {d.get('of') or len(d.get('forks') or [])} ways")
        elif kind == "fork" and fork and "attempts" in d and d.get("state") == "passed":  # as the fork ended
            said.append(f"{who}: its check passed" + (f", {d['lines']} lines" if d.get("lines") else ""))
        elif kind == "fork" and fork and "attempts" in d and d.get("state") not in (None, "running"):
            state = FORK_WORD.get(d["state"], d["state"])
            said.append(f"{who}: {state}" + (f": {item(fork_why(d['why']))}" if d.get("why") else ""))
        elif kind == "picked":  # as the run says it: `greet kept b: …`
            said.append(f"{title} " + kept_said((str(d.get("fork") or ""), item(d.get("reason")),
                                                  str(d.get("by") or "")), ": "))  # fmt: skip
        elif kind == "released":
            said.append(f"{title} came back: {words(d.get('why'))}")
        elif kind == "refused" and d.get("outside"):
            said.append(f"{title} is not done: {words(', '.join(d['outside']))} is outside its scope")
        elif kind == "refused" and "unchanged" in d:
            said.append(f"{title} is not done: nothing in its scope changed")
        elif kind == "check_passed" and row["node_id"] not in ended:  # 0.5.0 logged no refusal after it
            said.append(f"{title}: its check passed, not done yet")
        elif kind == "board":
            if d.get("became"):  # what it changed is in the rows just before it
                first[len(said)] = edits
            said.append(board_act(d, items))
        elif kind == "edited":
            said += edit_said(title, d.get("changed") or {}, titles)
        elif kind in GOALS:
            said.append(f"{GOALS[kind]}: {words(d.get('note'))}")
        elif kind == "accepted" and row["node_id"] not in parents:
            who = "your envelope accepted" if d.get("by") == "auto" else "you accepted"  # auto's, or yours
            accepted.append(accepted[0] if accepted else len(said))
            if len(accepted) == 1:
                said.append(f"{who} {title}")
            else:
                said[accepted[0]] = f"{who} {len(accepted)} tasks"
        elif kind == "accepted":
            continue  # a sub-goal accepted with its tasks: they say it
        elif kind == "auto":
            said.append(MILESTONES[kind].format(auto_said(d)))
        elif kind in MILESTONES:
            said.append(MILESTONES[kind].format(title))
        if kind != "edited":
            edits = len(said)
    kept = sorted(range(len(said)), key=lambda k: (k not in moves, k))[-3:]
    kept.sort(key=lambda k: (first.get(k, k), k not in first))  # as they happened, an answer before its edits
    return " · ".join(said[k] for k in kept)


def board_act(d: dict, items: dict[str, dict]) -> str:
    """A board act in the item's own words: what an agent asks, assumes or leaves out, and what you answered.
    Its row's note is `<act> <item>: <its text>`, and ` → <the answer>` once there is one."""
    act, kind = d.get("act", ""), items.get(d.get("item"), {}).get("kind", "question")
    text, _, answer = str(d.get("note") or "").partition(": ")[2].partition(" → ")
    if act == "put up":
        return f"{ASKS.get(kind, 'asks')}: {words(text)}"
    if act == "took":
        return f"{TAKES.get(kind, 'you took')}: {words(answer if kind == 'question' and answer else text)}"
    if act in ("picked", "answered"):
        return f"you {act}: {words(answer)}"
    return f"{act}: {words(text)}"


def edit_said(title: str, changed: dict, titles: dict[str, str]) -> list[str]:
    """An edit as what it changed: the files the task may write now or no longer, the tasks it waits on now or
    no longer, what it should achieve, else the field and its new value."""
    out = []
    for field, (was, now) in changed.items():
        if field not in LISTS:
            out.append(f"{title}: {FIELDS.get(field, f'its {field} is now')} “{words(now)}”")
            continue
        gained = [x for x in now or [] if x not in (was or [])]
        lost = [x for x in was or [] if x not in (now or [])]
        if field == "needs":
            gained, lost = [titles.get(x, x) for x in gained], [titles.get(x, x) for x in lost]
        for phrase, those in zip(LISTS[field], (gained, lost), strict=True):
            if those:
                out.append(f"{title} {phrase} {', '.join(those)}")
    return out
