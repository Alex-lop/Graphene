# X4 repo pick: pytest-dev/pytest-bdd, issue #476

Picked 2026-10-10. Everything on GitHub was read-only (searches, issue lists, PR lookups). I cloned six candidates under `scratchpad/x4-candidates/` and removed `origin` from each clone right after cloning. Nothing was committed or pushed.

## Chosen repository

| Fact | Value |
|---|---|
| Full name | `pytest-dev/pytest-bdd` |
| Clone URL | https://github.com/pytest-dev/pytest-bdd.git |
| Pinned HEAD | `0e04014fd56b325d702b6926d5dc9a8705636c2c` (branch `master`, 2026-10-06, "[pre-commit.ci] pre-commit autoupdate (#840)") |
| License | MIT (`LICENSE.txt`; `license = "MIT"` in `pyproject.toml`) |
| Python lines in `src/` | 3,145 (`find src -name '*.py' \| xargs wc -l`) |
| Layout | `src/pytest_bdd/`, tests under `tests/`, `pyproject.toml` with the `uv_build` backend, `uv.lock` committed |
| `uv sync` | exit 0 in 1.08 s (warm uv cache) |
| `uv run pytest -q` | **146 passed in 8.28 s** (9.52 s wall, including `uv run`) |
| Python picked by uv | CPython 3.13.9 (`requires-python = ">=3.10"`, no `.python-version` file) |
| Local clone | `scratchpad/x4-candidates/pytest-bdd` (no remotes, clean tree) |

## The issue

- **Number:** #476
- **Title:** print tags in gherkin-terminal-reporter
- **URL:** https://github.com/pytest-dev/pytest-bdd/issues/476
- **State:** open, unassigned, labels `good first issue` and `feature`, opened 2022-01-04, 4 comments

Body, copied as-is (GitHub stores it with CRLF line endings; they are converted to LF here):

````text
Hello, I am using the Gherkin tags in the feature specification to refer scenarios to different software requirements and it would be really convenient to be able to get those tags printed when I run pytest with the `--gherkin-terminal-reporter` option. I know they are generated into the cucumber JSON but that's less human readable as of right now.

The feature looks like this:
```
@R1.1 @R1.2
  Scenario: Send packages to socket
    Given a service listening on a random socket
    When tool sends "2" packages to socket
    Then "2" packages are received in the service
```

So it would be great to get the tags formatted in some way in the output of the test:

```
$ pytest --gherkin-terminal-reporter -vv
===================================================================================== test session starts =====================================================================================                                                                          

tests/pacsio_test.py::test_send_packages_to_socket <- utilities/pacs_io/.venv/lib/python3.8/site-packages/pytest_bdd/scenario.py 
Feature: Tool for network testing
    Scenario: Send packages to socket
    Given a service listening on a random socket
    When tool sends "2" packages to socket
    Then "2" packages are received in the service
    PASSED
    (tags: R1.1, R1.2)
```
````

**Reproduced at the pinned SHA.** I ran the issue's scenario through the clone's environment (`pytest --gherkin-terminal-reporter -vv`, in a scratch directory outside the clone). The current output has no tags at all:

```text
Feature: Tool for network testing
    Scenario: Send packages to socket
        Given a service listening on a random socket
        When tool sends "2" packages to socket
        Then "2" packages are received in the service
    PASSED
```

The issue expects an extra line after `PASSED` such as `(tags: R1.1, R1.2)`.

## How it meets each criterion

- **Python, `src/` layout, pytest under `tests/`, `pyproject.toml` that `uv sync` builds:** the package is in `src/pytest_bdd/`, the tests are in `tests/` (`pytest.ini` sets `testpaths = tests`), and `uv sync` builds it with `uv_build` on the first try.
- **Permissive license:** MIT.
- **Under 10,000 lines in `src/`:** 3,145.
- **`uv run pytest -q` green and under 2 minutes:** 146 passed in 8.28 s. I ran it under `perl -e 'alarm 180; exec @ARGV'`.
- **Open "good first issue" with a concrete, testable ask:** it is a small feature, and the issue shows the expected output. The change is in one 120-line file, `src/pytest_bdd/gherkin_terminal_reporter.py`, which prints the feature, rule, scenario and steps but never the tags. The tags already reach the reporter: `src/pytest_bdd/reporting.py:158` puts `"tags": sorted(scenario.tags)` into the scenario dict that the reporter reads. `tests/feature/test_gherkin_terminal_reporter.py` (398 lines) has pytester tests that check `-v` and `-vv` output, so the new test can follow them. An agent should finish this in well under an hour.
- **Not already closed by a merged PR:** nothing that references the issue has been merged:
  - #477 (2022) is still open. The maintainer asked for tests and it never got them.
  - #807 (2026-04) is open. Maintainer `youtux` approved it twice, then requested changes on 2026-09-14 to add a changelog line.
  - #799 and #830 were closed without merging.

