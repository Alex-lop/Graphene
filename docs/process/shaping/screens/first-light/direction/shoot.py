"""Screens of Graphene's own direction with tonight's plan and sessions hanging from it.

It never writes the real store. It reads the sessions the hooks recorded in the last day from
``--store`` (opened read-only), copies them into a new repository in a scratch directory with
Graphene's own ``.graphene/direction.txt``, and there:

- proposes tonight's plan (the first-light directive's lanes) as the session named by
  ``CLAUDE_CODE_SESSION_ID`` (the coordinator's, when run from its lanes), so that session and its
  subagents attach through the plan's node by what they do;
- stands in for Alex in that scratch store only, as a person caller: accepts the plan, hangs it from
  ``first-light``, and attaches the lanes whose work serves another node to that node. The
  direction's own nodes stay proposed, as they are in the committed file;
- writes `graphene direction` at 80 and 120 columns, `graphene plan --view tree` at 120x36, and
  `graphene watch` at 80x24 and 120x36, as text.

    cd docs/process/shaping/screens/first-light/direction
    uv run python shoot.py --store ~/Desktop/AllThingsAgenticHackathon/.graphene/graphene.db --out .
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from graphene_map import direction as D
from graphene_map import plan as P
from graphene_map.store import Store
from graphene_map.tui import Watch

ROOT = Path(__file__).resolve().parents[6]
ALEX = P.Caller("alex", True)
PLAN = """\
goal: first light: Graphene meets a real model for the first time, as practice, under $10
- A. first light: rungs 2 to 5 live, and the fixes first contact forces  [lane-a]
    scope: src/**, tests/**, docs/test/**
    check: python3 -m pytest tests/test_practice.py -q
- B. the rough cut, in real time  [lane-b]
    scope: docs/demo/**
    check: test -x docs/demo/build.sh
- C. what the shaping run left broken  [lane-c]
  - the board earns its place  [board]
      scope: src/graphene_map/board*.py, tests/test_board*.py, docs/test/**
      check: python3 -m pytest tests/test_board.py -q
  - nothing Graphene starts outlives what started it  [teardown]
      scope: src/graphene_map/**, tests/**
      check: python3 -m pytest tests/test_demo.py -q
  - no test reaches the keychain  [keychain]
      scope: tests/conftest.py, .github/workflows/ci.yml
      check: python3 -m pytest tests/test_keys.py -q
  - the hook's time under load  [hook]
      scope: src/graphene_map/hooks.py, src/graphene_map/gate.py, tests/test_hook_budget.py
      check: python3 -m pytest tests/test_hook_budget.py -q
  - walks.md's rough edges  [walks]
      scope: src/**, ui/**, tests/**, docs/process/shaping/walks.md
      check: python3 -m pytest tests/test_tui.py -q
- D. the direction, with everything attached  [lane-d]
    scope: src/graphene_map/direction*.py, tests/test_direction.py, .graphene/direction.txt
    check: python3 -m pytest tests/test_direction.py -q
- E. ready for the session with Alex  [lane-e]
    scope: docs/test/**
    check: test -f docs/test/LIVE_SESSION.md
- F. polish and the closing review  [lane-f]
    scope: README.md, docs/**
    check: true
    needs: lane-a, lane-b, lane-c, lane-d, lane-e
"""
# the lanes whose work serves another node of the direction than the plan's: the person's choice
ELSEWHERE = {
    "Lane C: the board earns its place": "board",
    "Lane C: replay/teardown processes": "teardown",
    "Lane D: the direction, core": "direction",
    "Lane B: rough cut pipeline": "rough-cut",
    "Lane E: ready for the live session": "with-alex",
    "Research Nebius Sandboxes billing": "sandboxes",
    "Lane C: walks.md, the terminal": "submission",
    "Lane C: walks.md, page and replay": "submission",
}
TABLES = {"sessions": "id", "prompts": "session_id", "tool_events": "session_id", "agents": "session_id"}


def copy_sessions(real: Path, store: Store) -> list[str]:
    """The last day's sessions, their prompts, calls and subagents, read-only from the real store."""
    src = sqlite3.connect(f"file:{real}?mode=ro", uri=True)
    since = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    ids = [r[0] for r in src.execute(
        "SELECT id FROM sessions s WHERE COALESCE(ended_at, started_at) >= ? OR EXISTS (SELECT 1 FROM "
        "tool_events e WHERE e.session_id = s.id AND e.timestamp >= ?)", (since, since))]  # fmt: skip
    for table, key in TABLES.items():
        cols = [c[1] for c in src.execute(f"PRAGMA table_info({table})")]
        rows = src.execute(
            f"SELECT {', '.join(cols)} FROM {table} WHERE {key} IN ({', '.join('?' for _ in ids)})", ids
        ).fetchall()
        store.conn.executemany(
            f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", rows
        )
    src.close()
    return ids


def graphene(repo: Path, *args: str, stdin: str | None = None, env: dict | None = None) -> str:
    said = subprocess.run(["graphene", *args], cwd=repo, input=stdin, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})  # fmt: skip
    return said.stdout


def screen(repo: Path, size: tuple[int, int]) -> str:
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            app.refresh_plan()
            await pilot.pause()
            return "\n".join(s.text.rstrip() for s in app.screen._compositor.render_strips())

    return asyncio.run(go())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(tempfile.mkdtemp(prefix="direction-demo-"))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    for part in ("src", "tests", "docs/test", "docs/demo"):
        (repo / part).mkdir(parents=True)
    (repo / "README.md").write_text("a scratch copy for the direction's screens\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=d@example.com", "-c", "user.name=D", "commit", "-qm", "start"],
                   cwd=repo, check=True)  # fmt: skip
    (repo / ".graphene").mkdir()
    shutil.copy(ROOT / D.FILE, repo / D.FILE)
    with Store.open(repo) as store:
        copy_sessions(args.store, store)
    graphene(repo, "plan", "propose", "-", stdin=PLAN)  # as the session that runs this: an agent's proposal
    with Store.open(repo) as store:
        P.accept(store, [], ALEX)
        d = D.read(repo)
        D.hang(store, d, "first-light", ALEX)
        tasks = dict(store.conn.execute(
            "SELECT json_extract(input, '$.description'), json_extract(response, '$.agentId') "
            "FROM tool_events WHERE tool = 'Agent'").fetchall())  # fmt: skip
        for task, node in ELSEWHERE.items():
            if tasks.get(task):
                D.attach(store, d, tasks[task], node, ALEX)
    args.out.mkdir(parents=True, exist_ok=True)
    env = {"GRAPHENE_AS": "person:alex"}
    for wide in (80, 120):
        said = graphene(repo, "direction", "--width", str(wide), env=env)
        (args.out / f"direction-{wide}.txt").write_text(said)
    (args.out / "plan-tree-120x36.txt").write_text(
        graphene(repo, "plan", "--view", "tree", "--width", "120", "--height", "36", env=env)
    )
    for size in ((80, 24), (120, 36)):
        (args.out / f"watch-{size[0]}x{size[1]}.txt").write_text(screen(repo, size) + "\n")
    print(repo)


if __name__ == "__main__":
    main()
