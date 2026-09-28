"""The key is found in the environment, then the keychain, never in a file; setting it never puts it in
argv. A fake `security` and a fake `secret-tool` stand in for the keychains, on a PATH of their own."""

import sys

import pytest
from fake_tokenfactory import Fake

from graphene_map import keys
from graphene_map import tokenfactory as tf

FAKE = r'''#!{python}
import json, os, pathlib, re, shlex, sys
here = pathlib.Path(__file__).parent
store, log = here / "store.json", here / "argv.log"
with open(log, "a") as f:
    f.write(json.dumps(sys.argv) + "\n")
kept = json.loads(store.read_text()) if store.exists() else {{}}
argv = sys.argv[1:]
if "{tool}" == "security":
    if argv == ["-i"]:
        argv = shlex.split(sys.stdin.read())
    if argv[0] == "find-generic-password":
        if "key" not in kept:
            sys.exit(44)
        print(kept["key"])
    elif argv[0] == "add-generic-password":
        kept["key"] = argv[argv.index("-w") + 1]
    elif argv[0] == "delete-generic-password":
        if kept.pop("key", None) is None:
            sys.exit(44)
else:
    if argv[0] == "lookup":
        if "key" not in kept:
            sys.exit(1)
        sys.stdout.write(kept["key"])
    elif argv[0] == "store":
        kept["key"] = sys.stdin.read()
    elif argv[0] == "clear":
        kept.pop("key", None)
store.write_text(json.dumps(kept))
'''


@pytest.fixture(params=["darwin", "linux"])
def keychain(request, tmp_path, monkeypatch):
    """A fake keychain for this platform: its store and the argv of every call, as files."""
    tool = "security" if request.param == "darwin" else "secret-tool"
    fake = tmp_path / "bin" / tool
    fake.parent.mkdir()
    fake.write_text(FAKE.format(python=sys.executable, tool=tool))
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent))
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "on")
    monkeypatch.setattr(keys, "PLATFORM", request.param)
    keys._from_keychain.cache_clear()
    yield fake.parent
    keys._from_keychain.cache_clear()


def test_the_suite_never_reaches_the_real_keychain(monkeypatch):
    monkeypatch.setattr(keys.subprocess, "run", lambda *a, **k: pytest.fail("the keychain was asked"))
    assert keys.find() is None


def test_nothing_set_is_none(keychain):
    assert keys.find() is None


def test_a_key_set_is_found_and_never_in_argv(keychain):
    keys.set("v1.the-secret")
    assert keys.find() == "v1.the-secret"
    assert "the-secret" not in (keychain / "argv.log").read_text()


def test_the_environment_comes_first(keychain, monkeypatch):
    keys.set("from-keychain")
    monkeypatch.setenv("NEBIUS_API_KEY", "from-env")
    assert keys.find() == "from-env"


def test_remove_takes_it_out(keychain):
    keys.set("gone-soon")
    keys.remove()
    assert keys.find() is None


def test_no_file_is_read(keychain, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("NEBIUS_API_KEY=from-a-file\n")
    assert keys.find() is None


def test_a_key_with_a_quote_is_refused_before_anything_runs(keychain):
    with pytest.raises(RuntimeError, match="one word"):
        keys.set('a"b')
    assert not (keychain / "argv.log").exists()


def test_with_the_keychain_off_nothing_is_set(monkeypatch):
    monkeypatch.setattr(keys, "PLATFORM", "darwin")
    with pytest.raises(RuntimeError, match="keychain is off"):
        keys.set("k")


def test_a_failed_remove_says_so(keychain):
    if keys.PLATFORM != "darwin":
        pytest.skip("secret-tool clear with nothing to clear is not a failure")
    with pytest.raises(RuntimeError, match="could not be removed: .* said exit"):
        keys.remove()


def test_the_keychain_key_reaches_token_factory(keychain, monkeypatch):
    with Fake() as f:
        env = f.env()
        monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", env["GRAPHENE_TOKENFACTORY_URL"])
        keys.set(env["NEBIUS_API_KEY"])
        tf._listed.cache_clear()
        line = keys.reached()
    tf._listed.cache_clear()
    assert line.startswith("Token Factory: reached, ") and line.endswith(" NVIDIA models")
    assert env["NEBIUS_API_KEY"] not in line


def test_reached_says_what_stood_in_the_way_without_the_key(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "not-shown")
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", "http://127.0.0.1:9/")
    monkeypatch.setattr(tf.time, "sleep", lambda s: None)
    tf._listed.cache_clear()
    line = keys.reached()
    tf._listed.cache_clear()
    assert line.startswith("Token Factory: not reached") and "not-shown" not in line and "\n" not in line


def test_a_keychain_tool_that_cannot_run_is_not_passed_over_for_the_next_on_the_path(keychain, tmp_path, monkeypatch):
    tool = "security" if keys.PLATFORM == "darwin" else "secret-tool"
    broken = tmp_path / "broken" / tool
    broken.parent.mkdir()
    broken.write_text("#!/nonexistent/interpreter\n")
    broken.chmod(0o755)
    monkeypatch.setenv("PATH", f"{broken.parent}:{keychain}")
    assert keys.find() is None
    assert not (keychain / "argv.log").exists()  # the next one on the PATH was never started


def test_model_written_code_and_a_check_never_find_the_keychain_key(tmp_path, monkeypatch):
    import json
    import subprocess

    from graphene_map import executor
    from graphene_map import plan as P

    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for tool in ("security", "secret-tool"):  # the child asks the machine's own, whatever PLATFORM says here
        (bin_ / tool).write_text(FAKE.format(python=sys.executable, tool=tool))
        (bin_ / tool).chmod(0o755)
    (bin_ / "store.json").write_text(json.dumps({"key": "sk-FAKEKEY-abc123xyz"}))
    monkeypatch.setenv("PATH", f"{bin_}:/usr/bin:/bin")
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "on")
    keys._from_keychain.cache_clear()
    assert keys.find() == "sk-FAKEKEY-abc123xyz"  # this process, Graphene's own, finds it
    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "a"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv], cwd=repo, check=True)
    peek = f"{sys.executable} -c 'from graphene_map import keys; print(keys.find())'"
    code, out = executor.Local(repo).run(peek)
    assert (code, out.strip()) == (0, "None")
    passed, said, _ = P.run_check(peek, repo)
    assert passed and "sk-FAKEKEY" not in said and "None" in said
    keys._from_keychain.cache_clear()


def test_a_keychain_that_hangs_is_given_up_on_and_asked_once_per_process(keychain, monkeypatch):
    tool = "security" if keys.PLATFORM == "darwin" else "secret-tool"
    (keychain / tool).write_text(f"#!/bin/sh\necho x >> {keychain}/spawns\nsleep 3\n")
    monkeypatch.setattr(keys, "TIMEOUT", 0.3)
    assert [keys.find() for _ in range(3)] == [None] * 3  # no TimeoutExpired, and no wait each time
    assert (keychain / "spawns").read_text() == "x\n"
