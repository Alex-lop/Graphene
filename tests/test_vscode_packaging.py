"""The VS Code extension (editors/vscode) as the repository holds it: what its manifest promises, what CI
does with it, and what the Python side leaves alone: ruff, pytest and the sdist."""

import json
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
EXT = ROOT / "editors" / "vscode"
MANIFEST = json.loads((EXT / "package.json").read_text())
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
CI = (ROOT / ".github/workflows/ci.yml").read_text()
STORE = ".graphene/graphene.db"

COMMANDS = ["Show Plan Graph", "Open Cockpit", "Auto…", "Set Envelope…", "Run Ready Tasks", "Stop", "Accept",
            "Accept All", "Add Step…", "Link…", "Edit Step…", "Drop Step", "Tell Agent…",
            "Set Up This Folder", "Refresh"]


def test_the_manifest_names_the_product_and_its_version():
    assert MANIFEST["name"] == "graphene-vscode"
    assert MANIFEST["displayName"] == "Graphene"
    assert MANIFEST["publisher"] == "alex-lop"
    assert MANIFEST["version"] == "0.8.0"
    assert MANIFEST["license"] == "Apache-2.0"
    assert MANIFEST["repository"]["url"] == PYPROJECT["project"]["urls"]["Repository"]
    assert MANIFEST["engines"]["vscode"] == "^1.95.0"


def test_the_extension_wakes_for_a_folder_with_a_store():
    assert f"workspaceContains:{STORE}" in MANIFEST["activationEvents"]


def test_every_command_is_titled_graphene_and_the_list_is_the_promised_one():
    titles = [c["title"] for c in MANIFEST["contributes"]["commands"]]
    assert titles == [f"Graphene: {name}" for name in COMMANDS]
    assert all(c["command"].startswith("graphene.") for c in MANIFEST["contributes"]["commands"])


def test_the_walkthrough_buttons_are_the_extensions_own_commands_and_its_picture_ships():
    [walk] = MANIFEST["contributes"]["walkthroughs"]
    ours = {c["command"] for c in MANIFEST["contributes"]["commands"]}
    linked = {m for s in walk["steps"] for m in re.findall(r"\(command:(graphene\.\w+)\)", s["description"])}
    assert linked == ours & {"graphene.init", "graphene.auto", "graphene.showGraph", "graphene.envelope"}
    shipped = (EXT / ".vscodeignore").read_text().split()
    for s in walk["steps"]:
        assert (EXT / s["media"]["image"]).is_file() and f"!{s['media']['image']}" in shipped, s["id"]


def test_the_activity_bar_shows_the_brand_mark_and_a_plan_view_and_the_graph():
    (container,) = MANIFEST["contributes"]["viewsContainers"]["activitybar"]
    assert container["title"] == "Graphene"
    icon = (EXT / container["icon"]).read_text()
    brand = (ROOT / "docs/brand/mark-small/graphene-mark-small-currentColor.svg").read_text()
    assert icon == brand  # the mark as the brand draws it, in currentColor so the bar's own colour paints it
    views = {v["id"]: v for v in MANIFEST["contributes"]["views"]["graphene"]}
    assert views["graphene.plan"]["name"] == "Plan"
    assert views["graphene.graph"]["type"] == "webview"


def test_the_settings_are_the_command_and_the_poll():
    props = MANIFEST["contributes"]["configuration"]["properties"]
    assert props["graphene.path"]["default"] == "graphene"
    assert props["graphene.path"]["scope"] == "machine"  # a cloned folder's settings never choose what runs
    assert props["graphene.pollMs"]["default"] == 1500
    assert MANIFEST["capabilities"]["untrustedWorkspaces"]["supported"] is False  # off in Restricted Mode


