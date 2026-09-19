"""Generate the synthetic *run* fixture under tests/fixtures/run.

One invented run on 2026-03-02 that exercises everything the graph has to draw: a main agent, a
Workflow group of six subagents, two plain `Agent` subagents, two worktrees (one inside the repo,
one outside it), a second top-level session in the outside worktree, heredoc writes with
`bashEditDiff`, commits in both recorded response shapes, a recorded cherry-pick, a commit with no
record at all, a check that fails then passes, a refused call, a write outside the repo, two agents
on one file in overlapping windows, and a `TaskCreate` list.

The scenario is said once, as `Turn` and `CommitSpec` data. The transcripts (`render`), the hook
events (`hook_events`), the real git repo (`build_repo`), the ground truth (`expected`) and the
direct store load (`load`) are all derived from it. Nothing here reads a clock, a random source or
the real machine: rendering twice is byte-identical, and every path is invented.

Run ``uv run python tests/fixtures/make_run_fixture.py`` to rewrite tests/fixtures/run;
tests/test_run_fixture.py checks the checked-in copy against this module.

Commits in S1's window, and the agent each belongs to::

    parser    app/parser.py                              w1    recorded commit, `stdout` shape
    store     app/store.py                               w2    recorded commit, `content` shape
    w3        app/cli.py           branch worktree-agent-w3    recorded commit, in a worktree
    cp        app/cli.py                                 w3    cherry-pick, via origin_sha = w3
    schema    app/schema.py app/gen_a.py app/gen_b.py    w4    recorded commit
    utilcore  app/util.py app/core.py                    w6    recorded commit
    guide     docs/guide.md                              a1    recorded commit
    a2        app/api.py tests/test_api.py  branch feature/api recorded commit, never merged
    unrec     pyproject.toml                         nobody    no record anywhere

Coverage for S1 over the 12 distinct paths in those commits::

    committed_files 12
    edit             6   app/parser.py app/cli.py app/util.py docs/guide.md app/api.py
                         tests/test_api.py
    shell            3   app/store.py app/schema.py app/core.py
    commit           2   app/gen_a.py app/gen_b.py     (in w4's commit, no write recorded)
    window           1   pyproject.toml                (committed in the window by no agent)
    nothing          1   pyproject.toml                (a `window` file counts as nothing)

Two traps are deliberate. `gitBranch` reads "main" on every record, w3's worktree records included,
because concurrent agents contaminate it: the worktree branch is only in the meta.json. And w4's
`bashEditDiff` names one of the three files it generated, with `moreFiles: 2` for the rest.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from make_transcript_fixture import bash_ok, edit_result

from graphene_debrief.model import Agent, Commit, Prompt, Session, ToolEvent
from graphene_debrief.sources.claude_code import project_dir_name

ROOT = "/home/dev/project"
ELSEWHERE = "/home/dev/wt/api"
S1 = "22222222-3333-4444-8555-666666666666"
S2 = "33333333-4444-4555-8666-777777777777"
P1 = "aaaaaaaa-1111-4111-8111-111111111111"
P2 = "bbbbbbbb-2222-4222-8222-222222222222"
RUN = "wf_ab12cd34-ef5"
DATE = "2026-03-02"
OUT = Path(__file__).parent / "run"
MODEL = "claude-fable-5-1"
WT_REL = ".claude/worktrees/agent-w3"
W3_BRANCH = "worktree-agent-w3"
API_BRANCH = "feature/api"
AUTHOR = ("Dev Example", "dev@example.invalid")

W1 = "0a1b2c3d4e5f6071"
W2 = "1a2b3c4d5e6f7082"
W3 = "2a3b4c5d6e7f8093"
W4 = "3a4b5c6d7e8f90a4"
W5 = "4a5b6c7d8e9fa0b5"
W6 = "5a6b7c8d9eafb0c6"
A1 = "6a7b8c9daebfc0d7"
A2 = "7a8b9cadbecfd0e8"
SH = "8a9bacbdcedfe0f9"

# Full SHAs of the repo ``build_repo`` creates. They do not depend on where it is built: identity,
# dates and content are all fixed. Produced by running build_repo once; test 3 re-checks them.
SHAS = {
    "base": "319ac43c27880fd36ab56d75d85af9309a64d041",
    "w3": "23cb2f06198e41d711d1ce1916beb22cda7b4f28",
    "parser": "4d35474499bddf97a8f302e7f0a48c5afd94d91f",
    "store": "527efa6c5f362c9ee0270bdbb3bbdf8a1792bf9a",
    "schema": "a8bc60f696fd40322a48bd364e07cb3758fd7a6f",
    "utilcore": "9c746c608df8db0e46da4e104b6c3384c7089593",
    "cp": "92a7691fff92b4011f9ec5f5ec55b4b50ce92952",
    "guide": "0a95f6e53eac38f2b464a205ae2bab3872bcb774",
    "a2": "2d045414144e90cce7824c493e2195517476e99f",
    "unrec": "e4fe8111d3f92bc5b951f2f1a89d1375f4cd8d5c",
}

# -- invented file contents ----------------------------------------------------------------------

README = "# Widget\n\nA small importer.\n"
PYPROJECT_V0 = '[project]\nname = "widget"\nversion = "0.1.0"\n'
PYPROJECT_V1 = '[project]\nname = "widget"\nversion = "0.2.0"\n'
CORE_V0 = 'VERSION = "0.1.0"\n\n\ndef run(config):\n    return config\n'
CORE_V1 = 'VERSION = "0.2.0"\n\n\ndef run(config):\n    return config\n'
UTIL_V0 = (
    "def clamp(value, low, high):\n"
    "    return max(low, min(value, high))\n"
    "\n"
    "\n"
    "def slug(text):\n"
    "    return text.lower()\n"
)
UTIL_V1 = UTIL_V0.replace("return text.lower()", "return text.strip().lower()")
UTIL_V2 = UTIL_V1.replace("return max(low, min(value, high))", "return min(max(value, low), high)")
UTIL_V3 = UTIL_V2.replace("def slug(text):", "def slug(text: str) -> str:")
TEST_CORE = "from app.core import run\n\n\ndef test_run():\n    assert run({}) == {}\n"
GUIDE_V0 = "# Guide\n\nTo be written.\n"
GUIDE_LINE = "Point the importer at a comma separated file and it prints the row count."
GUIDE_V1 = f"# Guide\n\n{GUIDE_LINE}\n"
GEN_PY = '"""Write app/schema.py and its two helper tables."""\n\nprint("generated 3 files")\n'
PARSER_V0 = (
    '"""Read the import file."""\n'
    "\n"
    "\n"
    "def parse(text):\n"
    '    return [line.split(",") for line in text.splitlines()]\n'
)
PARSER_V1 = PARSER_V0.replace("text.splitlines()]", "text.splitlines() if line.strip()]")
STORE_V0 = "import sqlite3\n\n\ndef open_store(path):\n    return sqlite3.connect(path)\n"
CLI_V0 = (
    "import sys\n"
    "\n"
    "from app.parser import parse\n"
    "\n"
    "\n"
    "def main(argv=None):\n"
    "    argv = sys.argv[1:] if argv is None else argv\n"
    "    print(len(parse(open(argv[0]).read())))\n"
)
SCHEMA_V0 = 'TABLES = ("rows", "runs")\n'
GEN_A_V0 = 'ROWS = ("id", "name")\n'
GEN_B_V0 = 'RUNS = ("id", "started")\n'
API_V0 = "from app.parser import parse\n\n\ndef rows(text):\n    return parse(text)\n"
API_OLD = "return parse(text)"
API_NEW = "return [dict(enumerate(r)) for r in parse(text)]"
API_V1 = API_V0.replace(API_OLD, API_NEW)
TEST_OLD = 'assert rows("a,b") == [["a", "b"]]'
TEST_NEW = 'assert rows("a,b") == [{0: "a", 1: "b"}]'
TEST_API_V0 = f"from app.api import rows\n\n\ndef test_rows():\n    {TEST_OLD}\n"
TEST_API_V1 = TEST_API_V0.replace(TEST_OLD, TEST_NEW)
PLAN_MD = "# Plan\n\nWrite the guide, then the API.\n"
WORKFLOW_SCRIPT = (
    "phase('Build', agents=['Build the parser', 'Build the store', 'Build the CLI', "
    "'Generate the schema'])\nphase('Verify', agents=['Verify util', 'Verify core'])\n"
)

BASE_FILES = (
    ("README.md", README),
    ("pyproject.toml", PYPROJECT_V0),
    ("app/__init__.py", ""),
    ("app/core.py", CORE_V0),
    ("app/util.py", UTIL_V0),
    ("tests/test_core.py", TEST_CORE),
    ("docs/guide.md", GUIDE_V0),
    ("scripts/gen.py", GEN_PY),
)

# -- invented prose ------------------------------------------------------------------------------

PROMPT_TEXT = {
    S1: (
        "Build a parser, a store and a CLI for the import file with a workflow, and check the "
        "tests. Then have agents write the guide and add the HTTP API."
    ),
    S2: ("In this worktree, make the API return dictionaries instead of lists, and lint it with a subagent."),
}
PROMPT_ID = {S1: P1, S2: P2}
FINAL_TEXT = {
    S1: "The modules, the guide and the API are in. The API is on a branch of its own.",
    S2: "The API returns dictionaries now and ruff is clean.",
}
DENIAL = (
    "This command was denied by the Claude Code auto mode classifier. Reason: [pushes to a shared remote]"
)
TASK_W1 = "Write app/parser.py so it reads the import file, and make the tests pass."
TASK_W2 = "Write app/store.py with a heredoc so the rows can be kept in sqlite."
TASK_W3 = "Write app/cli.py in your worktree and commit it on your own branch."
TASK_W4 = "Run scripts/gen.py to generate the schema, then commit everything it wrote."
TASK_W5 = "Tidy app/util.py: strip before lowering, and type the slug helper."
TASK_W6 = "Order the clamp helper, bump the version in app/core.py, and commit both files."
TASK_A1 = "Write docs/guide.md so a new reader can run the importer, and commit it."
TASK_A2 = "Add an HTTP API with a test, in a worktree on a branch of its own."
TASK_SH = "Run ruff over the API and report what it says."

CLOSE_W1 = "app/parser.py skips blank lines; the tests pass and the work is committed."
CLOSE_W2 = "app/store.py opens a sqlite file; written with a heredoc and committed."
CLOSE_W3 = "app/cli.py prints the row count; committed on its own branch, not on main."
CLOSE_W4 = "scripts/gen.py wrote the schema and two table modules; all three are committed."
CLOSE_W5 = "app/util.py strips before lowering and slug is typed; nothing committed here."
CLOSE_W6 = "clamp is ordered and the version is bumped; util.py and core.py are committed."
CLOSE_A1 = "docs/guide.md is written and committed; the push was refused, so nothing was published."
CLOSE_A2 = "app/api.py and its test live on feature/api; the branch was never merged to main."
CLOSE_SH = "ruff is clean on app/api.py."

TASKS = (
    ("task-1", "Build the parser, the store and the CLI", "Building the modules"),
    ("task-2", "Verify util and core", "Verifying the modules"),
    ("task-3", "Write the guide and add the HTTP API", "Writing the guide and the API"),
)
JOURNAL_KEYS = {
    W1: "3f2a9c15b04e7d8861ca0b2e4d97f350",
    W2: "8b1d4e6a2c90f57341ab8c6d0e2f9174",
    W3: "c40f8a71d2e6b39508f1a4c72d6b0e95",
    W4: "5e7b2d91a8c034f61b9d7e02c53a8f46",
    W5: "9a3c7e05b1d84f2760ce5b93a07d1f28",
    W6: "24d8f36b9e01a75c48b2d06f1e93c7a5",
}


def stamp(hms: str) -> str:
    """``"09:01:10"`` -> the transcript timestamp for it."""
    return f"{DATE}T{hms}.000Z"


def git_date(hms: str) -> str:
    return f"{DATE}T{hms}+00:00"


def sha(name: str) -> str:
    return SHAS[name]


def short(name: str) -> str:
    return SHAS[name][:7]


# -- the scenario, said once ----------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One recorded tool call: how it appears in the transcript, and what the store must hold."""

    id: str
    at: str  # the assistant record that made the call
    done: str  # the user record that carries its result
    tool: str
    input: dict
    text: str  # the tool_result block's own content
    result: object = None  # toolUseResult; None renders a record without that key
    ok: bool = True
    path: str | None = None  # what the store's file_path must be
    old: str | None = None
    new: str | None = None
    commit: str | None = None  # SHAS key, when this call is the one that made that commit
    origin: str | None = None  # SHAS key of the commit a cherry-pick copied


