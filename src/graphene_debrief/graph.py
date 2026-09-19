"""The map's contract: everything the page draws, with every position computed here.

Time runs left to right and one x unit is one second in which something was recorded; an idle
gap over two minutes becomes a break of fixed width that keeps its real duration. Agents are lanes
and the repo is rows of directories, both in order of first appearance, each in its own region with
its own y origin (so a new lane never pushes a repo row). The guarantee, tested over every prefix
of a run: a later record never changes the x of a mark already drawn and, with every group and
directory collapsed (the default), never changes its y. Expanding is the person's act: a member
carries ``dy`` and its group or directory carries ``extra``, and the page adds them; it decides no
order and no size. Nothing here is inferred: every mark and link names the record behind it.
"""

from __future__ import annotations

import json
import os
import posixpath
from dataclasses import asdict, dataclass, field

from .attribute import check_segments
from .debrief import _denial
from .model import Agent, Commit, ToolEvent
from .record import changes, coverage, seconds, window_commits
from .store import Store

CAPTION = "Layout and timing do not imply causality."
SOURCE = "claude-code"
IDLE = 120.0  # seconds with nothing recorded before the axis breaks
BREAK = 60.0  # the fixed width of a break, in x units
TICK = 300.0  # a tick at the first recorded moment at or after every five minutes of x
BUCKET = 10.0  # marks of one kind on one lane or row closer than this merge into one, with a count
LANE_H = 28
ROW_H = 22
MARK_CAP = 1500  # past this the bucket doubles until the marks fit; `omitted` says what that merged
CLAIM = 600.0  # a writer's hold on a file ends ten quiet minutes after its last write, or when it stops
TEXT_CAP = 2000
PATHS_CAP = 500
SPAWNERS = {"Agent", "Task", "Workflow"}
UNKNOWN_LANE = "lane:unknown"


@dataclass(slots=True)
class Lane:
    id: str
    kind: str  # main | agent | group | unknown
    session: str | None
    agent: str | None
    t0: str
    parent: str | None = None  # the lane that spawned it
    group: str | None = None  # the collapsed group it is drawn on until the person opens it
    depth: int = 0
    type: str | None = None
    task: str | None = None
    prompt: str | None = None
    cwd: str | None = None
    worktree: str | None = None
    run: str | None = None
    phase: str | None = None
    label: str | None = None
    closing: str | None = None
    t1: str | None = None
    x0: float = 0.0
    x1: float = 0.0
    y: float = 0.0
    dy: float = 0.0  # added to y when its group is open
    members: int = 0
    extra: float = 0.0  # height a group adds below itself when open
    source: str = SOURCE


@dataclass(slots=True)
class Row:
    id: str
    kind: str  # dir | file
    path: str
    t0: str
    dir: str | None = None
    y: float = 0.0
    dy: float = 0.0  # added to y when its directory is open
    files: int = 0
    changes: int = 0
    extra: float = 0.0
    collision: bool = False
    agents: list[str] = field(default_factory=list)  # lanes that wrote it, in order of first write


@dataclass(slots=True)
class Mark:
    id: str
    kind: str  # prompt | step | spawn | check | commit | failure | refused | outside | change | evidence
    region: str  # lanes | rows
    at: str  # the lane or row it sits on
    x: float
    y: float
    t: str
    agent: str | None  # the lane whose colour it takes
    grade: str  # edit | shell | commit | window | unknown for files; record for a recorded call
    ref: str  # the first record behind it
    count: int = 0
    label: str | None = None
    ok: bool | None = None
    shared: bool = False
    copy: bool = False


@dataclass(slots=True)
class Link:
    id: str
    kind: str  # spawned | returned | touched | committed-in | ran | blocked
    source: str
    target: str
    grade: str
    ref: str
    count: int = 1


@dataclass(slots=True)
class Graph:
    version: int = 1
    caption: str = CAPTION
    run: dict = field(default_factory=dict)
    axis: dict = field(default_factory=dict)
    lanes: list[Lane] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    counters: dict = field(default_factory=dict)
    omitted: dict = field(default_factory=dict)


