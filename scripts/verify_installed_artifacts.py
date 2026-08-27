#!/usr/bin/env python3
"""Build, install, and probe Graphene without importing from the checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_MCP_PROBE = r"""
import asyncio
import json
import os
import sys
import tempfile
import time

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED = {
    "mission": [
        "start_goal", "plan_goal", "get_digest", "approve_plan", "approve_result",
        "reject_result", "mission_status", "why", "mission_summary",
    ],
    "legacy": [
        "search_repo", "read_file", "open_evidence", "write_file",
        "run_fixed_test", "request_completion",
    ],
}

async def probe():
    executable, mode, *details = sys.argv[1:]
    args = []
    if mode == "legacy":
        args = ["--task", "baseline_max_attempts", "--profile", "platform-maintainer@1"]
    async def open_session(action):
        parameters = StdioServerParameters(
            command=executable, args=args, cwd=os.getcwd(), env=dict(os.environ)
        )
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
            async with stdio_client(parameters, errlog=errors) as streams:
                async with ClientSession(*streams) as session:
                    initialized = await session.initialize()
                    tools = [tool.name for tool in (await session.list_tools()).tools]
                    result = await action(session)
            errors.seek(0)
            diagnostic = errors.read()
        assert initialized.server_info.name == "graphene"
        assert tools == EXPECTED[mode], tools
        assert diagnostic == "GRAPHENE_MCP_STDIO_READY\n", diagnostic
        return result, tools

    if mode == "legacy":
        async def initialized_only(session):
            return None
        _, tools = await open_session(initialized_only)
        print(json.dumps({"mode": mode, "tools": tools}, sort_keys=True))
        return

    repository, goal, criteria_json, base_sha = details
    request = {
        "repo": repository,
        "goal": goal,
        "request_id": "installed_north_star_no_key",
        "success_criteria_json": criteria_json,
        "driver": "gemini-adk",
        "max_workers": "2",
        "authorization_mode": "policy_pre_authorized",
        "finalization_mode": "auto_finalize_isolated",
    }

    async def start(session):
        started = time.monotonic()
        response = await session.call_tool("start_goal", request)
        assert response.is_error is False, response.content
        value = response.structured_content
        elapsed = time.monotonic() - started
        assert elapsed < 5, elapsed
        assert value["accepted_request_id"] == request["request_id"]
        assert value["requested_authorization_mode"] == "policy_pre_authorized"
        assert value["effective_authorization_mode"] is None
        assert value["authorization_mode"] is None
        assert value["finalization_mode"] == "auto_finalize_isolated"
        assert value["base_sha"] == base_sha
        assert value["committed_policy_revision"] == 1
        return value["mission_id"], elapsed

    (mission_id, latency), tools = await open_session(start)

    async def reattach(session):
        duplicate = await session.call_tool("start_goal", request)
        assert duplicate.is_error is False, duplicate.content
        assert duplicate.structured_content["mission_id"] == mission_id
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = await session.call_tool(
                "mission_status", {"mission_id": mission_id}
            )
            assert response.is_error is False, response.content
            status = response.structured_content
            if status["status"] == "failed":
                return status
            await asyncio.sleep(0.05)
        raise AssertionError("no-key mission did not reach a failed terminal state")

    status, _ = await open_session(reattach)
    print(json.dumps({
        "mode": mode,
        "tools": tools,
        "mission_id": mission_id,
        "accepted_under_five_seconds": latency < 5,
        "fresh_stdio_reattached": True,
        "terminal_status": status["status"],
    }, sort_keys=True))

