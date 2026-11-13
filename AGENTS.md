# For agents

Three things that have put a red build on `main`:

- **The README is pinned by tests.** After any edit to `README.md`, run `uv run pytest tests -k readme -q -n auto`
  (about twenty seconds). A test that pins words moves with the words: change the test in the same commit, and say
  so in the pull request.
- **Before you open a pull request**, run `uv run ruff check` and `uv run pytest -q -n auto` (about six minutes).
- **Never merge a pull request whose checks are running or red**, and never push to `main`. `main` requires the
  three `test (ubuntu-latest, …)` checks; do not pass `--admin` to get past them.

The job is scoped. Read [dev/SCOPE.md](dev/SCOPE.md) and [dev/PRODUCT_NEXT.md](dev/PRODUCT_NEXT.md) before the
code, and take the prompt in [dev/prompts/workflow.md](dev/prompts/workflow.md). A request that names no files
is not a task. Do not search the repository for more to do.

The rest is in [CONTRIBUTING.md](CONTRIBUTING.md).