def to_json(graph: Graph, indent: int | None = None) -> str:
    return json.dumps(asdict(graph), ensure_ascii=False, indent=indent)


class Axis:
    """x for every recorded moment. x(t) depends only on the moments at or before t, which is what
    makes a mark's x final the moment it is drawn."""

    def __init__(self, stamps: set[str]) -> None:
        self.stamps = sorted(stamps, key=seconds)
        self.x: dict[str, float] = {}
        self.segments: list[dict] = []
        x = 0.0
        for before, stamp in zip([None, *self.stamps], self.stamps, strict=False):
            if before is not None:
                gap = seconds(stamp) - seconds(before)
                width = BREAK if gap > IDLE else gap
                if gap > IDLE:
                    self.segments.append(
                        {"kind": "break", "t0": before, "t1": stamp, "x0": x, "x1": x + width, "seconds": gap}
                    )
                x = round(x + width, 3)
            self.x[stamp] = x
        self.width = x
        self.ticks: list[dict] = []  # recorded moments, so a tick never moves either
        for stamp in self.stamps:
            if self.x[stamp] >= len(self.ticks) * TICK:
                self.ticks.append({"x": self.x[stamp], "t": stamp})


def _lane_id(session_id: str, agent_id: str | None) -> str:
    return f"lane:{session_id[:8]}:{agent_id or 'main'}"


def _ref(event: ToolEvent) -> str:
    return f"event:{event.session_id[:8]}:{event.id}"


def _kind(event: ToolEvent) -> tuple[str, str | None, bool | None]:
    """(mark kind, label, ok) for one call on its agent's lane."""
    command = str(event.input.get("command") or "") if event.tool == "Bash" else ""
    checks = check_segments(command) if command else []
    if checks:
        return "check", checks[0], event.success is not False
    if event.success is False:
        error = event.response.get("error") if isinstance(event.response, dict) else event.response
        refused, reason = _denial(str(error or ""))
        return ("refused", reason, False) if refused else ("failure", event.tool, False)
    if event.tool in SPAWNERS:
        return "spawn", str(event.input.get("description") or event.tool), None
    if event.file_path and os.path.isabs(event.file_path):
        return "outside", event.file_path, None
    return "step", None, None