@dataclass(frozen=True)
class Turn:
    """One agent's work: a session's main agent (``id`` is None) or one subagent."""

    id: str | None
    session: str
    cwd: str
    steps: tuple[Step, ...]
    started: str = ""
    ended: str = ""
    task: str | None = None
    type: str | None = None
    prompt: str | None = None
    phase: str | None = None
    worktree: str | None = None
    worktree_branch: str | None = None
    spawned_with_worktree: bool = False
    parent_tool_use_id: str | None = None
    workflow_run: str | None = None
    journal_key: str | None = None
    closing: str | None = None
    directory: str = ""  # where its files sit under the projects folder; "" for a main agent


@dataclass(frozen=True)
class CommitSpec:
    name: str  # key in SHAS
    at: str
    subject: str
    where: str  # "main" | "w3" | "api": which checkout it was made in
    files: tuple[tuple[str, str, str], ...]  # (repo-relative path, content after, status)
    agent: str | None = None
    event: str | None = None
    origin: str | None = None
    session: str | None = None


COMMITS = (
    CommitSpec(
        "base",
        "08:50:00",
        "widget: the first commit",
        "main",
        tuple((path, content, "A") for path, content in BASE_FILES),
    ),
    CommitSpec(
        "w3",
        "09:04:20",
        "cli: the command line",
        "w3",
        (("app/cli.py", CLI_V0, "A"),),
        agent=W3,
        event="toolu_w3_commit",
        session=S1,
    ),
    CommitSpec(
        "parser",
        "09:05:30",
        "parser: read the import file",
        "main",
        (("app/parser.py", PARSER_V1, "A"),),
        agent=W1,
        event="toolu_w1_commit",
        session=S1,
    ),
    CommitSpec(
        "store",
        "09:06:30",
        "store: keep the rows in sqlite",
        "main",
        (("app/store.py", STORE_V0, "A"),),
        agent=W2,
        event="toolu_w2_commit",
        session=S1,
    ),
    CommitSpec(
        "schema",
        "09:07:30",
        "schema: the generated tables",
        "main",
        (
            ("app/gen_a.py", GEN_A_V0, "A"),
            ("app/gen_b.py", GEN_B_V0, "A"),
            ("app/schema.py", SCHEMA_V0, "A"),
        ),
        agent=W4,
        event="toolu_w4_commit",
        session=S1,
    ),
    CommitSpec(
        "utilcore",
        "09:14:30",
        "verify: tighten util and core",
        "main",
        (("app/core.py", CORE_V1, "M"), ("app/util.py", UTIL_V3, "M")),
        agent=W6,
        event="toolu_w6_commit",
        session=S1,
    ),
    CommitSpec(
        "cp",
        "09:16:00",
        "cli: the command line",
        "main",
        (("app/cli.py", CLI_V0, "A"),),
        agent=W3,
        event="toolu_cp",
        origin="w3",
        session=S1,
    ),
    CommitSpec(
        "guide",
        "09:35:30",
        "guide: explain the import file",
        "main",
        (("docs/guide.md", GUIDE_V1, "M"),),
        agent=A1,
        event="toolu_a1_commit",
        session=S1,
    ),
    CommitSpec(
        "a2",
        "09:39:00",
        "api: serve the rows over http",
        "api",
        (("app/api.py", API_V1, "A"), ("tests/test_api.py", TEST_API_V1, "A")),
        agent=A2,
        event="toolu_a2_commit",
        session=S1,
    ),
    CommitSpec(
        "unrec",
        "09:41:00",
        "widget: bump the version",
        "main",
        (("pyproject.toml", PYPROJECT_V1, "M"),),
    ),
)

