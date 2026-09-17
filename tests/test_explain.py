"""Explainers: templates, the claude -p wrapper with a fake subprocess, and the fallback path."""

import json
import subprocess

import pytest

from graphene_debrief.debrief import build_debrief
from graphene_debrief.explain import (
    ClaudeCodeExplainer,
    ExplainError,
    NullExplainer,
    parse_reply,
    pick_explainer,
    template,
)
from graphene_debrief.model import FileChange, Hunk, Prompt, Session, ToolEvent
from graphene_debrief.store import Store


def change(path, effect="modified", added=2, removed=1, symbols=(), strategy="payload"):
    return FileChange(
        path,
        "s",
        "p1",
        effect,
        hunks=[Hunk(1, 1, 1, 2, ["-a", "+b", "+c"])],
        added=added,
        removed=removed,
        strategy=strategy,
        symbols=list(symbols),
    )


def test_templates():
    assert template(change("app/auth.py", "created", 40, 0, ["login", "logout"])) == (
        "Created auth.py with 40 lines, defining login and logout."
    )
    assert template(change("a.py", "created", 3, 0)) == "Created a.py with 3 lines."
    assert template(change("a.py", "deleted", 0, 9)) == "Deleted a.py (9 lines)."
    assert template(change("a.py", "reverted", 0, 0)) == "Edited a.py and then restored it; no net change."
    assert (
        template(change("app/auth.py", symbols=["login"])) == "Edited 1 definition in auth.py: login (+2/−1)."
    )
    assert template(change("app/auth.py", symbols=["a", "b", "c"])) == (
        "Edited 3 definitions in auth.py: a, b and c (+2/−1)."
    )
    assert template(change("notes.md", added=1, removed=0)) == "Changed 1 line in notes.md (+1/−0)."
    assert template(change("notes.md")) == "Changed 3 lines in notes.md (+2/−1)."
    assert template(change("x", strategy="none")) == "Changed x through a shell command (no diff available)."
    assert template(change("x", "deleted", 0, 0, strategy="none")) == (
        "Deleted x through a shell command (no content available)."
    )
    assert template(change("n.md", added=0, removed=0, strategy="deferred")) == (
        "Touched n.md; its diff for this session is credited to a later prompt."
    )
    assert template(change("n.md", "reverted", 0, 0, strategy="git")) == (
        "Touched n.md, but its content matches the session start."
    )


def test_null_explainer_covers_every_file():
    out = NullExplainer().explain_prompt("anything", [change("a.py"), change("b.py", "created", 1, 0)])
    assert out == {"a.py": "Changed 3 lines in a.py (+2/−1).", "b.py": "Created b.py with 1 lines."}


class FakeRunner:
    def __init__(self, stdout="", returncode=0, raise_=None):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode
        self.raise_ = raise_

    def __call__(self, argv, input, capture_output, text, timeout, **kwargs):
        self.calls.append((argv, input))
        if self.raise_:
            raise self.raise_
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "stderr text")


def envelope(result):
    return json.dumps({"type": "result", "is_error": False, "result": result})


def test_one_call_per_prompt_and_parsed_reply():
    reply = envelope(
        '```json\n{"a.py": " Adds login. ", "b.py": "unrelated to the request", "zzz": "ignored"}\n```'
    )
    runner = FakeRunner(stdout=reply)
    explainer = ClaudeCodeExplainer(model="haiku", runner=runner)
    files = [change("a.py"), change("b.py"), change("c.py")]
    out = explainer.explain_prompt("add login", files)
    assert out == {"a.py": "Adds login.", "b.py": "unrelated to the request"}
    assert len(runner.calls) == 1
    argv, request = runner.calls[0]
    assert argv[:3] == ["claude", "-p", "--output-format"]
    assert "--no-session-persistence" in argv and "--model" in argv and "haiku" in argv
    assert argv[argv.index("--json-schema") + 1].startswith('{"type":"object"')
    payload = json.loads(request[request.index("{") :])
    assert payload["request"] == "add login"
    assert [f["path"] for f in payload["files"]] == ["a.py", "b.py", "c.py"]
    assert payload["files"][0]["diff"] == "-a\n+b\n+c"


def test_request_caps_diff_size():
    big = change("big.py")
    big.hunks = [Hunk(1, 1, 1, 1, ["+" + "x" * 10_000])]
    request = ClaudeCodeExplainer(runner=FakeRunner()).request("p", [big])
    assert len(request) < 6_000
    assert "(diff truncated)" in request
    many = [change(f"f{i}.py") for i in range(60)]
    for f in many:
        f.hunks = [Hunk(1, 1, 1, 1, ["+" + "y" * 3_000])]
    request = ClaudeCodeExplainer(runner=FakeRunner()).request("p", many)
    assert "(diff omitted for size)" in request
    assert '"added": 2' in request


def test_secrets_never_reach_the_request():
    from graphene_debrief.explain import redact

    env = change(".env", "created", 1, 0)
    env.hunks = [Hunk(1, 0, 1, 1, ["+STRIPE_KEY=sk-live-abcdefghijklmnop"])]
    creds = change("config/credentials.yml")
    creds.hunks = [Hunk(1, 1, 1, 1, ["+password: hunter2"])]
    code = change("app.py")
    code.hunks = [Hunk(1, 1, 1, 2, ['+TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz"', "+x = 1"])]
    request = ClaudeCodeExplainer(runner=FakeRunner()).request("p", [env, creds, code])
    assert "sk-live" not in request and "hunter2" not in request and "ghp_" not in request
    assert request.count("(diff withheld: the file name suggests it holds secrets)") == 2
    assert '[redacted]\\"' in request and "+x = 1" in request
    assert (
        redact("notes/id_rsa.pub", "+ssh-rsa AAAA")
        == "(diff withheld: the file name suggests it holds secrets)"
    )
    assert (
        redact("a.py", "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----") == "[redacted]"
    )