class _Marks:
    """Marks merged by what they are, where they are and their x bucket; the first record in a
    bucket gives the mark its id and its x, so coarser buckets absorb marks and never move one."""

    def __init__(self, bucket: float) -> None:
        self.bucket = bucket
        self.by_key: dict[tuple, Mark] = {}
        self.on_lane: dict[str, str] = {}  # record reference -> the lane mark that holds it

    def add(self, mark: Mark) -> Mark:
        key = (mark.kind, mark.at, mark.agent, mark.grade, mark.ok, int(mark.x // self.bucket))
        kept = self.by_key.setdefault(key, mark)
        kept.count += 1
        kept.shared = kept.shared or mark.shared
        kept.copy = kept.copy or mark.copy
        if mark.region == "lanes":
            self.on_lane[mark.ref] = kept.id
        return kept


def build_graph(store: Store, session_ids: list[str], until: str | None = None) -> Graph:
    """The graph of these sessions, as recorded up to ``until`` (everything when None)."""

    def seen(stamp: str | None) -> bool:
        return bool(stamp) and (until is None or seconds(stamp) <= seconds(until))

    sessions = [s for s in (store.session(i) for i in session_ids) if s is not None]
    sessions = [s for s in sessions if s.started_at is None or seen(s.started_at)]
    ids = [s.id for s in sessions]
    events = [e for i in ids for e in store.events(i) if seen(e.timestamp)]
    events.sort(key=lambda e: (seconds(e.timestamp), e.id))
    prompts = [p for i in ids for p in store.prompts(i) if seen(p.timestamp)]
    agents = [a for i in ids for a in store.agents(i) if seen(a.started_at)]
    repo = sessions[0].repo if sessions else ""
    written, vendor = changes(events, agents, repo)

    starts = [s.started_at for s in sessions if s.started_at]
    commits: list[Commit] = []
    if starts:  # the window is compared as numbers: stored stamps differ in precision and offset
        opened = min(seconds(t) for t in starts)
        closed = max(seconds(s.ended_at) if s.ended_at else float("inf") for s in sessions)
        closed = min(closed, seconds(until)) if until else closed
        day = min(starts, key=seconds)[:10]
        in_window = [
            c for c in store.commits_between(day, "9999") if opened <= seconds(c.committed_at) <= closed
        ]
        commits = window_commits(in_window, ids)
    by_id = {(e.session_id, e.id): e for e in events}
    cov = coverage(commits, written, ids)

    # -- the axis: every recorded moment ---------------------------------------------------------
    stamps = {e.timestamp for e in events} | {p.timestamp for p in prompts} | set(starts)
    stamps |= {a.started_at for a in agents if a.started_at} | {
        a.ended_at for a in agents if seen(a.ended_at)
    }
    stamps |= {c.committed_at for c in commits}
    axis = Axis(stamps)

    # -- lanes, in order of first appearance -----------------------------------------------------
    first: dict[str, str] = {}
    last: dict[str, str] = {}

    def span(lane: str, stamp: str | None) -> None:
        if stamp:
            first[lane] = min(first.get(lane, stamp), stamp, key=seconds)
            last[lane] = max(last.get(lane, stamp), stamp, key=seconds)

    known = {(a.session_id, a.id): a for a in agents}
    for s in sessions:
        span(_lane_id(s.id, None), s.started_at)
    for p in prompts:
        span(_lane_id(p.session_id, None), p.timestamp)
    for e in events:
        span(_lane_id(e.session_id, None), e.timestamp)  # the main agent is there for the whole session
        span(_lane_id(e.session_id, e.agent_id), e.timestamp)
        if e.agent_id and (e.session_id, e.agent_id) not in known:  # an agent only its calls record
            known[(e.session_id, e.agent_id)] = Agent(id=e.agent_id, session_id=e.session_id)
    for a in known.values():
        for stamp in (a.started_at, a.ended_at if seen(a.ended_at) else None):
            span(_lane_id(a.session_id, a.id), stamp)
            span(_lane_id(a.session_id, None), stamp)

    lanes: dict[str, Lane] = {}
    for s in sessions:
        lane = _lane_id(s.id, None)
        if lane in first:
            lanes[lane] = Lane(lane, "main", s.id, None, first[lane], cwd=s.repo)

    def parent_of(a: Agent) -> str:
        lane = _lane_id(a.session_id, a.parent_agent_id)
        return lane if (a.session_id, a.parent_agent_id) in known else _lane_id(a.session_id, None)

    for a in known.values():
        lane = _lane_id(a.session_id, a.id)
        group = f"group:{a.session_id[:8]}:{a.workflow_run}" if a.workflow_run else None
        lanes[lane] = Lane(
            lane,
            "agent",
            a.session_id,
            a.id,
            first[lane],
            parent=parent_of(a),
            group=group,
            depth=a.depth or 1,
            type=a.type,
            task=a.task,
            prompt=a.prompt[:TEXT_CAP] if a.prompt else None,
            cwd=a.cwd,
            worktree=a.worktree,
            run=a.workflow_run,
            phase=a.phase,
            label=a.label,
            closing=a.closing[:TEXT_CAP] if a.closing and seen(a.ended_at) else None,
            source=a.source,
        )
        if group:
            span(group, first[lane])
            span(group, last[lane])
            if group not in lanes:
                lanes[group] = Lane(
                    group, "group", a.session_id, None, first[group], run=a.workflow_run, depth=1
                )
                lanes[group].parent = parent_of(a)
    unattributed = [c for c in commits if c.session_id is None]
    for c in unattributed:
        span(UNKNOWN_LANE, c.committed_at)
    if unattributed:
        lanes[UNKNOWN_LANE] = Lane(UNKNOWN_LANE, "unknown", None, None, first[UNKNOWN_LANE])
        lanes[UNKNOWN_LANE].task = "no recorded agent"

    def order(lane: Lane) -> tuple:
        return (seconds(first[lane.id]), lane.id)

    top = sorted((lane for lane in lanes.values() if lane.group is None), key=order)
    for index, lane in enumerate(top):
        lane.y = float(index * LANE_H)
        members = sorted((m for m in lanes.values() if m.group == lane.id), key=order)
        for k, member in enumerate(members):
            member.y, member.dy = lane.y, float((k + 1) * LANE_H)
        lane.members, lane.extra = len(members), float(len(members) * LANE_H)
    for lane in lanes.values():
        lane.t0, lane.t1 = first[lane.id], last[lane.id]
        lane.x0, lane.x1 = axis.x[lane.t0], axis.x[lane.t1]

    # -- rows: directories and their files, in order of first appearance -------------------------
    evidence = [  # a commit's path with no write recorded before it: drawn where the commit is
        (c, path) for c in commits for path, _ in c.files if cov.pairs[(c.sha, path)] in ("commit", "window")
    ]
    seen_at: dict[str, str] = {}
    for w in written:
        seen_at.setdefault(w.path, w.timestamp)
    for c, path in evidence:
        seen_at[path] = min(seen_at.get(path, c.committed_at), c.committed_at, key=seconds)
    rows: dict[str, Row] = {}
    for path, stamp in sorted(seen_at.items(), key=lambda item: (seconds(item[1]), item[0])):
        directory = posixpath.dirname(path) or "."
        parent = rows.setdefault(f"dir:{directory}", Row(f"dir:{directory}", "dir", directory, stamp))
        parent.files += 1
        rows[f"file:{path}"] = Row(f"file:{path}", "file", path, stamp, dir=parent.id)
    folders = [r for r in rows.values() if r.kind == "dir"]
    for index, folder in enumerate(folders):
        folder.y, folder.extra = float(index * ROW_H), float(folder.files * ROW_H)
        for k, child in enumerate(r for r in rows.values() if r.dir == folder.id):
            child.y, child.dy = folder.y, float((k + 1) * ROW_H)

    # -- collisions: a second agent writes a file while the first still holds it ------------------
    stopped = {  # a recorded stop, never the last thing seen: a prefix of the run must agree with the whole
        _lane_id(a.session_id, a.id): seconds(a.ended_at) for a in known.values() if seen(a.ended_at)
    }
    holds: dict[str, dict[str, float]] = {}  # path -> lane -> its last write
    for w in written:
        lane = _lane_id(w.session_id, w.agent_id)
        row = rows[f"file:{w.path}"]
        row.changes += 1
        rows[row.dir].changes += 1
        if lane not in row.agents:
            row.agents.append(lane)
        now = seconds(w.timestamp)
        for other, touched in holds.setdefault(w.path, {}).items():
            if other != lane and now <= min(touched + CLAIM, max(stopped.get(other, now), touched)):
                row.collision = rows[row.dir].collision = True
        holds[w.path][lane] = now

    # -- marks ------------------------------------------------------------------------------------
    def existing(session_id: str | None, agent_id: str | None) -> str:
        """The agent's lane; the main lane when only its id is recorded; the unknown lane for nobody."""
        if session_id is None:
            return UNKNOWN_LANE
        lane = _lane_id(session_id, agent_id)
        return lane if lane in lanes else _lane_id(session_id, None)

    commit_lane: dict[str, str] = {}
    commit_at: dict[str, str] = {}
    for c in commits:
        made = by_id.get((c.session_id, c.event_id)) if c.session_id and c.event_id else None
        ran_by = made.agent_id if made else c.agent_id
        commit_lane[c.sha] = existing(c.session_id, ran_by)
        commit_at[c.sha] = made.timestamp if made else c.committed_at

    def credit(c: Commit) -> str:
        return existing(c.session_id, c.agent_id)

    def draw(bucket: float) -> _Marks:
        marks = _Marks(bucket)
        specs: list[Mark] = []

        def lane_mark(kind, lane, stamp, agent, ref, label=None, ok=None):
            y = lanes[lane].y
            specs.append(
                Mark(
                    f"{kind}:{lane}:{ref}", kind, "lanes", lane, axis.x[stamp], y, stamp, agent, "record", ref
                )
            )
            specs[-1].label, specs[-1].ok = label, ok

        for p in prompts:
            lane = _lane_id(p.session_id, None)
            lane_mark(
                "prompt", lane, p.timestamp, lane, f"prompt:{p.session_id[:8]}:{p.id}", p.text[:TEXT_CAP]
            )
        for e in events:
            lane = _lane_id(e.session_id, e.agent_id)
            kind, label, ok = _kind(e)
            lane_mark(kind, lane, e.timestamp, lane, _ref(e), label, ok)
        for c in commits:
            label = f"{c.sha[:7]} {c.subject}"
            lane_mark("commit", commit_lane[c.sha], commit_at[c.sha], credit(c), f"commit:{c.sha}", label)
        for w in written:
            row = rows[f"file:{w.path}"]
            lane = _lane_id(w.session_id, w.agent_id)
            ref = f"event:{w.session_id[:8]}:{w.event_id}"
            mark = Mark(
                f"change:{row.id}:{ref}",
                "change",
                "rows",
                row.id,
                axis.x[w.timestamp],
                row.y,
                w.timestamp,
                lane,
                w.grade,
                ref,
            )
            mark.shared, mark.copy = w.shared, w.copy
            specs.append(mark)
        for c, path in evidence:
            row = rows[f"file:{path}"]
            ref = f"commit:{c.sha}"
            stamp = c.committed_at
            specs.append(
                Mark(
                    f"evidence:{row.id}:{ref}",
                    "evidence",
                    "rows",
                    row.id,
                    axis.x[stamp],
                    row.y,
                    stamp,
                    credit(c),
                    cov.pairs[(c.sha, path)],
                    ref,
                )
            )
        for mark in sorted(specs, key=lambda m: (m.x, m.id)):
            marks.add(mark)
        return marks

    bucket = BUCKET
    marks = draw(bucket)
    while len(marks.by_key) > MARK_CAP:
        bucket *= 2
        marks = draw(bucket)
    drawn = list(marks.by_key.values())

    # -- links ------------------------------------------------------------------------------------
    links: dict[str, Link] = {}

    def link(kind: str, source: str, target: str, grade: str, ref: str) -> None:
        key = f"{kind}:{source}>{target}" + (f":{grade}" if kind == "touched" else "")
        if key in links:
            links[key].count += 1
        else:
            links[key] = Link(key, kind, source, target, grade, ref)

    runs = {  # a Workflow call's runId names the directory its agents are recorded in
        e.response.get("runId"): e for e in events if e.tool == "Workflow" and isinstance(e.response, dict)
    }
    for lane in lanes.values():
        if lane.kind == "group" and lane.run in runs:
            lane.label = runs[lane.run].response.get("workflowName")
    for a in known.values():
        lane = lanes[_lane_id(a.session_id, a.id)]
        call = by_id.get((a.session_id, a.parent_tool_use_id)) or runs.get(a.workflow_run)
        ref = _ref(call) if call else f"agent:{a.session_id[:8]}:{a.id}"
        link("spawned", marks.on_lane.get(ref, lane.parent), lane.id, "record", ref)
        if seen(a.ended_at):
            link("returned", lane.id, lane.parent, "record", f"agent:{a.session_id[:8]}:{a.id}")
    for w in written:
        ref = f"event:{w.session_id[:8]}:{w.event_id}"
        link("touched", _lane_id(w.session_id, w.agent_id), f"file:{w.path}", w.grade, ref)
    for c in commits:
        for path, _ in c.files:
            if f"file:{path}" in rows:
                link(
                    "committed-in",
                    f"file:{path}",
                    marks.on_lane[f"commit:{c.sha}"],
                    cov.pairs[(c.sha, path)],
                    f"commit:{c.sha}",
                )
    for mark in drawn:
        if mark.kind in ("check", "refused"):
            link("ran" if mark.kind == "check" else "blocked", mark.at, mark.id, "record", mark.ref)

    # -- the agent's own list, counters, and what was left out ------------------------------------
    tasks: dict[str, dict] = {}
    for e in events:
        if (
            e.tool == "TaskCreate"
            and isinstance(e.response, dict)
            and isinstance(e.response.get("task"), dict)
        ):
            item = {
                "id": str(e.response["task"].get("id")),
                "subject": e.input.get("subject"),
                "ref": _ref(e),
            }
            item |= {
                "lane": _lane_id(e.session_id, e.agent_id),
                "created": e.timestamp,
                "x": axis.x[e.timestamp],
            }
            tasks[item["id"]] = item | {"started": None, "done": None}
        elif e.tool == "TaskUpdate" and str(e.input.get("taskId")) in tasks:
            state = {"in_progress": "started", "completed": "done"}.get(str(e.input.get("status")))
            if state:
                tasks[str(e.input["taskId"])][state] = e.timestamp

    checks = [(e, check_segments(str(e.input.get("command") or ""))) for e in events if e.tool == "Bash"]
    failed = [(e, segs) for e, segs in checks if segs and e.success is False]
    green = sum(
        any(
            e2.success is not False and set(s2) & set(segs) and seconds(e2.timestamp) > seconds(e.timestamp)
            for e2, s2 in checks
        )
        for e, segs in failed
    )
    kinds = [_kind(e)[0] for e in events]
    nothing = [p for p, g in cov.grades.items() if g == "window"]
    only_commit = [p for p, g in cov.grades.items() if g == "commit"]
    return Graph(
        run={
            "sessions": [
                {
                    "id": s.id,
                    "source": SOURCE,
                    "recorded_by": s.source,
                    "started": s.started_at,
                    "ended": s.ended_at,
                }
                for s in sessions
            ],
            "repo": os.path.basename(repo),
            "t0": axis.stamps[0] if axis.stamps else None,
            "t1": axis.stamps[-1] if axis.stamps else None,
            "prompts": len(prompts),
            "agents": len(known),
            "commits": len(commits),
        },
        axis={
            "unit": "one x is one second in which something was recorded",
            "width": axis.width,
            "bucket": bucket,
            "breaks": axis.segments,
            "ticks": axis.ticks,
        },
        lanes=sorted(lanes.values(), key=lambda lane: (lane.y, lane.dy)),
        rows=sorted(rows.values(), key=lambda r: (r.y, r.dy)),
        # by x, which is how the page finds the marks on screen, and a plain step before anything
        # at the same x, so the mark that says more is the one on top and the one a click reaches
        marks=sorted(drawn, key=lambda m: (m.x, m.kind != "step", m.id)),
        links=sorted(links.values(), key=lambda item: item.id),
        tasks=sorted(tasks.values(), key=lambda t: t["x"]),
        coverage={
            "committed_files": cov.committed_files,
            "write": cov.write,
            "edit": cov.edit,
            "shell": cov.shell,
            "commit": cov.commit,
            "nothing": cov.nothing,
            "window": cov.window,
            "paths": {"commit": only_commit[:PATHS_CAP], "nothing": nothing[:PATHS_CAP]},
        },
        counters={
            "failed_checks": len(failed),
            "rerun_green": green,
            "refused": kinds.count("refused"),
            "failures": kinds.count("failure"),
            "outside": len({e.file_path for e in events if _kind(e)[0] == "outside"}),
            "collisions": sum(r.collision for r in rows.values() if r.kind == "file"),
        },
        omitted={
            "records": len(prompts) + len(events) + len(commits) + len(written) + len(evidence),
            "merged_into_counts": sum(m.count - 1 for m in drawn),
            "vendor_more_files": vendor.more_files,
            "vendor_lists_unavailable": vendor.unavailable,
            "coverage_paths": max(0, len(nothing) - PATHS_CAP) + max(0, len(only_commit) - PATHS_CAP),
        },
    )