def test_no_runtime_dependencies_and_every_dev_one_pinned_exactly():
    assert "dependencies" not in MANIFEST
    for name, version in MANIFEST["devDependencies"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{name} is not pinned exactly: {version}"
    assert MANIFEST["devDependencies"]["@types/vscode"] == "1.95.0"  # never newer than engines.vscode


def test_the_package_script_builds_the_vsix_and_never_publishes():
    scripts = MANIFEST["scripts"]
    assert "graphene-0.8.0.vsix" in scripts["package"]
    assert "publish" not in " ".join(scripts.values())
    assert "npm run build" in scripts["test"]  # the smoke test runs the built extension


def test_the_lockfile_is_committed_and_the_builds_are_not():
    assert (EXT / "package-lock.json").exists()
    ignored = (EXT / ".gitignore").read_text().split()
    assert {"node_modules/", "out/", "dist/", "*.vsix"} <= set(ignored)
    listed = subprocess.run(["git", "ls-files", "editors/vscode"], cwd=ROOT, capture_output=True, text=True)
    tracked = listed.stdout
    assert "editors/vscode/package-lock.json" in tracked
    assert not re.search(r"editors/vscode/(node_modules|dist|out)/|\.vsix$", tracked, re.MULTILINE)


def test_the_licence_is_the_repositorys():
    assert (EXT / "LICENSE").read_text() == (ROOT / "LICENSE").read_text()


def test_the_readme_says_how_it_is_installed_and_whose_click_it_is():
    readme = (EXT / "README.md").read_text()
    assert "code --install-extension graphene-0.8.0.vsix" in readme
    assert "graphene state --json" in readme
    assert "A click in VS Code is the person's" in readme
    assert "uv tool install graphene-map" in readme


def test_the_source_takes_the_agent_marks_out_before_it_runs_graphene():
    source = (EXT / "src/commands.ts").read_text()
    for mark in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX", "AI_AGENT",
                 "GRAPHENE_NODE", "GRAPHENE_PLANNER", "GEMINI_CLI", "CURSOR_AGENT"):
        assert f'"{mark}"' in source
    extension = (EXT / "src/extension.ts").read_text()
    assert "GRAPHENE_AS" not in extension and "GRAPHENE_WATCH" not in extension  # stand-in marks: never set


def test_the_fixtures_follow_the_state_schema():
    for name in ("empty", "proposals", "running", "auto"):
        state = json.loads((EXT / "test/fixtures" / f"{name}.json").read_text())
        assert state["schema"] == 1
        assert set(state) >= {"goal", "envelope", "auto", "run", "spent", "scoreboard", "questions", "goals",
                              "tasks", "edges", "news"}
        for task in state["tasks"]:
            assert task["state"] in {"running", "review", "came back", "ready", "waiting", "proposed", "done",
                                     "yours"}
            assert {"id", "title", "state", "scope", "needs", "forks"} <= set(task)
    running = json.loads((EXT / "test/fixtures/running.json").read_text())
    greet = next(t for t in running["tasks"] if t["id"] == "greet")
    assert [f["letter"] for f in greet["forks"]] == ["a", "b", "c"] and greet["kept"]["letter"] == "b"


def test_ci_builds_the_extension_in_a_job_of_its_own_and_the_python_matrix_is_untouched():
    assert re.search(r"^  vscode:[^\n]*\n    runs-on: ubuntu-latest\n", CI, re.MULTILINE)
    job = CI.split("\n  vscode:", 1)[1]
    assert "working-directory: editors/vscode" in job
    assert "node-version: 22" in job
    assert all(step in job for step in ("npm ci", "npm test", "npm run package"))
    assert "os: [ubuntu-latest, macos-latest]" in CI and 'python: ["3.12", "3.13", "3.14"]' in CI


def test_the_python_tools_leave_the_editors_alone():
    assert "editors" in PYPROJECT["tool"]["ruff"]["extend-exclude"]
    assert "editors" in PYPROJECT["tool"]["pytest"]["ini_options"]["norecursedirs"]
    assert "editors" not in " ".join(PYPROJECT["tool"]["pytest"]["ini_options"]["testpaths"])
    excluded = PYPROJECT["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    builds = {f"editors/vscode/{what}" for what in ("node_modules", "out", "dist", "*.vsix")}
    assert builds <= set(excluded)


@pytest.mark.skipif(shutil.which("uv") is None, reason="builds the sdist as CI does, with uv")
def test_the_sdist_carries_the_extensions_source_and_none_of_its_builds(tmp_path):
    built = subprocess.run(["uv", "build", "--sdist", "--out-dir", str(tmp_path), str(ROOT)],
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    (sdist,) = tmp_path.glob("*.tar.gz")
    names = tarfile.open(sdist).getnames()
    assert any(n.endswith("editors/vscode/src/extension.ts") for n in names)
    assert not any(re.search(r"editors/vscode/(node_modules|dist|out)/|\.vsix$", n) for n in names)
