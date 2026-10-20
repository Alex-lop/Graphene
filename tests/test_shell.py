"""Reading a shell command: which files it writes.

The hook refuses a write with this answer (`gate.py`), so every case here is a command somebody
actually typed, not a grammar exercise.
"""

from pathlib import Path

import pytest

from graphene_map.shell import bash_written_paths, shell_segments


def test_bash_written_paths(tmp_path):
    root = tmp_path
    cases = {
        "echo hi > notes.txt": [("notes.txt", "write")],
        "cat <<'EOF' >> log/out.txt\nx\nEOF": [("log/out.txt", "write")],
        "sed -i '' 's/a/b/' src/x.py": [("src/x.py", "write")],
        "sed -i -e 's/a/b/' one.py two.py": [("one.py", "write"), ("two.py", "write")],
        "mv old.py new.py": [("new.py", "write"), ("old.py", "delete")],
        "rm -rf build dist/": [("build", "delete"), ("dist", "delete")],
        "tee -a a.log": [("a.log", "write")],
        "cp a.txt b.txt && touch c.txt": [("b.txt", "write"), ("c.txt", "write")],
        "ls 2>/dev/null > /dev/null": [],
        "git status": [],
        f"echo x > {root}/abs.txt": [("abs.txt", "write")],
        "echo x > /elsewhere/abs.txt": [("/elsewhere/abs.txt", "write")],
        "echo x > $HOME/y.txt": [(str(Path.home() / "y.txt"), "write")],  # $HOME resolves, like ~
    }
    for command, expected in cases.items():
        assert bash_written_paths(command, root) == expected, command


def test_heredoc_bodies_are_not_shell_syntax(tmp_path):
    command = "cat > out.py <<'EOF'\nif len(v) > 4096:\n    x = a > CONTENT_CAP\nEOF\necho done"
    assert bash_written_paths(command, tmp_path) == [("out.py", "write")]
    assert bash_written_paths("python - <<EOF\nprint(1 > 0)\nEOF", tmp_path) == []


def test_relative_paths_follow_cd(tmp_path):
    assert bash_written_paths("cd sub && echo hi > a.txt", tmp_path) == [("sub/a.txt", "write")]
    assert bash_written_paths("cd /elsewhere && echo x > a.txt", tmp_path) == [("/elsewhere/a.txt", "write")]
    assert bash_written_paths("cd sub && cd .. && echo x > b.txt", tmp_path) == [("b.txt", "write")]
    assert bash_written_paths("cd ~ && echo x > c.txt", tmp_path) == [(str(Path.home() / "c.txt"), "write")]


def test_quotes_variables_and_newlines_in_shell_commands(tmp_path):
    cases = {
        'grep -n "directory\\|rm -rf" docs/x.md | head -40': [],
        "echo 'a; rm -rf b' > note.txt": [("note.txt", "write")],
        'cd "$T" && echo x > f.txt && rm g.txt': [],
        'cd "$T" && echo x > /abs/f.txt': [("/abs/f.txt", "write")],
        "echo hi >notes.txt 2>/dev/null": [("notes.txt", "write")],
        "echo hi > a.txt\necho yo > b.txt": [("a.txt", "write"), ("b.txt", "write")],
        "printf 'x\\ny' > c.txt": [("c.txt", "write")],
        "cd sub; cd ..; echo > d.txt": [("d.txt", "write")],
        "(cd sub && echo > e.txt)": [("sub/e.txt", "write")],
        "rm -f x.txt 2>/dev/null": [("x.txt", "delete")],
        "rm -f y.txt 2>&1": [("y.txt", "delete")],
        "mv a.txt b.txt 1>log.txt": [("log.txt", "write"), ("b.txt", "write"), ("a.txt", "delete")],
    }
    for command, expected in cases.items():
        assert bash_written_paths(command, tmp_path) == expected, command


def test_files_inside_a_nested_checkout_are_outside_the_repo(tmp_path):
    """A worktree under .claude/worktrees/ (Claude Code puts them there) is another checkout, so a
    path inside it is named absolutely: it is not this repo's file."""
    from graphene_map.hooks import relative_path

    worktree = tmp_path / ".claude" / "worktrees" / "agent-1"
    (worktree / "src").mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: elsewhere\n")
    inside = str(worktree / "src" / "app.py")
    assert relative_path(inside, tmp_path) == inside
    assert relative_path(str(tmp_path / "src" / "app.py"), tmp_path) == "src/app.py"
    assert bash_written_paths(f"echo x > {inside}", tmp_path) == [(inside, "write")]


