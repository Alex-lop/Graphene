"""CP-C3: the /graphene loop end to end, on this repository, over MCP, with the map attached.

    uv run --frozen python scripts/e2e_mcp_loop.py OUTPUT_DIR

Clones this repository's HEAD into a private scratch directory (the target),
runs `graphene init` on it, starts `graphene-mcp` exactly as `.mcp.json`
does, attaches `graphene ui --frames` from a second process, and drives the
loop with the official MCP client: plan_goal -> the digest is shown -> a
forged digest is refused -> the shown digest is signed -> approve_plan runs
the fixture -> mission_status until awaiting_result -> mission_summary ->
why on a touched path. Writes transcript.md, transcript.jsonl, the frames,
and a README that lists every beat found. Exit 0 only if every beat is
present. Credential-free; macOS only (the scripted fixture needs
/usr/bin/sandbox-exec).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEATS = [
    "target cloned",
    "graphene init",
    "server ready",
    "tools listed",
    "goal prompt rendered",
    "plan_goal proposed",
    "digest shown",
    "forged digest refused",
    "digest signed",
    "approve_plan ran the map",
    "mission_status awaiting_result",
    "mission_summary",
    "why lineage",
    "ui frames captured",
]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    sys.path.insert(0, str(ROOT / "backend"))
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    from graphene.orchestration.scripted import load_scenario, scripted_supported

    if not scripted_supported():
        sys.stderr.write("the scripted fixture needs the macOS sandbox; nothing captured\n")
        return 3
    output = Path(argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    transcript: list[dict[str, object]] = []
    found: list[str] = []

    def beat(name: str, **detail: object) -> None:
        assert name in BEATS, name
        found.append(name)
        transcript.append({"t": round(time.monotonic() - started, 3), "beat": name, **detail})

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="graphene-e2e-") as scratch:
        scratch_path = Path(scratch).resolve()
        state = scratch_path / "state"
        state.mkdir(mode=0o700)
        target = scratch_path / "Graphene"
        subprocess.run(["git", "clone", "-q", str(ROOT), str(target)], check=True)
        head = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        beat("target cloned", head=head, target="<scratch>/Graphene")
        env = {**os.environ, "GRAPHENE_STATE_DIR": str(state), "NO_COLOR": "1"}
        subprocess.run(["uv", "run", "--frozen", "graphene", "init", "--repo", str(target)], cwd=ROOT, check=True, capture_output=True, env=env)
        beat("graphene init", policy="<target>/.graphene/project.json")
        config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["graphene"]
        errors = (output / "server-stderr.txt").open("w+", encoding="utf-8")
        parameters = StdioServerParameters(command=config["command"], args=config["args"], cwd=ROOT, env=env)
        frames = output / "frames"
        viewer: subprocess.Popen[str] | None = None

        async def loop() -> None:
            nonlocal viewer
            async with stdio_client(parameters, errlog=errors) as streams:
                async with ClientSession(*streams) as session:
                    init = await session.initialize()
                    beat("server ready", server=init.server_info.name, protocol=init.protocol_version)
                    tools = [tool.name for tool in (await session.list_tools()).tools]
                    prompts = [prompt.name for prompt in (await session.list_prompts()).prompts]
                    beat("tools listed", tools=tools, prompts=prompts)
                    goal = load_scenario().goal
                    rendered = await session.get_prompt("goal", {"goal": goal})
                    text = rendered.messages[0].content.text
                    beat("goal prompt rendered", stop_line="STOP AND ASK THE HUMAN TO SIGN" in text)

                    planned = await session.call_tool("plan_goal", {"repo": str(target), "goal": goal, "driver": "scripted-local"})
                    assert planned.is_error is False, planned.content
                    plan = planned.structured_content
                    mission_id, digest = plan["mission_id"], plan["digest"]
                    beat("plan_goal proposed", mission_id=mission_id, revision=plan["plan_revision"], base_sha=plan["base_sha"], nodes=[n["task_id"] for n in plan["task_graph"]])
                    shown = (await session.call_tool("get_digest", {"mission_id": mission_id})).structured_content
                    beat("digest shown", digest=shown["digest"], signed=shown["signed"])

                    viewer = subprocess.Popen(
                        [sys.executable, "-m", "graphene.cli.main", "ui", "--mission", mission_id, "--frames", str(frames), "--poll", "0.02", "--max-seconds", "240"],
                        env={**env, "PYTHONPATH": str(ROOT / "backend")}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    )
                    forged = digest[:-1] + ("0" if digest[-1] != "0" else "1")
                    refused = await session.call_tool("approve_plan", {"mission_id": mission_id, "digest": forged})
                    beat("forged digest refused", is_error=refused.is_error, message=refused.content[0].text if refused.content else "")
                    assert refused.is_error is True

                    # The human's signature: in this scripted run the operator is the
                    # script, and it signs exactly the digest the server showed.
                    beat("digest signed", digest=digest, by="scripted operator (not a person)")
                    approved = await session.call_tool("approve_plan", {"mission_id": mission_id, "digest": digest, "rationale": "e2e: the shown digest, signed by the scripted operator"})
                    assert approved.is_error is False, approved.content
                    run = approved.structured_content
                    beat("approve_plan ran the map", status=run["run"].get("status"), approval_truth=run["approval_truth"], attempts=run["run"].get("attempt_count"))

                    for _ in range(600):
                        status = (await session.call_tool("mission_status", {"mission_id": mission_id})).structured_content
                        if status["status"] in {"awaiting_result", "completed", "failed", "cancelled"}:
                            break
                        await asyncio.sleep(0.2)
                    beat("mission_status awaiting_result", status=status["status"], signed=status["signed"], states={t["task_id"]: t["state"] for t in status["tasks"]}, next_actions=status["next_actions"])
                    assert status["status"] == "awaiting_result"

                    summary = (await session.call_tool("mission_summary", {"mission_id": mission_id})).structured_content
                    beat("mission_summary", nodes=summary["nodes"], artifacts_touched=summary["artifacts_touched"], result=summary["result"], receipts=summary["receipts"], head_seq=summary["head_seq"])
                    path = summary["artifacts_touched"][0]
                    lineage = (await session.call_tool("why", {"mission_id": mission_id, "path": path})).structured_content
                    beat("why lineage", path=path, matched_by=lineage["matched_by"], stages={link["stage"]: link["status"] for link in lineage["links"]})
                    (output / "summary.txt").write_text(summary["text"] + "\n", encoding="utf-8")

        try:
            asyncio.run(loop())
        finally:
            errors.close()
        out, err = viewer.communicate(timeout=300) if viewer else ("", "")
        files = sorted(frames.glob("frame-*.txt"))
        beat("ui frames captured", frames=len(files), viewer_exit=viewer.returncode if viewer else None, viewer_stdout=out.strip())
        server_stderr = (output / "server-stderr.txt").read_text(encoding="utf-8")

    (output / "transcript.jsonl").write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in transcript), encoding="utf-8")
    lines = ["# /graphene loop over MCP — end to end on this repository", "",
             f"Target: a fresh clone of this repository at `{head}`, initialised with `graphene init`.",
             "Server: `graphene-mcp` launched exactly as `.mcp.json` launches it (`uv run --frozen graphene-mcp`).",
             "Client: the official Python MCP client over stdio. Viewer: `graphene ui --frames` in a second process, attached before approval.",
             "Driver: `scripted-local` — the credential-free fixture. The operator that signs is this script, not a person.", "",
             "## Beats", ""]
    for item in transcript:
        detail = {k: v for k, v in item.items() if k not in {"t", "beat"}}
        lines.append(f"- **{item['t']:7.3f}s** {item['beat']} — `{json.dumps(detail, sort_keys=True)[:400]}`")
    missing = [b for b in BEATS if b not in found]
    lines += ["", "## Verdict", "",
              f"Beats present: {len(found)}/{len(BEATS)}" + (f"; missing: {missing}" if missing else " — every beat present."),
              f"Server stderr: `{server_stderr.strip()}` (exactly the readiness token).",
              "What this proves: the six tools and the `goal` prompt over real stdio, the digest refused when forged and honoured when signed, execution inside the signed map, the summary and lineage from the store, and the map moving on screen in a separate read-only process.",
              "What it does not prove: a person signing in a chat client; a live model mission; Codex or Gemini CLI driving the same server."]
    (output / "transcript.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.write(f"{len(found)}/{len(BEATS)} beats, {len(files)} frames -> {output}\n")
    ok = not missing and server_stderr == "GRAPHENE_MCP_STDIO_READY\n" and len(files) >= 5
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
