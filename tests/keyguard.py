"""No test reaches the real keychain, whatever it does to GRAPHENE_KEYCHAIN, PATH or a child's environment
(decision 96). A pytest plugin, installed by tests/conftest.py and docs/test/conftest.py:

- Stand-ins for `security` and `secret-tool` go first on the session's PATH, so every process a test
  starts finds them before the real ones. They write down the call and exit 1; they never read stdin.
- An audit hook in the test process refuses to start a `security` or `secret-tool` that is not a
  test's fake, by name or by absolute path, and refuses `import keyring`: the test fails at once. A child
  whose PATH would find a real keychain tool (a test replaced the PATH, or gave it none) gets the
  stand-ins put on it just ahead of that tool.
- A stand-in's call fails the test it was made in; one left at the end of the session fails the run.

A test that needs a keychain fakes it: a `security` or `secret-tool` it writes under its tmp_path and
puts first on the PATH (tests/test_keys.py's `keychain`). A tool in the temp directory is the only kind
that runs. Beyond reach: a child process that runs the real tool by its absolute path, or makes a PATH
of its own; Graphene's own code does neither (keys.py asks `which()` on the PATH it was given).
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

TOOLS = ("security", "secret-tool")
SHIM = """#!/bin/sh
echo "$(basename "$0") $1${{PYTEST_CURRENT_TEST:+, during $PYTEST_CURRENT_TEST}}" >> '{log}'
echo "keyguard: a test asked the keychain; it was a stand-in, and nothing was read or kept" >&2
exit 1
"""
HOW = "a test that needs a keychain fakes one under its tmp_path (tests/test_keys.py's `keychain`)"
SHIMS: Path | None = None  # the stand-ins' directory, made once a session
TEMP = Path(tempfile.gettempdir()).resolve()  # where every test's fakes live
refused: list[str] = []
seen = 0  # lines of the stand-ins' log already said
STALE = 3600  # ponytail: an hour; a child outliving its session by more finds the real tool next on its PATH


def install(config: pytest.Config) -> None:
    """Put the stand-ins first on the PATH, hook the test process, and watch every test; once a session."""
    global SHIMS
    if SHIMS:
        return
    _sweep()
    shims = Path(tempfile.mkdtemp(prefix=f"keyguard-{os.getpid()}-")).resolve()  # left: see _sweep
    for tool in TOOLS:
        (shims / tool).write_text(SHIM.format(log=shims / "calls.log"))
        (shims / tool).chmod(0o755)
    SHIMS = shims
    os.environ["PATH"] = f"{shims}{os.pathsep}{os.environ.get('PATH', os.defpath)}"
    sys.addaudithook(_audit)
    config.pluginmanager.register(sys.modules[__name__], "keyguard")


def _sweep() -> None:
    """Earlier sessions' stand-ins go once their pytest has ended and an hour has passed since they were
    last used, so they do not pile up in the temp directory, and a child that outlived its session still
    meets them meanwhile. A name without a pid is from before the pid was put in it."""
    for old in TEMP.glob("keyguard-*"):
        pid = old.name.split("-")[1]
        try:
            if time.time() - old.stat().st_mtime < STALE:
                continue
            if pid.isdigit():
                os.kill(int(pid), 0)  # raises once its pytest has ended
                continue
        except ProcessLookupError:
            pass
        except OSError:
            continue  # another session swept it first, or another user's session is still running
        shutil.rmtree(old, ignore_errors=True)


def _refuse_real(program, env) -> None:
    """A keychain tool anywhere but under the temp directory is the real one; a stand-in is not a fake."""
    program = os.fsdecode(program)
    if os.sep not in program:  # found on the PATH the child is given, as exec finds it
        if program not in TOOLS:
            return
        program = shutil.which(program, path=os.pathsep.join(os.get_exec_path(env))) or ""
    found = Path(program).resolve()
    if program and found.name in TOOLS and (not found.is_relative_to(TEMP) or found.parent == SHIMS):
        _refuse(f"{found} was about to run")


def _shims_first(env) -> None:
    """The stand-ins go on a child's PATH just ahead of the first real keychain tool it would find there,
    behind any fake the test put first."""
    dirs, covered = os.get_exec_path(env), set()
    for i, where in enumerate(dirs):
        if len(covered) == len(TOOLS):
            return
        for tool in set(TOOLS) - covered:
            found = Path(where, tool)
            if found.is_file() and os.access(found, os.X_OK):
                if not found.resolve().is_relative_to(TEMP):
                    ahead = os.pathsep.join([*dirs[:i], str(SHIMS), *dirs[i:]])
                    (os.environ if env is None else env)["PATH"] = ahead
                    return
                covered.add(tool)


def _refuse(what: str) -> None:
    refused.append(f"keyguard: {what}: the real keychain is not for tests; {HOW}")
    pytest.fail(refused[-1], pytrace=False)


def _audit(event: str, args: tuple) -> None:
    if event == "subprocess.Popen":  # (executable, args, cwd, env)
        _refuse_real(args[0], args[3])
        _shims_first(args[3])
    elif event in ("os.exec", "os.posix_spawn"):  # (path, argv, env)
        _refuse_real(args[0], args[2])
    elif event == "os.spawn":  # (mode, path, args, env)
        _refuse_real(args[1], args[3])
    elif event == "os.system":
        _shims_first(None)
    elif event == "import" and args[0].partition(".")[0] == "keyring":
        _refuse("keyring was imported")


def _said() -> list[str]:
    """What was refused, and the stand-ins' calls, since the last time asked."""
    global seen
    log = SHIMS / "calls.log"
    calls = log.read_text().splitlines() if log.exists() else []
    said = refused[:] + [f"keyguard: a process asked the keychain: {c}; {HOW}" for c in calls[seen:]]
    refused.clear()
    seen = len(calls)
    return said


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    said = [line for line in _said() if line not in str(report.longrepr)]
    if said and report.failed:
        report.sections.append(("keyguard", "\n".join(said)))
    elif said:
        report.outcome, report.longrepr = "failed", "\n".join(said)
    return report


def pytest_sessionfinish(session: pytest.Session) -> None:
    said = _said()  # a call from a child that outlived its test, or made outside any test
    if said:
        print("\n" + "\n".join(said), file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


# where git finds the repository, as `git bisect run`, a hook or `rebase --exec` export it: a test's git
# would act on the repository running the suite (a task repo's commit landed there), so no test gets them;
# nor the settings given as `git -c`, which reach a hook and `rebase --exec` too (commit.gpgsign=true
# failed every test repo's commit)
GIT_LOCATION = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX",
                "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")  # fmt: skip


def no_git_location() -> None:
    for name in GIT_LOCATION:
        os.environ.pop(name, None)
