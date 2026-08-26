# /graphene loop over MCP — end to end on this repository

Target: a fresh clone of this repository at `4874af381ad5765578a556e71bb31832a2df9ca2`, initialised with `graphene init`.
Server: `graphene-mcp` launched exactly as `.mcp.json` launches it (`uv run --frozen graphene-mcp`).
Client: the official Python MCP client over stdio. Viewer: `graphene ui --frames` in a second process, attached before approval.
Driver: `scripted-local` — the credential-free fixture. The operator that signs is this script, not a person.

## Beats

- **  1.493s** target cloned — `{"head": "4874af381ad5765578a556e71bb31832a2df9ca2", "target": "<scratch>/Graphene"}`
- **  2.818s** graphene init — `{"policy": "<target>/.graphene/project.json"}`
- **  3.971s** server ready — `{"protocol": "2025-11-25", "server": "graphene"}`
- **  3.974s** tools listed — `{"prompts": ["goal"], "tools": ["plan_goal", "get_digest", "approve_plan", "mission_status", "why", "mission_summary"]}`
- **  3.976s** goal prompt rendered — `{"stop_line": true}`
- **  4.319s** plan_goal proposed — `{"base_sha": "e5995606e3cdcf37737dc613e2f391e229726358", "mission_id": "mission_start_5541d5c504fa7f8409087233", "nodes": ["assemble_candidate", "redact_notes", "render_json", "render_markdown", "verify_candidate", "wire_cli"], "revision": 1}`
- **  4.350s** digest shown — `{"digest": "cddcda3f19194df275e7be75c9fe2ba9b087fa4ebfd69ed7893b97754040bf8c", "signed": false}`
- **  4.397s** forged digest refused — `{"is_error": true, "message": "Error executing tool approve_plan: plan approval digest does not match the committed revision"}`
- **  4.397s** digest signed — `{"by": "scripted operator (not a person)", "digest": "cddcda3f19194df275e7be75c9fe2ba9b087fa4ebfd69ed7893b97754040bf8c"}`
- ** 11.441s** approve_plan ran the map — `{"approval_truth": "server_derived: relayed by the agent, not TTY-attested", "attempts": 7, "status": "awaiting_result"}`
- ** 11.553s** mission_status awaiting_result — `{"next_actions": ["graphene mission result show mission_start_5541d5c504fa7f8409087233", "graphene mission approve-result mission_start_5541d5c504fa7f8409087233 --bundle-id FINAL_RESULT_ID", "graphene mission reject-result mission_start_5541d5c504fa7f8409087233 --bundle-id FINAL_RESULT_ID"], "signed": true, "states": {"assemble_candidate": "done", "redact_notes": "done", "render_json": "done", "re`
- ** 11.630s** mission_summary — `{"artifacts_touched": ["status_report/cli.py", "status_report/redact.py", "status_report/render_json.py", "status_report/render_markdown.py", "tests/test_cli.py", "tests/test_redact.py", "tests/test_render_json.py", "tests/test_render_markdown.py"], "head_seq": 61, "nodes": [{"attempts": 1, "outcome": "passed", "state": "done", "task_id": "assemble_candidate"}, {"attempts": 1, "outcome": "passed",`
- ** 11.742s** why lineage — `{"matched_by": "path", "path": "status_report/cli.py", "stages": {"accepted_inputs": "established", "approval": "unknown", "assembly_candidate": "established", "prior_attempts": "not_present", "producer_attempt": "established", "target": "established", "verification": "established"}}`
- ** 12.469s** ui frames captured — `{"frames": 16, "viewer_exit": 0, "viewer_stdout": "wrote 16 frame(s) to /Users/alexlopez/Desktop/AllThingsAgenticHackathon/evidence/integration/2026-08-26/frames"}`

## Verdict

Beats present: 14/14 — every beat present.
Server stderr: `GRAPHENE_MCP_STDIO_READY` (exactly the readiness token).
What this proves: the six tools and the `goal` prompt over real stdio, the digest refused when forged and honoured when signed, execution inside the signed map, the summary and lineage from the store, and the map moving on screen in a separate read-only process.
What it does not prove: a person signing in a chat client; a live model mission; Codex or Gemini CLI driving the same server.
