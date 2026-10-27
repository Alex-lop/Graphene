"""Where people install the VS Code extension: the publish workflow, the end-to-end job in CI, and the docs
that send Alex and a stranger to the right place. Read from the files, as test_packaging.py reads release.yml.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
PUBLISH = (ROOT / ".github/workflows/publish-vscode.yml").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()


def job(workflow: str, name: str) -> str:
    """The text of one job, from its name to the next job's."""
    after = workflow.split(f"\n  {name}:", 1)[1]
    return re.split(r"\n  \w[\w-]*:\n", after, maxsplit=1)[0]


def test_each_registry_publishes_in_a_job_of_its_own_so_one_refusal_can_be_rerun_alone():
    """One sequential job put Open VSX after the Marketplace: when Open VSX refused the first run, a second
    run failed at the Marketplace, which already had the version, and Open VSX never got it. Two jobs that
    both need the build and take its .vsix let "Re-run failed jobs" run only the registry that refused."""
    marketplace, open_vsx = job(PUBLISH, "marketplace"), job(PUBLISH, "open-vsx")
    for registry in (marketplace, open_vsx):
        assert "needs: build" in registry
        assert "actions/download-artifact" in registry  # the same file the build job made, not a new one
    assert "vsce@" in marketplace and "publish --packagePath" in marketplace and "ovsx" not in marketplace
    assert "ovsx@" in open_vsx and "publish graphene-" in open_vsx and "vsce" not in open_vsx
    assert "npm run package" in job(PUBLISH, "build") and "publish" not in job(PUBLISH, "build")


def test_the_end_to_end_job_stays_off_the_release_path_until_it_has_gone_green_and_cannot_hang_it():
    """release.yml calls ci.yml on a tag, and PyPI's upload waits for every job in it. The end-to-end job
    (a VS Code under xvfb, driven by Playwright) has not yet run on Linux; a red or hung run there would burn
    the tag. It skips itself on a tag until a green Linux run is on record, and it has a timeout: GitHub's
    default is six hours."""
    e2e = job(CI, "vscode-e2e")
    head = e2e.split("steps:", 1)[0]  # the job's own keys, before its steps
    assert re.search(r"\n    if: .*refs/tags/", head)
    assert re.search(r"\n    timeout-minutes: ([1-9]\d?)\n", head)


def test_releasing_names_open_vsxs_real_claim_form_and_what_it_asks():
    """RELEASING.md sent Alex to a "Publisher ownership request" template that open-vsx.org does not have. Its
    issue forms, read on 27 October 2026, are "Claim namespace ownership", "Release request" and a website
    issue; the claim asks for a GitHub account with twelve months of public history, and its quickest proof
    is the same publisher on the Marketplace with an extension there, so it comes after that listing."""
    said = (ROOT / "docs/RELEASING.md").read_text()
    assert "Publisher ownership request" not in said
    assert "Claim namespace ownership" in said
    assert "12 months" in said
    assert said.index("Marketplace listing is up") < said.index("Claim namespace ownership")


def test_the_readme_installs_the_vsix_the_package_script_makes_today():
    """The README told people to install graphene-0.9.0.vsix while package.json said 0.8.0, so `npm run
    package` made a file of another name. The README travels inside the .vsix: its install line names the
    version the manifest has, and a bump that forgets it fails here."""
    import json

    version = json.loads((ROOT / "editors/vscode/package.json").read_text())["version"]
    readme = (ROOT / "editors/vscode/README.md").read_text()
    assert f"code --install-extension graphene-{version}.vsix" in readme
    assert "graphene-0." not in readme.replace(f"graphene-{version}.vsix", "")  # no other version's file


def test_releasing_walks_one_version_through_its_commands():
    """Its tag example said v0.6.0 while its release and extension examples said 0.9.0: three places, two
    versions, for one procedure. Every version its commands name is the same one."""
    said = (ROOT / "docs/RELEASING.md").read_text()
    blocks = "\n".join(re.findall(r"```sh\n(.*?)```", said, re.DOTALL))
    blocks = re.sub(r"@\d+\.\d+\.\d+", "", blocks)  # a package pin such as ovsx@1.3.0 is not a release
    assert len(set(re.findall(r"\bv?(\d+\.\d+\.\d+)\b", blocks))) == 1  # the tag v0.9.0 and the file 0.9.0