# A worktree is added right after the commit its branch must point at.
WORKTREES = {"base": (WT_REL, W3_BRANCH), "cp": ("", API_BRANCH)}


def _created_hunk(content: str) -> dict:
    lines = content.splitlines()
    return {
        "oldStart": 0,
        "oldLines": 0,
        "newStart": 1,
        "newLines": len(lines),
        "lines": ["+" + line for line in lines],
    }


def _write_result(path: str, content: str) -> dict:
    return {"type": "create", "filePath": path, "content": content, "structuredPatch": []}


def _edit_step(
    ident: str,
    at: str,
    done: str,
    path: str,
    old: str,
    new: str,
    before: str,
    after: str,
    stored: str,
    absolute: str = "",
) -> Step:
    """An Edit. ``path`` is the recorded input, ``absolute`` the path the result names when they
    differ (a relative input only resolves against the recorded cwd), ``stored`` the store's value."""
    return Step(
        id=ident,
        at=at,
        done=done,
        tool="Edit",
        input={"file_path": path, "old_string": old, "new_string": new, "replace_all": False},
        text=f"The file {absolute or path} has been updated successfully.",
        result=edit_result(absolute or path, old, new, before),
        path=stored,
        old=before,
        new=after,
    )


def _commit_step(ident: str, at: str, done: str, name: str, paths: str, structured: bool = True) -> Step:
    """``git add … && git commit -q … && git log --oneline -1``, in either recorded response shape.

    ``paths`` is what the recorded command staged: ``-A`` for w1, which is what agents usually
    type, and explicit paths for the rest, because these agents share one checkout and a blanket
    ``-A`` would have swept a concurrent agent's files into the commit. ``build_repo`` stages the
    commit's own files either way, so the recorded command and the real repo never disagree."""
    spec = next(c for c in COMMITS if c.name == name)
    line = f"{short(name)} {spec.subject}"
    command = f'git add {paths} && git commit -q -m "{spec.subject}" && git log --oneline -1'
    return Step(
        id=ident,
        at=at,
        done=done,
        tool="Bash",
        input={"command": command, "description": "Commit the work"},
        text=line,
        result=bash_ok(line) if structured else None,
        commit=name,
    )


def _check_step(ident: str, at: str, done: str, output: str, ok: bool = True) -> Step:
    return Step(
        id=ident,
        at=at,
        done=done,
        tool="Bash",
        input={"command": "uv run pytest -q", "description": "Run the tests"},
        text=output,
        result=bash_ok(output) if ok else f"Error: {output}",
        ok=ok,
    )


def _handback(ident: str, at: str, done: str, message: str) -> Step:
    return Step(
        id=ident,
        at=at,
        done=done,
        tool="SubagentHandback",
        input={"message": message},
        text=message,
        result={"success": True, "message": message},
    )


