"""`.git/` is git's own: a hook planted in `.git/hooks/` runs on the person's next commit, and `git status`
never shows it, so `done` could not see it either. The night of 26 October found a leaf whose scope was
`.git/hooks/pre-commit` proposed, accepted (by the envelope at once, with auto on) and free to write there.
No scope reaches it now, and no write into it is let through, whatever the scope says."""

import subprocess

import pytest

from graphene_map import gate as G
from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map.store import Store

ALEX = P.Caller("alex", True)
BOT = P.Caller("claude:b0t", False, "b0t-session")


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    who = ["-c", "user.email=t@e", "-c", "user.name=T"]
    subprocess.run(["git", "-C", str(tmp_path), *who, "commit", "-qm", "a"], check=True)
    return tmp_path


@pytest.mark.parametrize("scope", [".git/hooks/pre-commit", ".git/**", ".git", "./.git/config"])
def test_no_scope_reaches_git_dir(repo, scope):
    with Store.open(repo) as store:
        for who in (BOT, ALEX):
            with pytest.raises(P.Refused, match=r"\.git/ is git's own"):
                text = f"? reach in  [reach-{who.name[:3]}]\n    scope: {scope}\n    check: true\n"
                T.apply(store, text, who, None, files=P.tracked(repo))


@pytest.mark.parametrize("path", [".git/hooks/pre-commit", ".git/config", ".git"])
def test_a_write_into_git_dir_is_refused_whatever_the_scope(repo, path):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "all", "title": "everything", "scope": ["**"], "check": "true"}], ALEX)
        held = [P.get(store, "all")]
        assert not P.binds(path, held[0], [])
        said = G.scope_refused(store, held, path, "s1", "Write")
        assert said and ".git/ is git's own" in said
        assert P.binds("a.py", held[0], [])  # the rest of the scope holds as it did
