# Releasing

Publishing is driven by a git tag: push the tag, GitHub Actions builds and publishes to PyPI.

## Every release

1. Bump the version in three places, and keep them identical (then `uv lock`):
   - `version` in `pyproject.toml`
   - `__version__` in `src/graphene_map/__init__.py`
   - the first line of `dev/launch/release-notes.md`, which a test checks against `pyproject.toml`: a bump
     that misses it fails the release run before the upload, and burns the tag
2. Write the release notes in `CHANGELOG.md`, its heading dated the day you tag, and in
   `dev/launch/release-notes.md`, the body of the GitHub release.
3. Commit them, land them on `main` and push `main` first: PyPI shows the README, and the README loads its
   pictures from `main`, so a tag cut before they are there publishes a page of broken images. Then tag `main`
   and push the tag:

   ```sh
   git push origin main
   git tag v0.9.0
   git push origin v0.9.0
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

   If the run fails before the upload (a red leg, as v0.5.1's did), nothing reached PyPI, but the tag is public:
   leave it where it is, fix main, bump to the next version and tag that. The changelog keeps the skipped version's
   heading and says it was never published.

5. When the run is green, make the GitHub release for the tag, with the VS Code extension built from the same
   commit attached (its version is in `editors/vscode/package.json`; the extension's README sends people here
   for it):

   ```sh
   (cd editors/vscode && npm ci && npm run package)
   gh release create v0.9.0 --title "Graphene 0.9.0" --notes-file dev/launch/release-notes.md \
     editors/vscode/graphene-0.9.0.vsix
   ```

   Publishing the release starts `publish-vscode.yml`: it builds the `.vsix` again from the tag and publishes
   that one file to the Marketplace and to Open VSX. Watch it with `gh run watch`. It refuses a release whose tag
   is not the extension's version, so bump the extension (below) before you tag.

## The VS Code extension

### Every release

1. Bump it with the CLI, in `editors/vscode/package.json` and its lock file in one go (the `package` script
   names its `.vsix` after that version):

   ```sh
   (cd editors/vscode && npm version 0.9.0 --no-git-tag-version)
   ```

2. Write its entry in `editors/vscode/CHANGELOG.md`, two lines at most a line.
3. Commit with the CLI's bump. The release publishes it (above). To publish without a release:

   ```sh
   gh workflow run publish-vscode.yml --ref main
   gh run watch
   ```

   The workflow builds the `.vsix` once and publishes it from two jobs, `marketplace` and `open-vsx`. When one
   refuses (Open VSX, on the first run, if a step above was missed), use **Re-run failed jobs** on the run's
   page (`gh run rerun <id> --failed`): only that registry runs again. A whole new run is refused by the
   registry that already has the version. By hand, from `editors/vscode` with the `.vsix` of the release
   beside you, the same two commands are `npx ovsx publish graphene-<version>.vsix -p <token>` and
   `npx vsce publish --packagePath graphene-<version>.vsix -p <token>`. A version a registry has is final;
   a wrong file there means the next version.

4. Look at both pages once: `https://marketplace.visualstudio.com/items?itemName=alex-lop.graphene-vscode` and
   `https://open-vsx.org/extension/alex-lop/graphene-vscode`. The Marketplace verifies a new publisher's first
   upload by hand, which can take an hour or so; the page says "being verified" until then.

### First time only (about 20 minutes)

Checked on 27 October 2026 from a terminal: the publisher id `alex-lop` was free on both. Open VSX answered
`GET https://open-vsx.org/api/alex-lop` with 404 `Namespace not found`, and the Marketplace's gallery query for
publisher `alex-lop` listed nothing and its publisher page gave 404. If either is taken by the time you sign up,
use `alexlop` on both, and change `publisher` in `editors/vscode/package.json` to match before you publish (the
extension's id becomes `alexlop.graphene-vscode`; the README's links above change with it).

**The Marketplace (VS Code), about 10 minutes.**

1. Sign in at <https://marketplace.visualstudio.com/manage> with a Microsoft account (a personal one is fine).
   Create a publisher: ID `alex-lop`, display name `Alex Lopez`. The ID is the part of the extension's id before
   the dot, and it cannot change later.
2. The token comes from Azure DevOps, not the Marketplace. Go to <https://dev.azure.com> with the same account;
   if it asks you to create an organization, create one with any name (the token is not tied to it).
   Then the user menu at the top right, **Personal access tokens**, **New Token**:
   - Name: `vsce`; Organization: **All accessible organizations** (a token for one organization is refused by
     the Marketplace); Expiration: custom, up to a year.
   - Scopes: **Custom defined**, click **Show all scopes**, under **Marketplace** tick **Manage** only.
   Copy the token: it is shown once.
3. Check it before you store it, from `editors/vscode`:

   ```sh
   VSCE_PAT=<the token> npx vsce verify-pat alex-lop
   ```

**Open VSX (Cursor, VSCodium, Gitpod), about 10 minutes.**

1. Sign in at <https://open-vsx.org> with GitHub (**Log in**, top right).
2. Open your profile (your avatar, then **Settings**). Under **Eclipse account** it asks you to link one: create
   it at <https://accounts.eclipse.org/user/register> with the same GitHub username filled in, then come back and
   sign the **Eclipse Foundation Open VSX Publisher Agreement** there. Publishing is refused until it is signed.
3. Under **Access Tokens**, generate one named `ovsx`. Copy it: it is shown once.
4. Create the namespace, from any directory:

   ```sh
   npx --yes ovsx@1.3.0 create-namespace alex-lop -p <the token>
   ```

   A namespace you created lets you publish into it. The page says "unverified" beside the publisher until
   you claim the namespace, which is optional. Do it once the Marketplace listing is up: open an issue at
   <https://github.com/EclipseFdn/open-vsx.org/issues/new/choose> with the **Claim namespace ownership** form
   (title "Claiming namespace alex-lop"). It asks for a GitHub account with at least 12 months of public
   history, and its quickest proof is the first option, the same publisher on the Marketplace with an
   extension there whose `package.json` names its repository, which ours does.

**The two secrets, one minute.** From the repository:

```sh
gh secret set VSCE_PAT   # paste the Azure DevOps token
gh secret set OVSX_PAT   # paste the Open VSX token
```

The workflow reads them as `secrets.VSCE_PAT` and `secrets.OVSX_PAT`. Tokens expire: the Azure one on the date
you chose, so the run's first error a year from now is "401" from the Marketplace, and the fix is a new token
and `gh secret set` again.

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