@pytest.mark.parametrize(
    "command, written",
    [
        ("# update the schema\necho x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("ls # list first\necho x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("# write it\ncat > src/db/schema.py <<'EOF'\nTABLES = ['x']\nEOF", [("src/db/schema.py", "write")]),
        ("echo https://example.com/#top\necho x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("x=abc; echo ${#x} > src/db/schema.py", [("src/db/schema.py", "write")]),
        ('echo "a # b" > out.txt', [("out.txt", "write")]),
        ("grep -n '>' src/db/schema.py", []),
        ("rg -n '>>' src", []),
        ("echo x \\> not-a-write.txt", []),
        ("echo '>' > src/api/users.py", [("src/api/users.py", "write")]),
        ("cat > a.txt <<'EOF'\ndon't\nEOF\necho x > outside.txt",
         [("a.txt", "write"), ("outside.txt", "write")]),
    ],
)
def test_a_comment_hides_no_write_after_it_and_a_quoted_redirect_writes_nothing(command, written, tmp_path):
    """An adversarial pass at the gate (19 October): a `#` comment line above a write hid it (shlex read the
    comment to the end of the command once its newlines were `;`), and a quoted `>` in a grep pattern was read
    as a redirect, refusing a read. A comment ends with its line; a `>` inside quotes, or escaped, is text; an
    apostrophe in a heredoc body opens no quote."""
    assert bash_written_paths(command, tmp_path) == [(p, k) for p, k in written]


def test_a_commit_message_keeps_its_quoted_redirects_and_hashes():
    assert shell_segments("git commit -m 'a > b # c'") == [["git", "commit", "-m", "a > b # c"]]


@pytest.mark.parametrize(
    "command, written",
    [
        # finding 4: redirect forms and targets the parser did not read. Each wrote src/db/schema.py.
        ("echo x >& src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo x 1<> src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo x &>> src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo x | command tee src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo x |& tee src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo x | command tee -a src/db/schema.py", [("src/db/schema.py", "write")]),
        ("dd if=/dev/zero of=src/db/schema.py", [("src/db/schema.py", "write")]),
        ("install -m 644 a src/db/schema.py", [("src/db/schema.py", "write")]),
        # a variable set to a literal in the same command, and $PWD / $(pwd), resolve
        ("F=src/db/schema.py; echo x > $F", [("src/db/schema.py", "write")]),
        ("d=src/db; echo x > $d/schema.py", [("src/db/schema.py", "write")]),
        ("echo x > $PWD/src/db/schema.py", [("src/db/schema.py", "write")]),
        # a target the hook cannot know before bash runs: a glob, a variable it was not given, a
        # command substitution (a backtick stays one token; `$(…)` shlex splits on its parens)
        ("echo x > src/db/schema.p?", [("src/db/schema.p?", "unknown")]),
        ("echo x > $OUT", [("$OUT", "unknown")]),
        ("echo x > `mktemp`", [("`mktemp`", "unknown")]),
        # not a write: a fd duplication, a glob that only deletes, /dev/null
        ("echo x >&2", []),
        ("rm -rf build/*", []),
        ("cat a > /dev/null", []),
    ],
)
def test_redirect_forms_and_targets_the_parser_now_reads(command, written, tmp_path):
    """Finding 4 of the adversarial pass: `>&`, `1<>`, `&>>`, `|&`, `command`/`dd`/`install`, and a
    redirect after a variable the command set, a glob or `$PWD`, were not read and let a write by. A
    target that stays a variable, a glob or a substitution is "unknown": the gate refuses it while a
    leaf is held (it cannot be checked), but `$PWD`, `$HOME` and an in-command literal resolve."""
    assert bash_written_paths(command, tmp_path) == [(p, k) for p, k in written]


@pytest.mark.parametrize(
    "command, written",
    [
        # finding 5: cd followed wrongly. Each of these wrote src/db/schema.py and was missed.
        ("cd -P src/db && echo x > schema.py", [("src/db/schema.py", "write")]),
        ("cd -- src/db && echo x > schema.py", [("src/db/schema.py", "write")]),
        ("cd src/api && cd - >/dev/null && echo x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("cd $PWD/src/db && echo x > schema.py", [("src/db/schema.py", "write")]),
        ("(cd src/api); echo x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("(cd src/api && pwd >/dev/null) && echo x > src/db/schema.py", [("src/db/schema.py", "write")]),
        # a subshell's cd ends at its `)`, so the write after it lands where the outer shell is, not
        # inside the subshell's directory (these were read as src/src/… and wrongly refused)
        ("(cd src && ls >/dev/null) && echo x > src/api/users.py", [("src/api/users.py", "write")]),
        ("pushd src/api >/dev/null && echo x > users.py", [("src/api/users.py", "write")]),
        # and the honest cases the parser already read stay the same
        ("cd sub && echo hi > a.txt", [("sub/a.txt", "write")]),
        ("(cd sub && echo > e.txt)", [("sub/e.txt", "write")]),
    ],
)
def test_cd_flags_dash_pwd_and_subshells_are_followed_as_bash_does(command, written, tmp_path):
    """Finding 5: `cd -P`/`cd --` were read as `cd ~`, `cd -` and `cd $PWD/…` lost the directory, and a
    subshell's `cd` leaked past its `)` (so a write after it was read in the wrong place, bypassing the
    scope one way and falsely refused the other). The cwd now follows bash: flags skipped, `cd -` to the
    previous directory, `$PWD` resolved, a subshell's cd undone at its `)`."""
    assert bash_written_paths(command, tmp_path) == [(p, k) for p, k in written]
