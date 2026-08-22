from __future__ import annotations

import pytest

from graphene.shadow.classify import (
    CLASSIFY_VERSION,
    CommandClassification,
    FileOp,
    classify_command,
)

CHECK_FAMILIES = [
    ("pytest -q", "pytest"),
    ("py.test tests/", "pytest"),
    (".venv/bin/pytest -x", "pytest"),
    ("python -m pytest tests/unit", "pytest"),
    ("python3 -m pytest", "pytest"),
    ("python3.13 -m pytest -q", "pytest"),
    ("/usr/bin/python3 -X dev -m pytest", "pytest"),
    ("uv run pytest -q", "pytest"),
    ("uv run --frozen pytest -q tests/unit/shadow", "pytest"),
    ("uv run --python 3.13 pytest", "pytest"),
    ("uv run --frozen python -m pytest", "pytest"),
    ("poetry run pytest", "pytest"),
    ("python -m unittest discover -s tests", "python-unittest"),
    ("npm test", "npm-test"),
    ("npm run test", "npm-test"),
    ("npm run test:unit", "npm-test"),
    ("npm t", "npm-test"),
    ("npm test -- --coverage", "npm-test"),
    ("yarn test", "yarn-test"),
    ("yarn run test", "yarn-test"),
    ("pnpm test", "pnpm-test"),
    ("npx jest --ci", "jest"),
    ("jest src/", "jest"),
    ("./node_modules/.bin/jest", "jest"),
    ("npx vitest run", "vitest"),
    ("vitest", "vitest"),
    ("node --test tests/", "node-test"),
    ("go test ./...", "go-test"),
    ("cargo test --workspace", "cargo-test"),
    ("make test", "make-test"),
    ("make check", "make-test"),
    ("make -C backend test", "make-test"),
    ("ruff check .", "ruff"),
    ("ruff format --check backend", "ruff"),
    ("uv run --frozen ruff check backend tests", "ruff"),
    ("mypy backend", "mypy"),
    ("python -m mypy backend", "mypy"),
    ("pyright", "pyright"),
    ("eslint src --max-warnings 0", "eslint"),
    ("npx eslint .", "eslint"),
    ("tsc --noEmit", "tsc"),
    ("tsc", "tsc"),
    ("flake8 backend", "flake8"),
    ("python -m flake8", "flake8"),
    ("black --check .", "black"),
    ("python -m compileall backend", "compileall"),
]

NOT_CHECKS = [
    "ruff format .",
    "black .",
    "npm run build",
    "npm run lint",
    "node app.js",
    "go build ./...",
    "cargo build",
    "make",
    "make build",
    'echo "pytest passed"',
    "echo 'all tests pass && pytest'",
    "git status",
    "uv run python app.py",
    "python -m http.server",
    "python pytest_helper.py",
    "",
    "   ",
]

VCS_OPS = [
    "git commit -m 'wip'",
    "git push origin main",
    "git checkout -b feature",
    "git switch main",
    "git reset --hard HEAD~1",
    "git rebase -i main",
    "git stash",
    "git merge feature",
    "git cherry-pick abc123",
    "git tag v1.0.0",
    "git am patch.mbox",
    "git restore backend/app.py",
    "git clean -fd",
    "git rm old.py",
    "git mv a.py b.py",
    "git add .",
    "git branch -D stale",
    "git branch -d stale",
    "git branch --delete stale",
    "git -C /tmp/repo commit -m msg",
    "git --no-pager commit -m msg",
    "git -c user.name=x commit -m msg",
]

GIT_READ_ONLY = [
    "git status",
    "git log --oneline -5",
    "git diff --stat",
    "git show HEAD",
    "git rev-parse HEAD",
    "git for-each-ref",
    "git branch",
    "git branch --list",
    "git -C /tmp/repo status",
]

NETWORK_OPS = [
    "curl -sSf https://example.test/health",
    "wget https://example.test/file.tgz",
    "http GET example.test",
    "https example.test",
    "httpie example.test",
    "ssh host uptime",
    "scp file host:/tmp",
    "sftp host",
    "rsync -av src/ host:dst/",
    "nc -z host 22",
    "ncat host 22",
    "telnet host 23",
    "ping -c 1 host",
    "dig example.test",
    "nslookup example.test",
    "gh pr view 12",
    "git clone https://example.test/repo.git",
    "git fetch origin",
    "git pull --rebase",
]

