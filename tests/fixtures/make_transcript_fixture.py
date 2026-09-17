"""Generate the synthetic Claude Code transcript fixture under tests/fixtures/transcripts.

The record shapes mirror what Claude Code 2.1.27x writes to ~/.claude/projects/<dir>/<session>.jsonl
(observed on real transcripts while building the parser); the content is invented. Run
``uv run python tests/fixtures/make_transcript_fixture.py`` to rewrite the files; a test checks the
checked-in copy matches this script.
"""

from __future__ import annotations

import json
from pathlib import Path

SID = "11111111-2222-4333-8444-555555555555"
AGENT = "a1b2c3d4e5f60718"
CWD = "/home/dev/project"
OUT = Path(__file__).parent / "transcripts"
HELLO_V1 = 'def greet(name):\n    return f"hi {name}"\n'
HELLO_V2 = 'def greet(name):\n    return f"hello {name}"\n'
TEST = "from app.hello import greet\n\n\ndef test_greet():\n    assert greet('x') == 'hello x'\n"
README_OLD = "# Old title\n\nSome words.\n"
README_NEW = "# New title\n\nSome words.\n"


def stamp(minute: int, second: int) -> str:
    return f"2026-03-01T09:{minute:02d}:{second:02d}.000Z"


def base(kind: str, minute: int, second: int, **extra) -> dict:
    record = {
        "parentUuid": None,
        "isSidechain": False,
        "userType": "external",
        "cwd": CWD,
        "sessionId": SID,
        "version": "2.1.274",
        "gitBranch": "main",
        "type": kind,
        "uuid": f"uuid-{minute:02d}{second:02d}",
        "timestamp": stamp(minute, second),
    }
    record.update(extra)
    return record


def user_text(text: str, prompt_id: str, minute: int, second: int, **extra) -> dict:
    return base(
        "user",
        minute,
        second,
        promptId=prompt_id,
        promptSource="typed",
        origin={"kind": "human"},
        message={"role": "user", "content": text},
        **extra,
    )


