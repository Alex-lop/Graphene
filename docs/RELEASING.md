# Releasing

Publishing is driven by a git tag: push the tag, GitHub Actions builds and publishes to PyPI.

## Every release

1. Bump the version in two places, and keep them identical (then `uv lock`; no test pins the number):
   - `version` in `pyproject.toml`
   - `__version__` in `src/graphene_map/__init__.py`
2. Write the release notes in `CHANGELOG.md`.
3. Commit both, then tag and push the tag:

   ```sh
   git tag v0.3.0
   git push origin v0.3.0
   ```

4. Watch the run:

   ```sh
   gh run watch
   ```

   The release first runs the whole suite on the tagged commit (`release.yml` calls `ci.yml`), builds the wheel,
   installs it into a clean virtualenv and runs `graphene --version` from it. Only if all of that passes does it
   publish. A tag push no longer starts a second CI run.

   After the upload it runs the published version, `uvx --isolated --from graphene-map==<version> graphene demo
   --cheat`, in a throwaway home, retrying while PyPI's index catches up. If that step fails the version is already
   on PyPI: the fix is a new version, and `gh run watch` shows the CI legs nested under the release run.

## First time only

PyPI has to be told to trust this repository. On PyPI, add a trusted publisher
to the `graphene-map` project with exactly these values:

- Owner: `Alex-lop`
- Repository: `Graphene`
- Workflow: `release.yml`
- Environment: `pypi`

Then create the matching environment on GitHub under Settings -> Environments,
named `pypi`. Without it the publish job cannot get the token it needs and the
run fails. Trusted publishing is why there is no API token or password here.