INSTALL_OPS = [
    "pip install requests",
    "pip3 install -r requirements.txt",
    "python -m pip install -e .",
    "uv add httpx",
    "uv sync --frozen",
    "uv pip install ruff",
    "uv tool install ruff",
    "pipx install black",
    "poetry add httpx",
    "poetry install",
    "npm install",
    "npm i lodash",
    "npm ci",
    "npm add lodash",
    "yarn add lodash",
    "yarn install",
    "pnpm add lodash",
    "pnpm install",
    "pnpm i",
    "brew install jq",
    "apt install jq",
    "apt-get install -y jq",
    "sudo apt-get install -y jq",
    "cargo add serde",
    "cargo install ripgrep",
    "go get example.test/pkg",
    "go install example.test/cmd@latest",
    "gem install rails",
    "conda install numpy",
]

PLAIN_EXEC = [
    "ls -la",
    "cat README.md",
    "pip download requests",
    "pip uninstall requests",
    "uv lock",
    "uv run python app.py",
    "npm run start",
    "go version",
    "cargo build --release",
    "gem list",
    "echo hello",
    "grep -r TODO backend",
]


@pytest.mark.parametrize(("command", "family"), CHECK_FAMILIES)
def test_check_families(command: str, family: str) -> None:
    result = classify_command(command)
    assert result.kind == "check_run"
    assert result.check_family == family


@pytest.mark.parametrize("command", NOT_CHECKS)
def test_not_checks(command: str) -> None:
    result = classify_command(command)
    assert result.kind == "command_exec"
    assert result.check_family is None


@pytest.mark.parametrize("command", VCS_OPS)
def test_vcs_ops(command: str) -> None:
    assert classify_command(command) == CommandClassification("vcs_op", None, ())


@pytest.mark.parametrize("command", GIT_READ_ONLY)
def test_read_only_git_is_command_exec(command: str) -> None:
    assert classify_command(command) == CommandClassification("command_exec", None, ())


@pytest.mark.parametrize("command", NETWORK_OPS)
def test_network_ops(command: str) -> None:
    assert classify_command(command) == CommandClassification("network_op", None, ())


@pytest.mark.parametrize("command", INSTALL_OPS)
def test_install_ops(command: str) -> None:
    assert classify_command(command) == CommandClassification("install_op", None, ())


@pytest.mark.parametrize("command", PLAIN_EXEC)
def test_plain_exec(command: str) -> None:
    assert classify_command(command) == CommandClassification("command_exec", None, ())


@pytest.mark.parametrize(
    ("command", "kind", "family"),
    [
        ("git push && curl x && pip install y && pytest -q", "check_run", "pytest"),
        ("pytest -q || npm test", "check_run", "pytest"),
        ("npm test; pytest -q", "check_run", "npm-test"),
        ("git push origin main && curl https://example.test", "network_op", None),
        ("pip install x && curl https://example.test", "install_op", None),
        ("git commit -m x; git status", "vcs_op", None),
        ("ls | grep foo", "command_exec", None),
        ("cd backend && pytest -q", "check_run", "pytest"),
        ("cd backend; pytest -q", "check_run", "pytest"),
        ("cd backend\npytest -q", "check_run", "pytest"),
        ("echo done\npytest -q", "check_run", "pytest"),
        ("(cd backend && pytest -q)", "check_run", "pytest"),
        ("pytest -q | tee out.log", "check_run", "pytest"),
        ("echo $(git status)", "command_exec", None),
    ],
)
def test_compound_priority_and_first_family(
    command: str, kind: str, family: str | None
) -> None:
    result = classify_command(command)
    assert result.kind == kind
    assert result.check_family == family


@pytest.mark.parametrize(
    "command",
    [
        "FOO=1 pytest -q",
        "FOO=1 BAR=two pytest -q",
        "env FOO=1 pytest -q",
        "env -i PATH=/usr/bin pytest -q",
        "time pytest -q",
        "sudo pytest -q",
        "sudo -E pytest -q",
        "sudo -u runner pytest -q",
        "FOO=1 env BAR=2 sudo time pytest -q",
        "cd backend pytest -q",
    ],
)
def test_prefixes_are_stripped(command: str) -> None:
    result = classify_command(command)
    assert result.kind == "check_run"
    assert result.check_family == "pytest"


def test_shlex_fallback_on_unbalanced_quotes() -> None:
    result = classify_command('echo "oops && pytest -q')
    assert result.kind == "check_run"
    assert result.check_family == "pytest"

    fallback = classify_command("echo it's done && rm -f stale.txt")
    assert fallback.kind == "command_exec"
    assert fallback.file_ops == (FileOp("file_delete", "stale.txt"),)