def test_empty_file_list_makes_no_call():
    runner = FakeRunner()
    assert ClaudeCodeExplainer(runner=runner).explain_prompt("p", []) == {}
    assert runner.calls == []


@pytest.mark.parametrize(
    "runner",
    [
        FakeRunner(raise_=subprocess.TimeoutExpired("claude", 1)),
        FakeRunner(raise_=FileNotFoundError("claude")),
        FakeRunner(returncode=1),
        FakeRunner(stdout="not json"),
        FakeRunner(stdout=json.dumps({"is_error": True, "result": "{}"})),
        FakeRunner(stdout=envelope("no json here")),
        FakeRunner(stdout=envelope("{not: valid}")),
        FakeRunner(stdout=envelope("[1, 2]")),
    ],
)
def test_failures_raise_explain_error(runner):
    with pytest.raises(ExplainError):
        ClaudeCodeExplainer(runner=runner).explain_prompt("p", [change("a.py")])


def test_structured_output_is_preferred_over_result_text():
    stdout = json.dumps(
        {"is_error": False, "result": "prose", "structured_output": {"a.py": " Structured. "}}
    )
    assert parse_reply(stdout, ["a.py"]) == {"a.py": "Structured."}


def test_parse_reply_keeps_only_known_paths():
    assert parse_reply(envelope('{"a": "x", "b": "", "c": 3}'), ["a", "b", "c"]) == {"a": "x"}


def test_parse_reply_salvages_pairs_from_slightly_broken_json():
    broken = (
        'Here you go:\n{\n "a.py": "Adds \\"login\\".",\n'
        ' "b.py": "Unquoted trailing text" oops,\n "c.py": "Fine."\n}'
    )
    assert parse_reply(envelope(broken), ["a.py", "b.py", "c.py"]) == {
        "a.py": 'Adds "login".',
        "b.py": "Unquoted trailing text",
        "c.py": "Fine.",
    }
    with pytest.raises(ExplainError):
        parse_reply(envelope("{ nothing usable here }"), ["a.py"])


def test_pick_explainer(monkeypatch):
    assert pick_explainer("none")[0].name == "none"
    assert pick_explainer("claude")[0].name == "claude"
    with pytest.raises(ValueError):
        pick_explainer("gpt")
    monkeypatch.setattr("graphene_debrief.explain.shutil.which", lambda _: None)
    explainer, notice = pick_explainer(None)
    assert (explainer.name, notice) == ("none", None)
    monkeypatch.setattr("graphene_debrief.explain.shutil.which", lambda _: "/usr/bin/claude")
    explainer, notice = pick_explainer(None)
    assert explainer.name == "claude" and "claude" in notice


class CountingExplainer:
    name = "claude"

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def explain_prompt(self, prompt_text, files):
        self.calls += 1
        if self.fail:
            raise ExplainError("boom")
        return {f.path: f"Model says {f.path}." for f in files}


def seed(store):
    store.upsert_session(
        Session(
            id="s",
            repo="/r",
            started_at="2026-01-01T00:00:00.000Z",
            ended_at="2026-01-01T01:00:00.000Z",
            source="backfill",
        )
    )
    store.add_prompt(Prompt("p1", "s", 1, "2026-01-01T00:00:01.000Z", "make a.py"))
    store.add_prompt(Prompt("p2", "s", 2, "2026-01-01T00:30:00.000Z", "make b.py"))
    for i, (pid, path) in enumerate([("p1", "a.py"), ("p2", "b.py")]):
        store.add_event(
            ToolEvent(
                f"e{i}",
                "s",
                pid,
                f"2026-01-01T00:{i * 30 + 2:02d}:00.000Z",
                "Write",
                {"file_path": path, "content": "x\n"},
                {"type": "create", "content": "x\n"},
                True,
                file_path=path,
                old_content=None,
                new_content="x\n",
            )
        )


def test_model_explanations_are_stored_and_reused(tmp_path):
    with Store.open(tmp_path) as store:
        seed(store)
        explainer = CountingExplainer()
        first = build_debrief(store, ["s"], tmp_path, explainer)
        assert [f.explanation for p in first.prompts for f in p.files] == [
            "Model says a.py.",
            "Model says b.py.",
        ]
        assert explainer.calls == 2  # one call per prompt
        assert store.explanation("p1", "a.py") == ("Model says a.py.", "claude")
        second = build_debrief(store, ["s"], tmp_path, CountingExplainer())
        assert [f.explained_by for p in second.prompts for f in p.files] == ["claude", "claude"]
        assert second.notes == []


def test_failure_falls_back_to_templates_with_a_note(tmp_path):
    with Store.open(tmp_path) as store:
        seed(store)
        explainer = CountingExplainer(fail=True)
        debrief = build_debrief(store, ["s"], tmp_path, explainer)
        assert explainer.calls == 1  # after the first failure the run stays on templates
        assert [f.explanation for p in debrief.prompts for f in p.files] == [
            "Created a.py with 1 lines.",
            "Created b.py with 1 lines.",
        ]
        assert debrief.notes == ["explanations by claude failed (boom); showing templates instead"]
        assert store.explanation("p1", "a.py") is None


def test_a_prompt_with_hundreds_of_files_is_explained_in_batches():
    runner = FakeRunner(stdout=envelope("{}"))
    files = [change(f"f{i}.py") for i in range(250)]
    assert ClaudeCodeExplainer(runner=runner).explain_prompt("p", files) == {}
    assert len(runner.calls) == 3
    assert all(len(request) < 200_000 for _, request in runner.calls)
