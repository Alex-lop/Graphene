from graphene_map import plan as P
from graphene_map.nemotron import executor
from graphene_map.run import prompt_for

NODE = P.Node("n1", "t", goal="g", scope=["a.py"], check="true")


def test_notes_first_in_order():
    out = prompt_for(NODE, ["first note", "second note"], None)
    lines = out.splitlines()
    assert lines[:3] == ["first note", "second note", ""]
    assert lines[3].startswith("You are doing one leaf")
    assert "sent back with" not in out


def test_no_note_starts_with_sentence():
    assert prompt_for(NODE, [], None).startswith("You are doing one leaf")


def test_release_sentence_names_wants():
    assert "--wants naming that file" in prompt_for(NODE, [], None)


def test_executor_system_names_release_wants_landed_file():
    for word in ("release", "wants", "landed"):
        assert word in executor.SYSTEM


def test_claude_code_takes_the_prompt_after_a_double_dash_so_a_note_may_begin_with_a_dash():
    from graphene_map.run import command_for

    argv = command_for("claude -p --model sonnet", "- the note first\n\nYou are doing one leaf", "S", False)
    assert argv[-3:] == ["S", "--", "- the note first\n\nYou are doing one leaf"]
    assert "--" not in command_for("/tmp/executor.sh", "- note", "S", False)