@pytest.mark.parametrize(
    ("command", "file_ops"),
    [
        ("rm stale.txt", (FileOp("file_delete", "stale.txt"),)),
        (
            "rm -rf build/ dist/",
            (FileOp("file_delete", "build/"), FileOp("file_delete", "dist/")),
        ),
        ("rm -rf /dev/null", ()),
        ("rm -rf *.pyc", ()),
        ("rm -f a?.txt", ()),
        ("rm -f [ab].txt", ()),
        ("rm -f $TMPFILE", ()),
        ("rm -f `mktemp`", ()),
        ("rm -f -- -weird", ()),
        ("rm -f stale.txt 2>/dev/null", (FileOp("file_delete", "stale.txt"),)),
        (
            "mv a.py b.py",
            (FileOp("file_delete", "a.py"), FileOp("file_create", "b.py")),
        ),
        (
            "mv -f a.py b.py dir/",
            (FileOp("file_delete", "a.py"), FileOp("file_delete", "b.py")),
        ),
        ("mv -t dir/ a.py", (FileOp("file_delete", "a.py"),)),
        ("cp a.py b.py", (FileOp("file_create", "b.py"),)),
        ("cp -r src dest/", ()),
        ("cp a.py", ()),
        (
            "touch new.py other.py",
            (FileOp("file_create", "new.py"), FileOp("file_create", "other.py")),
        ),
        ("tee out.log", (FileOp("file_edit", "out.log"),)),
        ("tee -a out.log", (FileOp("file_edit", "out.log"),)),
        ("sed -i 's/a/b/' app.py", (FileOp("file_edit", "app.py"),)),
        ("sed -i.bak 's/a/b/' app.py", (FileOp("file_edit", "app.py"),)),
        ("sed -i '' 's/a/b/' app.py", (FileOp("file_edit", "app.py"),)),
        (
            "sed -i -e 's/a/b/' app.py lib.py",
            (FileOp("file_edit", "app.py"), FileOp("file_edit", "lib.py")),
        ),
        ("sed -ri 's/a/b/' app.py", (FileOp("file_edit", "app.py"),)),
        ("sed --in-place=.bak 's/a/b/' app.py", (FileOp("file_edit", "app.py"),)),
        ("sed -n 's/a/b/p' app.py", ()),
        ("sed 's/a/b/' app.py > out.py", (FileOp("file_create", "out.py"),)),
        ("echo hi > out.txt", (FileOp("file_create", "out.txt"),)),
        ("echo hi >out.txt", (FileOp("file_create", "out.txt"),)),
        ("echo hi >> out.txt", (FileOp("file_edit", "out.txt"),)),
        ("echo hi 1> out.txt", (FileOp("file_create", "out.txt"),)),
        ("echo hi 2> err.txt", (FileOp("file_create", "err.txt"),)),
        ("echo hi 2>> err.txt", (FileOp("file_edit", "err.txt"),)),
        ("echo hi &> all.txt", (FileOp("file_create", "all.txt"),)),
        ("echo hi > /dev/null", ()),
        ("echo hi > /dev/null 2>&1", ()),
        ("echo hi 2>&1", ()),
        ("echo hi >&2", ()),
        ("echo hi > out.txt 2>&1", (FileOp("file_create", "out.txt"),)),
        ('echo hi > "my file.txt"', (FileOp("file_create", "my file.txt"),)),
        ("echo hi > *.txt", ()),
        ('grep ">" app.py', ()),
        ("echo '>' app.py", ()),
        ("cat < input.txt", ()),
        (
            "cat <<EOF > out.txt\nrm -rf everything\nEOF\n",
            (FileOp("file_create", "out.txt"),),
        ),
        (
            "cat > out.txt <<'EOF'\nrm -rf everything && pytest\nEOF",
            (FileOp("file_create", "out.txt"),),
        ),
        (
            "echo x > a.txt && rm b.txt",
            (FileOp("file_create", "a.txt"), FileOp("file_delete", "b.txt")),
        ),
        ("sudo rm -rf build/", (FileOp("file_delete", "build/"),)),
        ("pytest -q > out.log 2>&1", (FileOp("file_create", "out.log"),)),
        ("ls -la", ()),
        ("echo 'rm -rf x'", ()),
    ],
)
def test_file_ops(command: str, file_ops: tuple[FileOp, ...]) -> None:
    assert classify_command(command).file_ops == file_ops


def test_heredoc_body_is_not_classified() -> None:
    result = classify_command("cat > notes.txt <<'EOF'\npytest -q\ncurl x\nEOF\n")
    assert result.kind == "command_exec"
    assert result.check_family is None
    assert result.file_ops == (FileOp("file_create", "notes.txt"),)


def test_line_continuation_is_joined() -> None:
    result = classify_command("uv run --frozen \\\n  pytest -q")
    assert result == CommandClassification("check_run", "pytest", ())


def test_result_is_a_named_tuple_and_version_is_pinned() -> None:
    assert CLASSIFY_VERSION == "classify.v1"
    result = classify_command("pytest -q")
    assert isinstance(result, CommandClassification)
    assert isinstance(result.file_ops, tuple)
    assert result == ("check_run", "pytest", ())