def _task_update(ident: str, at: str, done: str, task_id: str, old: str, new: str) -> Step:
    return Step(
        id=ident,
        at=at,
        done=done,
        tool="TaskUpdate",
        input={"taskId": task_id, "status": new},
        text=f"Task {task_id} is {new}",
        result={
            "success": True,
            "taskId": task_id,
            "updatedFields": ["status"],
            "statusChange": {"from": old, "to": new},
        },
    )


def _agent_step(
    ident: str, at: str, done: str, agent_id: str, description: str, prompt: str, worktree: bool = False
) -> Step:
    tool_input = {"description": description, "subagent_type": "general-purpose", "prompt": prompt}
    if worktree:
        tool_input["isolation"] = "worktree"
    return Step(
        id=ident,
        at=at,
        done=done,
        tool="Agent",
        input=tool_input,
        text=f"{description}: done.",
        result={
            "isAsync": False,
            "status": "completed",
            "agentId": agent_id,
            "description": description,
            "resolvedModel": MODEL,
            "prompt": prompt,
            "outputFile": f"/home/dev/.claude/agent-output/agent-{agent_id}.md",
            "canReadOutputFile": True,
        },
    )


def _workflow_turn(agent: str, **kwargs) -> Turn:
    return Turn(
        id=agent,
        session=S1,
        type="workflow-agent",
        workflow_run=RUN,
        journal_key=JOURNAL_KEYS[agent],
        directory=f"{S1}/subagents/workflows/{RUN}",
        **kwargs,
    )


