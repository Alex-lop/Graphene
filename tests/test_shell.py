"""Reading a shell command: which files it writes.

The hook refuses a write with this answer (`gate.py`), so every case here is a command somebody
actually typed, not a grammar exercise.
"""

from pathlib import Path

from graphene_map.shell import bash_written_paths


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
        "echo x > $HOME/y.txt": [],
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