def tool_use(tool_id: str, name: str, inp: dict, minute: int, second: int, **extra) -> dict:
    return base(
        "assistant",
        minute,
        second,
        requestId=f"req-{tool_id}",
        message={
            "model": "claude-fable-5-1",
            "id": f"msg-{tool_id}",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": inp}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
        **extra,
    )


def tool_result(
    tool_id: str,
    content: str,
    structured,
    prompt_id: str,
    minute: int,
    second: int,
    error: bool = False,
    **extra,
) -> dict:
    block = {"tool_use_id": tool_id, "type": "tool_result", "content": content}
    if error:
        block["is_error"] = True
    return base(
        "user",
        minute,
        second,
        promptId=prompt_id,
        message={"role": "user", "content": [block]},
        toolUseResult=structured,
        **extra,
    )


def bash_ok(stdout: str) -> dict:
    return {"stdout": stdout, "stderr": "", "interrupted": False, "isImage": False, "noOutputExpected": False}


def edit_result(path: str, old: str, new: str, original: str) -> dict:
    return {
        "filePath": path,
        "oldString": old,
        "newString": new,
        "originalFile": original,
        "replaceAll": False,
        "structuredPatch": [],
        "userModified": False,
    }


def main_records() -> list[dict]:
    hello = f"{CWD}/app/hello.py"
    test_path = f"{CWD}/tests/test_hello.py"
    readme = f"{CWD}/README.md"
    outside = "/home/dev/notes/todo.md"
    return [
        {"type": "mode", "mode": "normal", "sessionId": SID},
        {"type": "last-prompt", "leafUuid": "uuid-0000", "sessionId": SID},
        base(
            "attachment",
            0,
            1,
            attachment={
                "type": "hook_success",
                "hookName": "SessionStart:startup",
                "hookEvent": "SessionStart",
                "content": "hello from a hook",
            },
        ),
        base(
            "user",
            0,
            2,
            isMeta=True,
            promptId="p-1",
            message={
                "role": "user",
                "content": "<local-command-caveat>Caveat: local commands.</local-command-caveat>",
            },
        ),
        base(
            "user",
            0,
            2,
            promptId="p-1",
            message={
                "role": "user",
                "content": "<command-name>/model</command-name>\n<command-args></command-args>",
            },
        ),
        user_text("Add a greet function to app/hello.py and a test for it.", "p-1", 0, 5),
        base(
            "assistant",
            0,
            6,
            message={"role": "assistant", "content": [{"type": "text", "text": "Adding it."}]},
        ),
        tool_use("toolu_w1", "Write", {"file_path": hello, "content": HELLO_V1}, 1, 0),
        tool_result(
            "toolu_w1",
            f"File created successfully at: {hello}",
            {"type": "create", "filePath": hello, "content": HELLO_V1, "structuredPatch": []},
            "p-1",
            1,
            1,
        ),
        tool_use("toolu_w2", "Write", {"file_path": test_path, "content": TEST}, 1, 30),
        tool_result(
            "toolu_w2",
            f"File created successfully at: {test_path}",
            {"type": "create", "filePath": test_path, "content": TEST, "structuredPatch": []},
            "p-1",
            1,
            31,
        ),
        tool_use("toolu_b1", "Bash", {"command": "uv run pytest -q", "description": "Run the tests"}, 2, 0),
        tool_result(
            "toolu_b1",
            "Exit code 1\nFAILED tests/test_hello.py::test_greet - AssertionError",
            "Error: Exit code 1\nFAILED tests/test_hello.py::test_greet - AssertionError",
            "p-1",
            2,
            5,
            error=True,
        ),
        tool_use(
            "toolu_e1",
            "Edit",
            {
                "file_path": hello,
                "old_string": 'f"hi {name}"',
                "new_string": 'f"hello {name}"',
                "replace_all": False,
            },
            3,
            0,
        ),
        tool_result(
            "toolu_e1",
            f"The file {hello} has been updated successfully.",
            edit_result(hello, 'f"hi {name}"', 'f"hello {name}"', HELLO_V1),
            "p-1",
            3,
            1,
        ),
        tool_use(
            "toolu_b2", "Bash", {"command": "uv run pytest -q", "description": "Run the tests again"}, 4, 0
        ),
        tool_result("toolu_b2", "1 passed in 0.01s", bash_ok("1 passed in 0.01s"), "p-1", 4, 3),
        base("system", 4, 4, subtype="turn_duration", durationMs=240000, content=""),
        user_text("Run the linter with a subagent and tell me what it finds.", "p-2", 10, 0),
        tool_use(
            "toolu_a1",
            "Agent",
            {"description": "lint", "prompt": "Run ruff and report.", "subagent_type": "general-purpose"},
            10,
            5,
        ),
        tool_result(
            "toolu_a1",
            "All checks passed.",
            {
                "agentId": AGENT,
                "status": "completed",
                "description": "lint",
                "prompt": "Run ruff and report.",
            },
            "p-2",
            10,
            40,
        ),
        tool_use(
            "toolu_q1",
            "AskUserQuestion",
            {
                "questions": [
                    {
                        "question": "Ship it?",
                        "header": "Next",
                        "options": [{"label": "yes", "description": "go"}],
                        "multiSelect": False,
                    }
                ]
            },
            11,
            0,
        ),
        tool_result(
            "toolu_q1",
            "The user doesn't want to proceed with this tool use.",
            "Error: The user doesn't want to proceed with this tool use.",
            "p-2",
            11,
            5,
            error=True,
        ),
        {
            "type": "queue-operation",
            "operation": "enqueue",
            "timestamp": stamp(20, 0),
            "sessionId": SID,
            "content": "Rename the README title, then put it back.",
        },
        user_text("Rename the README title, then put it back.", "p-3", 20, 0),
        tool_use(
            "toolu_e2",
            "Edit",
            {"file_path": readme, "old_string": "# Old title", "new_string": "# New title"},
            20,
            5,
        ),
        tool_result(
            "toolu_e2", "updated", edit_result(readme, "# Old title", "# New title", README_OLD), "p-3", 20, 6
        ),
        tool_use(
            "toolu_e3",
            "Edit",
            {"file_path": readme, "old_string": "# New title", "new_string": "# Old title"},
            20,
            10,
        ),
        tool_result(
            "toolu_e3",
            "updated",
            edit_result(readme, "# New title", "# Old title", README_NEW),
            "p-3",
            20,
            11,
        ),
        tool_use("toolu_w3", "Write", {"file_path": outside, "content": "remember to push\n"}, 21, 0),
        tool_result(
            "toolu_w3",
            f"File created successfully at: {outside}",
            {"type": "create", "filePath": outside, "content": "remember to push\n", "structuredPatch": []},
            "p-3",
            21,
            1,
        ),
        tool_use("toolu_b3", "Bash", {"command": "rm -f scratch.txt"}, 21, 30),
        tool_result("toolu_b3", "", bash_ok(""), "p-3", 21, 31),
        {
            "type": "file-history-snapshot",
            "messageId": "uuid-2131",
            "snapshot": {"messageId": "uuid-2131", "trackedFileBackups": {}, "timestamp": stamp(21, 32)},
            "isSnapshotUpdate": False,
        },
        {"type": "ai-title", "aiTitle": "greet function", "sessionId": SID},
    ]


def subagent_records() -> list[dict]:
    side = {"isSidechain": True, "agentId": AGENT}
    return [
        base(
            "user", 10, 6, promptId="p-2", message={"role": "user", "content": "Run ruff and report."}, **side
        ),
        tool_use("toolu_s1", "Bash", {"command": "uv run ruff check ."}, 10, 10, **side),
        tool_result("toolu_s1", "All checks passed!", bash_ok("All checks passed!"), "p-2", 10, 20, **side),
        base(
            "assistant",
            10,
            30,
            message={"role": "assistant", "content": [{"type": "text", "text": "All checks passed."}]},
            **side,
        ),
    ]


def render() -> dict[Path, str]:
    main = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in main_records())
    sub = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in subagent_records())
    return {OUT / f"{SID}.jsonl": main, OUT / SID / "subagents" / f"agent-{AGENT}.jsonl": sub}


if __name__ == "__main__":
    for path, text in render().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