def _scenario(root: str, elsewhere: str) -> tuple[Turn, ...]:
    """Every agent of the run, in a stable order: S1's main agent, its eight subagents, then S2's."""
    wt3 = f"{root}/{WT_REL}"
    plain = f"{S1}/subagents"

    main1 = Turn(
        id=None,
        session=S1,
        cwd=root,
        started="09:00:05",
        ended="09:42:00",
        steps=(
            *(
                Step(
                    id=f"toolu_tc{n}",
                    at=f"09:00:{20 + 5 * (n - 1):02d}",
                    done=f"09:00:{21 + 5 * (n - 1):02d}",
                    tool="TaskCreate",
                    input={"subject": subject, "description": subject, "activeForm": active},
                    text=f"Created task {tid}",
                    result={"task": {"id": tid, "subject": subject}},
                )
                for n, (tid, subject, active) in enumerate(TASKS, start=1)
            ),
            _task_update("toolu_tu1", "09:00:35", "09:00:36", "task-1", "pending", "in_progress"),
            Step(
                id="toolu_wf",
                at="09:01:00",
                done="09:15:20",
                tool="Workflow",
                input={"script": WORKFLOW_SCRIPT},
                text="Six agents finished.",
                result={
                    "status": "completed",
                    "taskId": "task-1",
                    "taskType": "workflow",
                    "workflowName": "build-the-tool",
                    "runId": RUN,
                    "summary": "Four agents built the modules, two verified them.",
                    "transcriptDir": (
                        f"/home/dev/.claude/projects/{project_dir_name(Path(root))}"
                        f"/{S1}/subagents/workflows/{RUN}"
                    ),
                    "scriptPath": f"{root}/.claude/workflows/build-the-tool.py",
                },
            ),
            _task_update("toolu_tu2", "09:09:10", "09:09:11", "task-2", "pending", "in_progress"),
            _task_update("toolu_tu3", "09:15:25", "09:15:26", "task-1", "in_progress", "completed"),
            _task_update("toolu_tu4", "09:15:35", "09:15:36", "task-2", "in_progress", "completed"),
            Step(
                id="toolu_cp",
                at="09:16:00",
                done="09:16:04",
                tool="Bash",
                input={
                    "command": f"git cherry-pick {short('w3')}",
                    "description": "Take the CLI onto main",
                },
                text=f"[main {short('cp')}] cli: the command line",
                result=bash_ok(
                    f"[main {short('cp')}] cli: the command line\n"
                    " Date: Mon Mar 2 09:04:20 2026 +0000\n"
                    " 1 file changed, 8 insertions(+)\n"
                    " create mode 100644 app/cli.py"
                ),
                commit="cp",
                origin="w3",
            ),
            _task_update("toolu_tu5", "09:29:50", "09:29:51", "task-3", "pending", "in_progress"),
            _agent_step("toolu_ag1", "09:30:00", "09:36:10", A1, "Write the user guide", TASK_A1),
            _agent_step("toolu_ag2", "09:30:05", "09:40:20", A2, "Add the HTTP API", TASK_A2, worktree=True),
            _task_update("toolu_tu6", "09:40:30", "09:40:31", "task-3", "in_progress", "completed"),
        ),
    )

    w1 = _workflow_turn(
        W1,
        cwd=root,
        task="Build the parser",
        prompt=TASK_W1,
        phase="Build",
        started="09:01:10",
        ended="09:06:00",
        closing=CLOSE_W1,
        steps=(
            Step(
                id="toolu_w1_write",
                at="09:01:40",
                done="09:01:41",
                tool="Write",
                input={"file_path": f"{root}/app/parser.py", "content": PARSER_V0},
                text=f"File created successfully at: {root}/app/parser.py",
                result=_write_result(f"{root}/app/parser.py", PARSER_V0),
                path="app/parser.py",
                new=PARSER_V0,
            ),
            _check_step(
                "toolu_w1_check1",
                "09:03:00",
                "09:03:20",
                "Exit code 1\nFAILED tests/test_parser.py::test_blank - IndexError",
                ok=False,
            ),
            _edit_step(
                "toolu_w1_edit",
                "09:04:00",
                "09:04:01",
                f"{root}/app/parser.py",
                "text.splitlines()]",
                "text.splitlines() if line.strip()]",
                PARSER_V0,
                PARSER_V1,
                "app/parser.py",
            ),
            _check_step("toolu_w1_check2", "09:05:00", "09:05:10", "3 passed in 0.12s"),
            _commit_step("toolu_w1_commit", "09:05:30", "09:05:35", "parser", "-A"),
            _handback("toolu_w1_back", "09:05:50", "09:06:00", CLOSE_W1),
        ),
    )

    store_diff = {
        "changedFiles": [f"{root}/app/store.py"],
        "files": [
            {
                "filePath": f"{root}/app/store.py",
                "created": True,
                "hunks": [_created_hunk(STORE_V0)],
            }
        ],
        "moreFiles": 0,
    }
    w2 = _workflow_turn(
        W2,
        cwd=root,
        task="Build the store",
        prompt=TASK_W2,
        phase="Build",
        started="09:01:12",
        ended="09:07:00",
        closing=CLOSE_W2,
        steps=(
            Step(
                id="toolu_w2_heredoc",
                at="09:02:10",
                done="09:02:14",
                tool="Bash",
                input={
                    "command": f"cat > app/store.py <<'EOF'\n{STORE_V0}EOF",
                    "description": "Write the store module",
                },
                text="",
                result={**bash_ok(""), "bashEditDiff": store_diff},
            ),
            _check_step("toolu_w2_check", "09:05:40", "09:05:50", "4 passed in 0.14s"),
            _commit_step(
                "toolu_w2_commit", "09:06:30", "09:06:36", "store", "app/store.py", structured=False
            ),
            _handback("toolu_w2_back", "09:06:50", "09:07:00", CLOSE_W2),
        ),
    )

    w3 = _workflow_turn(
        W3,
        cwd=wt3,
        task="Build the CLI",
        prompt=TASK_W3,
        phase="Build",
        worktree=wt3,
        worktree_branch=W3_BRANCH,
        spawned_with_worktree=True,
        started="09:01:14",
        ended="09:05:20",
        closing=CLOSE_W3,
        steps=(
            Step(
                id="toolu_w3_write",
                at="09:02:30",
                done="09:02:32",
                tool="Write",
                input={"file_path": f"{wt3}/app/cli.py", "content": CLI_V0},
                text=f"File created successfully at: {wt3}/app/cli.py",
                result=_write_result(f"{wt3}/app/cli.py", CLI_V0),
                path="app/cli.py",
                new=CLI_V0,
            ),
            _commit_step("toolu_w3_commit", "09:04:20", "09:04:26", "w3", "app/cli.py"),
            _handback("toolu_w3_back", "09:05:10", "09:05:20", CLOSE_W3),
        ),
    )

    schema_diff = {
        "changedFiles": [f"{root}/app/schema.py"],
        "files": [
            {
                "filePath": f"{root}/app/schema.py",
                "created": True,
                "hunks": [_created_hunk(SCHEMA_V0)],
            }
        ],
        "moreFiles": 2,
    }
    w4 = _workflow_turn(
        W4,
        cwd=root,
        task="Generate the schema",
        prompt=TASK_W4,
        phase="Build",
        started="09:02:00",
        ended="09:08:00",
        closing=CLOSE_W4,
        steps=(
            Step(
                id="toolu_w4_gen",
                at="09:03:30",
                done="09:03:40",
                tool="Bash",
                input={"command": "python scripts/gen.py", "description": "Generate the schema"},
                text="generated 3 files",
                result={**bash_ok("generated 3 files"), "bashEditDiff": schema_diff},
            ),
            _commit_step(
                "toolu_w4_commit",
                "09:07:30",
                "09:07:36",
                "schema",
                "app/schema.py app/gen_a.py app/gen_b.py",
            ),
            _handback("toolu_w4_back", "09:07:50", "09:08:00", CLOSE_W4),
        ),
    )

    w5 = _workflow_turn(
        W5,
        cwd=root,
        task="Verify util",
        prompt=TASK_W5,
        phase="Verify",
        started="09:10:00",
        ended="09:14:00",
        closing=CLOSE_W5,
        steps=(
            _edit_step(
                "toolu_w5_edit1",
                "09:11:00",
                "09:11:02",
                f"{root}/app/util.py",
                "return text.lower()",
                "return text.strip().lower()",
                UTIL_V0,
                UTIL_V1,
                "app/util.py",
            ),
            _edit_step(
                "toolu_w5_edit2",
                "09:13:00",
                "09:13:02",
                f"{root}/app/util.py",
                "def slug(text):",
                "def slug(text: str) -> str:",
                UTIL_V2,
                UTIL_V3,
                "app/util.py",
            ),
            _handback("toolu_w5_back", "09:13:50", "09:14:00", CLOSE_W5),
        ),
    )

    core_diff = {
        "changedFiles": [f"{root}/app/core.py"],
        "files": [
            {
                "filePath": f"{root}/app/core.py",
                "hunks": [
                    {
                        "oldStart": 1,
                        "oldLines": 1,
                        "newStart": 1,
                        "newLines": 1,
                        "lines": ['-VERSION = "0.1.0"', '+VERSION = "0.2.0"'],
                    }
                ],
            }
        ],
        "moreFiles": 0,
        "shared": True,
    }
    w6 = _workflow_turn(
        W6,
        cwd=root,
        task="Verify core",
        prompt=TASK_W6,
        phase="Verify",
        started="09:10:05",
        ended="09:15:00",
        closing=CLOSE_W6,
        steps=(
            _edit_step(
                "toolu_w6_edit",
                "09:12:00",
                "09:12:02",
                f"{root}/app/util.py",
                "return max(low, min(value, high))",
                "return min(max(value, low), high)",
                UTIL_V1,
                UTIL_V2,
                "app/util.py",
            ),
            Step(
                id="toolu_w6_sed",
                at="09:13:30",
                done="09:13:34",
                tool="Bash",
                input={
                    "command": "sed -i '' 's/0\\.1\\.0/0.2.0/' app/core.py",
                    "description": "Bump the version in core",
                },
                text="",
                result={**bash_ok(""), "bashEditDiff": core_diff},
            ),
            _commit_step("toolu_w6_commit", "09:14:30", "09:14:36", "utilcore", "app/util.py app/core.py"),
            _handback("toolu_w6_back", "09:14:50", "09:15:00", CLOSE_W6),
        ),
    )

    a1 = Turn(
        id=A1,
        session=S1,
        cwd=root,
        task="Write the user guide",
        type="general-purpose",
        prompt=TASK_A1,
        parent_tool_use_id="toolu_ag1",
        started="09:30:10",
        ended="09:36:00",
        closing=CLOSE_A1,
        directory=plain,
        steps=(
            _edit_step(
                "toolu_a1_edit",
                "09:31:20",
                "09:31:22",
                f"{root}/docs/guide.md",
                "To be written.",
                GUIDE_LINE,
                GUIDE_V0,
                GUIDE_V1,
                "docs/guide.md",
            ),
            Step(
                id="toolu_a1_outside",
                at="09:33:00",
                done="09:33:02",
                tool="Write",
                input={"file_path": "/home/dev/notes/plan.md", "content": PLAN_MD},
                text="File created successfully at: /home/dev/notes/plan.md",
                result=_write_result("/home/dev/notes/plan.md", PLAN_MD),
                path="/home/dev/notes/plan.md",
            ),
            Step(
                id="toolu_a1_push",
                at="09:34:00",
                done="09:34:02",
                tool="Bash",
                input={"command": "git push origin main", "description": "Publish the guide"},
                text=DENIAL,
                result=f"Error: {DENIAL}",
                ok=False,
            ),
            _commit_step("toolu_a1_commit", "09:35:30", "09:35:36", "guide", "docs/guide.md"),
            _handback("toolu_a1_back", "09:35:50", "09:36:00", CLOSE_A1),
        ),
    )

    a2 = Turn(
        id=A2,
        session=S1,
        cwd=elsewhere,
        task="Add the HTTP API",
        type="general-purpose",
        prompt=TASK_A2,
        parent_tool_use_id="toolu_ag2",
        worktree=elsewhere,
        worktree_branch=API_BRANCH,
        spawned_with_worktree=True,
        started="09:30:15",
        ended="09:40:00",
        closing=CLOSE_A2,
        directory=plain,
        steps=(
            Step(
                id="toolu_a2_write",
                at="09:31:00",
                done="09:31:03",
                tool="Write",
                input={"file_path": f"{elsewhere}/app/api.py", "content": API_V0},
                text=f"File created successfully at: {elsewhere}/app/api.py",
                result=_write_result(f"{elsewhere}/app/api.py", API_V0),
                path="app/api.py",
                new=API_V0,
            ),
            Step(
                id="toolu_a2_test",
                at="09:33:40",
                done="09:33:43",
                tool="Write",
                input={"file_path": f"{elsewhere}/tests/test_api.py", "content": TEST_API_V0},
                text=f"File created successfully at: {elsewhere}/tests/test_api.py",
                result=_write_result(f"{elsewhere}/tests/test_api.py", TEST_API_V0),
                path="tests/test_api.py",
                new=TEST_API_V0,
            ),
            # the recorded file_path is relative here: it only resolves against the recorded cwd
            _edit_step(
                "toolu_a2_edit",
                "09:35:00",
                "09:35:03",
                "tests/test_api.py",
                TEST_OLD,
                TEST_NEW,
                TEST_API_V0,
                TEST_API_V1,
                "tests/test_api.py",
                absolute=f"{elsewhere}/tests/test_api.py",
            ),
            _commit_step("toolu_a2_commit", "09:39:00", "09:39:06", "a2", "app/api.py tests/test_api.py"),
            _handback("toolu_a2_back", "09:39:50", "09:40:00", CLOSE_A2),
        ),
    )

    main2 = Turn(
        id=None,
        session=S2,
        cwd=elsewhere,
        started="09:32:00",
        ended="09:38:00",
        steps=(
            _edit_step(
                "toolu_s2_edit",
                "09:34:00",
                "09:34:03",
                f"{elsewhere}/app/api.py",
                API_OLD,
                API_NEW,
                API_V0,
                API_V1,
                "app/api.py",
            ),
            _agent_step("toolu_s2_agent", "09:35:30", "09:37:40", SH, "Lint the API", TASK_SH),
        ),
    )

    helper = Turn(
        id=SH,
        session=S2,
        cwd=elsewhere,
        task="Lint the API",
        type="general-purpose",
        prompt=TASK_SH,
        parent_tool_use_id="toolu_s2_agent",
        worktree=elsewhere,
        worktree_branch=API_BRANCH,
        started="09:36:00",
        ended="09:37:30",
        closing=CLOSE_SH,
        directory=f"{S2}/subagents",
        steps=(
            Step(
                id="toolu_sh_lint",
                at="09:36:30",
                done="09:36:40",
                tool="Bash",
                input={"command": "uv run ruff check", "description": "Lint the API"},
                text="All checks passed!",
                result=bash_ok("All checks passed!"),
            ),
            _handback("toolu_sh_back", "09:37:20", "09:37:30", CLOSE_SH),
        ),
    )

    return (main1, w1, w2, w3, w4, w5, w6, a1, a2, main2, helper)


