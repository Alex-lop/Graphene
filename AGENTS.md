# For agents

Three things that have put a red build on `main`:

- **The README is pinned by tests.** After any edit to `README.md`, run `uv run pytest tests -k readme -q -n auto`
  (about twenty seconds). A test that pins words moves with the words: change the test in the same commit, and say
  so in the pull request.
- **Before you open a pull request**, run `uv run ruff check` and `uv run pytest -q -n auto` (about six minutes).
- **Never merge a pull request whose checks are running or red**, and never push to `main`. `main` requires the
  three `test (ubuntu-latest, …)` checks; do not pass `--admin` to get past them.

The direction is [dev/VISION.md](dev/VISION.md): a page that draws an agent's session as a graph, with nothing
to set up. The prompt that carries it out is [dev/prompts/sessions.md](dev/prompts/sessions.md); read both before
the code. A request that names no files is not a task. Do not search the repository for more to do.

The rest is in [CONTRIBUTING.md](CONTRIBUTING.md).
