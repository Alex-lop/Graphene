"""Replay Codex 0.167.2's live PreToolUse payload, including multi-file patches."""

import json

import pytest
import test_every_agent as E

from graphene_map import hooks
from graphene_map.store import Store


@pytest.fixture
def repo(tmp_path, monkeypatch):
    return E.repo.__wrapped__(tmp_path, monkeypatch)


def patch(repo, command, sid=E.SID):
    return E.hook(repo, "PreToolUse", session=sid, tool_name="apply_patch", tool_input={"command": command})


@pytest.mark.parametrize("operation", ["Add", "Update", "Delete"])
def test_patch_checks_every_path_before_any_write(repo, operation):
    E.hold(repo)
    command = f"*** Begin Patch\n*** {operation} File: outside.txt\n+x\n*** End Patch"
    assert E.verdict(patch(repo, command)) == "deny"
    assert not (repo / "outside.txt").exists()


def test_a_patch_inside_the_files_passes_and_a_move_checks_its_destination(repo):
    E.hold(repo)
    assert patch(repo, "*** Begin Patch\n*** Update File: inside.txt\n@@\n-i\n+ok\n*** End Patch") is None
    move = "*** Begin Patch\n*** Update File: inside.txt\n*** Move to: outside.txt\n@@\n-i\n+x\n*** End Patch"
    assert E.verdict(patch(repo, move)) == "deny"
    mixed = "*** Begin Patch\n*** Add File: inside.txt\n+x\n*** Add File: outside.txt\n+x\n*** End Patch"
    assert E.verdict(patch(repo, mixed)) == "deny"


def test_codex_run_matches_its_hold_without_changing_direct_session_ids(repo, monkeypatch):
    E.hold(repo)
    command = "*** Begin Patch\n*** Update File: inside.txt\n@@\n-i\n+x\n*** End Patch"
    monkeypatch.setenv("GRAPHENE_EXECUTOR", "codex")
    monkeypatch.setenv("GRAPHENE_NODE", "n1")
    monkeypatch.setenv("GRAPHENE_ATTEMPT", E.SID)
    assert patch(repo, command, sid="live-codex-id") is None
    assert (
        E.hook(
            repo,
            "PreToolUse",
            session="live-codex-id",
            tool_name="Bash",
            tool_input={"command": "echo ok > inside.txt"},
        )
        is None
    )
    monkeypatch.delenv("GRAPHENE_ATTEMPT")
    assert E.verdict(patch(repo, command, sid="stranger")) == "deny"


def test_init_installs_codex_hooks_and_remove_keeps_other_handlers(repo):
    from test_plan_cli import person

    assert person("init", "--planner", "codex", "--executor", "codex").exit_code == 0
    path = repo / ".codex/hooks.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == hooks.HOOK_COMMAND
    own = {"hooks": [{"type": "command", "command": "echo other"}]}
    data["hooks"]["PreToolUse"].append(own)
    path.write_text(json.dumps(data))
    assert person("init", "--remove").exit_code == 0
    assert json.loads(path.read_text()) == {"hooks": {"PreToolUse": [own]}}


def test_a_malformed_patch_is_refused(repo):
    E.hold(repo)
    assert E.verdict(patch(repo, "not a patch")) == "deny"


def test_codex_hooks_are_copied_into_task_worktrees(repo):
    from graphene_map.run import worktree_for

    hooks.install_codex_hooks(repo)
    with Store.open(repo) as store:
        tree = worktree_for(store, repo, repo, "n1")
    assert (tree / ".codex/hooks.json").read_bytes() == (repo / ".codex/hooks.json").read_bytes()


def test_patch_cannot_edit_the_store_even_without_a_plan(repo):
    command = "*** Begin Patch\n*** Add File: .graphene/pwn\n+x\n*** End Patch"
    assert E.verdict(patch(repo, command)) == "deny"


def test_codex_install_preserves_other_hooks_and_rejects_invalid_settings(repo):
    path = repo / ".codex/hooks.json"
    path.parent.mkdir()
    path.write_text('{"hooks": {"PreToolUse": [{"hooks": [{"command": "echo other", "type": "command"}]}]}}')
    assert hooks.install_codex_hooks(repo) == ["PreToolUse"]
    data = json.loads(path.read_text())
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo other"
    before = path.read_text()
    assert hooks.install_codex_hooks(repo) == [] and path.read_text() == before
    path.write_text("[]")
    with pytest.raises(ValueError):
        hooks.install_codex_hooks(repo)
    assert path.read_text() == "[]"


def test_captured_codex_payloads_are_refused_before_the_write(repo):
    import io
    from pathlib import Path

    E.hold(repo)
    source = Path(__file__).parent / "fixtures/codex-hooks-0.167.2.json"
    for event in json.loads(source.read_text().replace("<fixture>", str(repo))):
        event["session_id"] = E.SID
        out = io.StringIO()
        assert hooks.hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
        assert E.verdict(json.loads(out.getvalue())) == "deny"
    assert not (repo / "captured.txt").exists() and not (repo / "shell.txt").exists()