# -- transcripts ----------------------------------------------------------------------------------


def _record(turn: Turn, kind: str, hms: str, **extra) -> dict:
    record = {
        "parentUuid": None,
        "isSidechain": turn.id is not None,
        "userType": "external",
        "cwd": turn.cwd,
        "sessionId": turn.session,
        "version": "2.1.274",
        "gitBranch": "main",  # contaminated on purpose: w3 and a2 are not on main
        "type": kind,
        "uuid": f"u-{turn.id or 'main'}-{hms.replace(':', '')}",
        "timestamp": stamp(hms),
    }
    if turn.id is not None:
        record["agentId"] = turn.id
    record.update(extra)
    return record


def _step_records(turn: Turn, step: Step) -> list[dict]:
    block = {"tool_use_id": step.id, "type": "tool_result", "content": step.text}
    if not step.ok:
        block["is_error"] = True
    result = _record(
        turn,
        "user",
        step.done,
        promptId=PROMPT_ID[turn.session],
        message={"role": "user", "content": [block]},
    )
    if step.result is not None:
        result["toolUseResult"] = step.result
    call = _record(
        turn,
        "assistant",
        step.at,
        requestId=f"req-{step.id}",
        message={
            "model": MODEL,
            "id": f"msg-{step.id}",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "tool_use", "id": step.id, "name": step.tool, "input": step.input}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
    )
    return [call, result]


def _turn_records(turn: Turn) -> list[dict]:
    opening = {"promptSource": "typed", "origin": {"kind": "human"}} if turn.id is None else {}
    text = PROMPT_TEXT[turn.session] if turn.id is None else turn.prompt
    records = [
        _record(
            turn,
            "user",
            turn.started,
            promptId=PROMPT_ID[turn.session],
            message={"role": "user", "content": text},
            **opening,
        )
    ]
    for step in turn.steps:
        records.extend(_step_records(turn, step))
    if turn.id is None:
        records.append(
            _record(
                turn,
                "assistant",
                turn.ended,
                message={
                    "role": "assistant",
                    "content": [{"type": "text", "text": FINAL_TEXT[turn.session]}],
                },
            )
        )
    return records