## Notes for the planner

- **#807 may merge soon.** Our clone is pinned, so that doesn't affect the experiment. Once it merges, its diff is a maintainer-approved answer to compare against.
- **Tags become pytest marks.** The 2022 comment in the thread ran into `PytestUnknownMarkWarning` when a feature file used unregistered tags. A new pytester test needs to register those marks or filter the warning. `pytest.ini` turns warnings into errors only for those coming from the `pytest_bdd` package.
- **Output format is partly open.** The issue only shows `-vv` output with a `(tags: ...)` line. It doesn't say what `-v` should print, or whether feature-level and rule-level tags count. The tags are already sorted in the report context. The maintainer asked #807 for a `CHANGES.rst` entry, so the change should add one too.

## Runners-up

### 1. danieldeer/seriousdb, issue #275

| Fact | Value |
|---|---|
| Clone URL | https://github.com/danieldeer/seriousdb.git |
| Pinned HEAD | `1ea220c88afae885c28e51b113d8beb5e0b055c2` (`main`, 2026-10-03) |
| License | MIT |
| Python lines in `src/` | 1,068 (`src/seriousdb/`) |
| Tests | 182 passed in 0.83 s (1.41 s wall); setuptools backend, `uv.lock` committed |
| Python picked by uv | CPython 3.13.9 (`requires-python = ">=3.11"`) |

**Issue:** #275, "A stored null makes a key unreadable and undeletable, and delete() mutates before raising", https://github.com/danieldeer/seriousdb/issues/275. Labels `bug` and `good first issue`.

**Why it is not the pick:**
- It is a real bug with a script that reproduces it, but the code has moved on since the report. At the pinned SHA, `delete()` no longer mutates before raising, so the issue's final `assert` now passes.
- What is still broken: a key whose value is `null` in the database file shows up in `count()` and `exists()`, but `get()` and `delete()` both raise `ResourceNotFoundError`.
- The maintainer's comment changes the fix from what the issue body suggests: reject `None` in `set`, and treat a file containing `null` values as corrupt on load.
- The issue is assigned to `cophilot`, whose PR #284 was closed without merging on 2026-10-05.

### 2. OpenLucasKaka/bareloop, issue #19

| Fact | Value |
|---|---|
| Clone URL | https://github.com/OpenLucasKaka/bareloop.git |
| Pinned HEAD | `b58e39609542fe2334deb831b55aeb5f011a7d0f` (`main`, 2026-10-10) |
| License | MIT |
| Python lines in `src/` | 8,163 (`src/bareloop/`) |
| Tests | 262 passed in 10.76 s (11.80 s wall); hatchling backend, `uv.lock` committed |
| Python picked by uv | CPython 3.13.9 (`requires-python = ">=3.12"`) |

**Issue:** #19, "feat(cli): add /stats and /compact interactive slash commands", https://github.com/OpenLucasKaka/bareloop/issues/19. Labels `enhancement` and `good first issue`. Opened 2026-10-10, no comments, no PRs.

**Why it is not the pick:**
- It asks for two features in an interactive prompt_toolkit loop (`src/bareloop/main.py`).
- `/stats` needs token and tool counts summed over the whole session, and nothing in the code keeps those totals yet. That leaves more design to the agent than #476 does.
- The repo is at version 0.1.0 and changes quickly.
- The same repo's #11 (`BARELOOP_ENABLE_MCP=false`) is a smaller task, but its body lost every inline-code word (for example "Read  from environment variables (defaults to )").

## Near-misses dropped by the 10,000-line rule

These were cloned and counted. They have good issues but too many lines in `src/`:

- **mldsveda/PyScrappy, #186** (noise-removal regex over-matches): 10,343 lines. Of all the issues I read, this one is best specified: it has a repro snippet, the expected result and a list of tests, and no PRs reference it.
- **hermes-labs-ai/lintlang, #162** (discover `.cursor/rules`): 10,345 lines. Open PR #170.
- **anthropics/claude-agent-sdk-python, #1359** (`1e6` ceiling parsing): 13,295 lines. Five open PRs.

## Method

1. I ran four `gh search repos` queries: sorted by updated (`--size '<4000'`), by stars (`--size '<2000'`), by help-wanted issues, and by forks (updated after 2026-09-01). Together they returned 363 repos. After dropping copyleft licenses and repos with no license, 300 were left.
2. A GET of each repo's root contents showed that 53 have both `src/` and `pyproject.toml`, and 44 of those also have `tests/`.
3. I listed the open good-first-issue issues in each of those 44 repos, read the promising ones, and used the issue timeline API to find PRs that reference them.
4. I cloned six repos (`git clone --depth 100`, then `git remote remove origin`). Three failed the line count, and the other three all passed `uv sync` and `pytest`.
