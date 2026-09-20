# Releasing

Publishing is driven by a git tag: push the tag, GitHub Actions builds and publishes to PyPI.

## Every release

1. Bump the version in three places, and keep them identical (then `uv lock` and `npm --prefix ui install`):
   - `version` in `pyproject.toml`
   - `__version__` in `src/graphene_debrief/__init__.py`
   - `"version"` in `ui/package.json`
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

   The workflow builds the wheel, installs it into a clean virtualenv and runs
   `graphene --version` from it. Only if that passes does it publish.

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