def _meta(turn: Turn) -> dict:
    """The ``agent-<id>.meta.json`` sibling. A Workflow agent has no ``toolUseId``: only the
    ``wf_`` directory name, which is the parent Workflow call's ``runId``, ties it to that call."""
    if turn.workflow_run:
        meta = {
            "agentType": turn.type,
            "description": turn.task,
            "requestNonInteractive": True,
            "requestShape": "prompt",
            "spawnDepth": 1,
            "workflowPhase": turn.phase,
        }
    else:
        meta = {
            "agentType": turn.type,
            "description": turn.task,
            "toolUseId": turn.parent_tool_use_id,
            "spawnDepth": 1,
            "requestShape": "prompt",
            "requestNonInteractive": True,
        }
    if turn.spawned_with_worktree:
        meta["spawnedWithWorktree"] = True
        meta["worktreePath"] = turn.worktree
        if not turn.workflow_run:
            meta["worktreeBranch"] = turn.worktree_branch
    return meta


def _journal(turns: tuple[Turn, ...]) -> str:
    """The Workflow run's journal: starts, then results as they came back. It holds no labels."""
    workflow = [t for t in turns if t.workflow_run]
    lines = [{"type": "started", "agentId": t.id, "key": f"v2:{t.journal_key}"} for t in workflow]
    lines += [
        {"type": "result", "agentId": t.id, "key": f"v2:{t.journal_key}", "result": t.closing}
        for t in sorted(workflow, key=lambda t: t.ended)
    ]
    return "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)


def render(root: str = ROOT, elsewhere: str = ELSEWHERE) -> dict[str, str]:
    """Relative path under a Claude ``projects/`` directory -> file text."""
    turns = _scenario(root, elsewhere)
    folder = {S1: project_dir_name(Path(root)), S2: project_dir_name(Path(elsewhere))}
    out: dict[str, str] = {}
    for turn in turns:
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in _turn_records(turn))
        if turn.id is None:
            out[f"{folder[turn.session]}/{turn.session}.jsonl"] = text
            continue
        stem = f"{folder[turn.session]}/{turn.directory}/agent-{turn.id}"
        out[f"{stem}.jsonl"] = text
        out[f"{stem}.meta.json"] = json.dumps(_meta(turn), ensure_ascii=False, indent=2) + "\n"
    out[f"{folder[S1]}/{S1}/subagents/workflows/{RUN}/journal.jsonl"] = _journal(turns)
    return dict(sorted(out.items()))


# -- hook events ----------------------------------------------------------------------------------


def hook_events(root: str = ROOT, elsewhere: str = ELSEWHERE) -> list[tuple[str, dict]]:
    """Session S2 as the live hooks would deliver it: (timestamp, hook event), in time order."""
    turns = _scenario(root, elsewhere)
    main = next(t for t in turns if t.session == S2 and t.id is None)
    helper = next(t for t in turns if t.session == S2 and t.id is not None)
    events: list[tuple[str, dict]] = [
        (
            stamp("09:31:55"),
            {"hook_event_name": "SessionStart", "session_id": S2, "cwd": elsewhere, "source": "startup"},
        ),
        (
            stamp(main.started),
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": S2,
                "cwd": elsewhere,
                "prompt": PROMPT_TEXT[S2],
                "prompt_id": P2,
            },
        ),
        (
            stamp("09:35:35"),
            {
                "hook_event_name": "SubagentStart",
                "session_id": S2,
                "cwd": elsewhere,
                "agent_id": helper.id,
                "agent_type": helper.type,
            },
        ),
        (
            stamp("09:37:35"),
            {
                "hook_event_name": "SubagentStop",
                "session_id": S2,
                "cwd": elsewhere,
                "agent_id": helper.id,
                "agent_type": helper.type,
            },
        ),
        (stamp(main.ended), {"hook_event_name": "Stop", "session_id": S2, "cwd": elsewhere}),
    ]
    for turn in (main, helper):
        for step in turn.steps:
            event = {
                "hook_event_name": "PostToolUse",
                "session_id": S2,
                "cwd": turn.cwd,
                "prompt_id": P2,
                "tool_name": step.tool,
                "tool_input": step.input,
                "tool_response": step.result if step.result is not None else {"content": step.text},
                "tool_use_id": step.id,
            }
            if turn.id is not None:
                event["agent_id"] = turn.id
            events.append((stamp(step.done), event))
    return sorted(events, key=lambda pair: (pair[0], pair[1]["hook_event_name"]))


# -- the git repo ---------------------------------------------------------------------------------