asyncio.run(probe())
"""


def _run(
    argv: list[str | Path],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> str:
    command = [str(item) for item in argv]
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr or completed.stdout
        raise RuntimeError(f"{command!r} failed ({completed.returncode}):\n{detail}")
    return completed.stdout


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def _environment(home: Path, state: Path, database: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "GEMINI_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GRAPHENE_GITHUB_TOKEN",
        "PYTHONHOME",
        "PYTHONPATH",
        "SSH_AUTH_SOCK",
        "VIRTUAL_ENV",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "GRAPHENE_LINEAGE_DB": str(database),
            "GRAPHENE_STATE_DIR": str(state),
            "HOME": str(home),
            "NO_COLOR": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return environment


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_install(uv: str, artifact: Path, scratch: Path) -> dict[str, object]:
    environment_root = scratch / artifact.name.replace(".", "-")
    venv = environment_root / "venv"
    outside = _private(environment_root / "outside")
    home = _private(environment_root / "home")
    state = _private(environment_root / "state")
    legacy_runtime = _private(environment_root / "legacy-runtime")
    python = venv / "bin" / "python"
    graphene = venv / "bin" / "graphene"
    graphene_mcp = venv / "bin" / "graphene-mcp"

    _run([uv, "venv", "--python", sys.executable, venv], cwd=outside)
    _run([uv, "pip", "install", "--python", python, artifact], cwd=outside)
    env = _environment(home, state, legacy_runtime / "lineage.sqlite3")

    import_probe = _run(
        [
            python,
            "-I",
            "-c",
            (
                "import importlib.metadata as m,json,pathlib,sys; "
                "import graphene,graphene.legacy_app; "
                "from graphene.package_data import legacy_project_root,north_star_project_root; "
                "r=legacy_project_root(); n=north_star_project_root(); "
                "required=['contracts/golden_path.json','contracts/graph_mvp.json',"
                "'demo/fixture/SECURITY.md']; "
                "assert all((r/p).is_file() for p in required); "
                "assert (n/'scripts/materialize_north_star.py').is_file(); "
                "assert (n/'demo/north_star/repository/orders_api/verify_migration.py').is_file(); "
                "assert not any(x.lower().startswith('pytest') for x in "
                "(m.requires('graphene') or [])); "
                "assert 'pydantic==2.13.4' in (m.requires('graphene') or []); "
                "print(json.dumps({'module':graphene.__file__,'resources':str(r),"
                "'north_star_resources':str(n)}))"
            ),
        ],
        cwd=outside,
        env=env,
    )
    imported = json.loads(import_probe)
    assert not Path(imported["module"]).is_relative_to(ROOT)
    assert not Path(imported["resources"]).is_relative_to(ROOT)
    assert not Path(imported["north_star_resources"]).is_relative_to(ROOT)

    target = outside / "north-star-target"
    materialized = json.loads(
        _run(
            [
                python,
                "-I",
                "-c",
                (
                    "import io,json,sys; from pathlib import Path; "
                    "from graphene.demo_live import _materialize; "
                    "t=_materialize(Path(sys.argv[1]),io.StringIO()); "
                    "print(json.dumps({'repository':str(t.repository),'goal':t.goal,"
                    "'criteria':t.success_criteria,'base_sha':t.base_sha}))"
                ),
                target,
            ],
            cwd=outside,
            env=env,
        )
    )
    assert materialized["repository"] == str(target.resolve())

    _run([graphene, "--help"], cwd=outside, env=env)
    _run(
        [graphene, "demo", "--driver", "verified-replay", "--no-open", "--exit-after-demo"],
        cwd=outside,
        env=env,
    )
    _run(
        [graphene, "mission", "replay", "taskmaster", "--no-open", "--exit-after-replay"],
        cwd=outside,
        env=env,
    )
    _run([graphene, "ui", "--replay", "taskmaster", "--once"], cwd=outside, env=env)
    _run(
        [
            graphene,
            "--json",
            "run",
            "baseline_max_attempts",
            "--profile",
            "platform-maintainer@1",
        ],
        cwd=outside,
        env=env,
    )
    mission_probe = json.loads(
        _run(
            [
                python,
                "-I",
                "-c",
                _MCP_PROBE,
                graphene_mcp,
                "mission",
                materialized["repository"],
                materialized["goal"],
                json.dumps(materialized["criteria"], separators=(",", ":")),
                materialized["base_sha"],
            ],
            cwd=outside,
            env=env,
            timeout=90,
        )
    )
    assert mission_probe["accepted_under_five_seconds"] is True
    assert mission_probe["fresh_stdio_reattached"] is True
    assert mission_probe["terminal_status"] == "failed"

    legacy_mcp_runtime = _private(environment_root / "legacy-mcp-runtime")
    legacy_env = _environment(home, state, legacy_mcp_runtime / "lineage.sqlite3")
    _run(
        [python, "-I", "-c", _MCP_PROBE, graphene_mcp, "legacy"],
        cwd=outside,
        env=legacy_env,
    )
    return {
        "artifact": artifact.name,
        "artifact_sha256": _sha256(artifact),
        "installed_module": imported["module"],
        "installed_resources": imported["resources"],
        "installed_north_star_resources": imported["north_star_resources"],
        "north_star_target_base_sha": materialized["base_sha"],
        "north_star_no_key": mission_probe,
        "probes": [
            "entry-points",
            "verified-demo-replay",
            "mission-replay",
            "replay-ui",
            "installed-north-star-materialization",
            "legacy-cli-bootstrap",
            "mission-mcp-no-key-start-and-reattach",
            "legacy-mcp-initialize",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="fail unless the source tree exactly matches the reported Git revision",
    )
    arguments = parser.parse_args()
    uv = shutil.which("uv")
    if uv is None:
        parser.error("uv is required")

    revision = _run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    source_tree_clean = not _run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT
    ).strip()
    if arguments.require_clean and not source_tree_clean:
        parser.error("source tree does not exactly match HEAD")

    with tempfile.TemporaryDirectory(prefix="graphene-installed-proof-") as raw:
        scratch = Path(raw).resolve()
        dist = scratch / "dist"
        dist.mkdir()
        outside = _private(scratch / "build-outside")
        _run([uv, "build", "--sdist", "--no-sources", "--out-dir", dist, ROOT], cwd=outside)
        sdist, = dist.glob("*.tar.gz")
        _run([uv, "build", "--wheel", "--no-sources", "--out-dir", dist, sdist], cwd=outside)
        wheel, = dist.glob("*.whl")
        results = [_probe_install(uv, artifact, scratch) for artifact in (wheel, sdist)]
        target_base_shas = {
            result["north_star_target_base_sha"] for result in results
        }
        if len(target_base_shas) != 1:
            raise RuntimeError("installed artifacts materialized different target bases")
        target_base_sha = target_base_shas.pop()

    print(
        json.dumps(
            {
                "source_revision": revision,
                "source_tree_clean": source_tree_clean,
                "north_star_target_base_sha": target_base_sha,
                "artifacts": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