def _git_env(at: str) -> dict[str, str]:
    """A git environment with nothing of this machine in it, and one fixed time."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME=AUTHOR[0],
        GIT_AUTHOR_EMAIL=AUTHOR[1],
        GIT_COMMITTER_NAME=AUTHOR[0],
        GIT_COMMITTER_EMAIL=AUTHOR[1],
        GIT_AUTHOR_DATE=git_date(at),
        GIT_COMMITTER_DATE=git_date(at),
        LC_ALL="C",
        TZ="UTC",
    )
    return env


def _git(cwd: Path, *args: str, at: str = "08:50:00") -> str:
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env=_git_env(at),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def build_repo(path: Path, elsewhere: Path) -> dict[str, str]:
    """Create the scenario's repo at ``path``, with both worktrees. Returns name -> full SHA.

    The SHAs do not depend on ``path``: identity, dates, message and content are all fixed, and no
    global or system git config is read.
    """
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    trees = {"main": path, "api": elsewhere, "w3": path / WT_REL}
    built: dict[str, str] = {}
    for spec in COMMITS:
        tree = trees[spec.where]
        if spec.origin:  # a cherry-pick keeps the origin's author and patch
            _git(path, "cherry-pick", built[spec.origin], at=spec.at)
        else:
            for rel, content, _ in spec.files:
                target = tree / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            _git(tree, "add", "--", *[rel for rel, _, _ in spec.files], at=spec.at)
            _git(tree, "commit", "-q", "-m", spec.subject, at=spec.at)
        built[spec.name] = _git(tree, "rev-parse", "HEAD", at=spec.at)
        if spec.name in WORKTREES:
            rel, branch = WORKTREES[spec.name]
            target = (path / rel) if rel else elsewhere
            _git(path, "worktree", "add", "-q", "-b", branch, str(target), at=spec.at)
    return built


# -- ground truth ---------------------------------------------------------------------------------


def _stored(step: Step) -> tuple[dict, object]:
    """What the store keeps for a call. Outside the repo, only the path survives: the contents of
    a file that is not ours may be credentials."""
    response = step.result if step.result is not None else {"content": step.text}
    if step.path and os.path.isabs(step.path):
        keep = {k: v for k, v in step.input.items() if k in ("file_path", "notebook_path")}
        return keep, None if step.ok else response
    return step.input, response


def _tool_events(turns: tuple[Turn, ...]) -> list[ToolEvent]:
    events = [
        ToolEvent(
            id=step.id,
            session_id=turn.session,
            prompt_id=PROMPT_ID[turn.session],
            timestamp=stamp(step.at),
            tool=step.tool,
            input=_stored(step)[0],
            response=_stored(step)[1],
            success=step.ok,
            agent_id=turn.id,
            file_path=step.path,
            old_content=step.old,
            new_content=step.new,
            cwd=turn.cwd,
        )
        for turn in turns
        for step in turn.steps
    ]
    return sorted(events, key=lambda e: (e.session_id, e.timestamp, e.id))


def _agents(turns: tuple[Turn, ...]) -> list[Agent]:
    return [
        Agent(
            id=turn.id,
            session_id=turn.session,
            parent_tool_use_id=turn.parent_tool_use_id,
            parent_agent_id=None,  # every subagent here was spawned by its session's main agent
            type=turn.type,
            task=turn.task,
            prompt=turn.prompt,
            cwd=turn.cwd,
            worktree=turn.worktree,
            workflow_run=turn.workflow_run,
            phase=turn.phase,
            label=None,  # the journal holds no labels
            depth=1,
            started_at=stamp(turn.started),
            ended_at=stamp(turn.ended),
            closing=turn.closing,
            source="claude-code",
        )
        for turn in turns
        if turn.id is not None
    ]


def _commits() -> list[Commit]:
    return [
        Commit(
            sha=sha(spec.name),
            committed_at=stamp(spec.at),
            subject=spec.subject,
            session_id=spec.session,
            agent_id=spec.agent,
            event_id=spec.event,
            origin_sha=sha(spec.origin) if spec.origin else None,
            files=[(rel, status) for rel, _, status in spec.files],
        )
        for spec in COMMITS
        if spec.name != "base"  # the repo's first commit is older than either session
    ]


GRADES = {
    "app/parser.py": "edit",
    "app/cli.py": "edit",
    "app/util.py": "edit",
    "docs/guide.md": "edit",
    "app/api.py": "edit",
    "tests/test_api.py": "edit",
    "app/store.py": "shell",
    "app/schema.py": "shell",
    "app/core.py": "shell",
    "app/gen_a.py": "commit",
    "app/gen_b.py": "commit",
    "pyproject.toml": "window",
}


def _coverage() -> dict[str, int]:
    paths = {rel for spec in COMMITS if spec.name != "base" for rel, _, _ in spec.files}
    grades = [GRADES[path] for path in sorted(paths)]
    return {
        "committed_files": len(paths),
        "edit": grades.count("edit"),
        "shell": grades.count("shell"),
        "commit": grades.count("commit"),
        "window": grades.count("window"),
        "nothing": grades.count("window") + grades.count("unknown"),
    }


def expected(root: str = ROOT, elsewhere: str = ELSEWHERE) -> dict:
    """The ground truth a correct ingester must reach from ``render()`` plus ``build_repo()``."""
    turns = _scenario(root, elsewhere)
    return {
        "agents": _agents(turns),
        "commits": _commits(),
        "events": [
            {
                "id": e.id,
                "session_id": e.session_id,
                "agent_id": e.agent_id,
                "tool": e.tool,
                "timestamp": e.timestamp,
                "file_path": e.file_path,
                "cwd": e.cwd,
                "success": e.success,
            }
            for e in _tool_events(turns)
        ],
        "coverage": {S1: _coverage()},
        "notes": {
            "grades": dict(GRADES),
            "windows": {
                S1: (stamp("09:00:05"), stamp("09:42:00")),
                S2: (stamp("09:32:00"), stamp("09:38:00")),
            },
            "idle_gap": (stamp("09:16:04"), stamp("09:29:50")),
            "collisions": [
                {"path": "app/util.py", "agents": [W5, W6], "cross_session": False},
                {"path": "app/api.py", "agents": [A2, None], "cross_session": True},
            ],
            "refused": [{"event": "toolu_a1_push", "agent": A1, "reason": "auto mode classifier"}],
            "failed_then_passed": {
                "agent": W1,
                "failed": "toolu_w1_check1",
                "passed": "toolu_w1_check2",
            },
            "outside_repo_writes": ["/home/dev/notes/plan.md"],
            "omitted_more_files": 2,
            "shared_diff_events": ["toolu_w6_sed"],
            "unrecorded_commits": [sha("unrec")],
            "worktrees": {W3: f"{root}/{WT_REL}", A2: elsewhere, SH: elsewhere},
            "branches": {"w3": W3_BRANCH, "a2": API_BRANCH},
            "tasks": [{"id": tid, "subject": subject} for tid, subject, _ in TASKS],
        },
    }


def load(store, root: str = ROOT, elsewhere: str = ELSEWHERE) -> None:
    """Write the ground truth straight into an open Store: no parsing, no git, no clock."""
    turns = _scenario(root, elsewhere)
    heads = {S1: sha("base"), S2: sha("cp")}  # git HEAD when each session started
    with store.transaction():
        for sid in (S1, S2):
            main = next(t for t in turns if t.session == sid and t.id is None)
            store.upsert_session(
                Session(
                    id=sid,
                    repo=root,
                    started_at=stamp(main.started),
                    ended_at=stamp(main.ended),
                    head_at_start=heads[sid],
                    source="backfill",
                )
            )
            store.add_prompt(
                Prompt(
                    id=PROMPT_ID[sid],
                    session_id=sid,
                    ordinal=1,
                    timestamp=stamp(main.started),
                    text=PROMPT_TEXT[sid],
                )
            )
        for agent in _agents(turns):
            store.upsert_agent(agent)
        for event in _tool_events(turns):
            store.add_event(event)
        for commit in _commits():
            store.add_commit(commit)


def main() -> None:
    for rel, text in render().items():
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
