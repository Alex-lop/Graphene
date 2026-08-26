---
description: Plan, sign, and run a goal inside the Graphene map
---

Run the Graphene loop toward this goal: $ARGUMENTS

Use the `graphene` MCP server (this repository ships it in `.mcp.json`). The
server's `goal` prompt carries the full instructions; the short form:

1. `plan_goal` with `repo` = this repository's absolute path and the goal above
   (`driver="scripted-local"` unless I asked for a live model run).
2. Show me the mission id, revision, `base_sha`, digest, and every node of the
   task graph with its dependencies. Tell me I can watch with `graphene ui`.
3. STOP. Ask me to sign by replying with the digest. Do not call `approve_plan`
   until I have typed it.
4. `approve_plan` with the digest I typed — never one you copied for me.
5. Poll `mission_status` until it is `awaiting_result`, `completed`, `failed`,
   or `cancelled`, or until `needs_you` names a decision; relay that verbatim.
6. `mission_summary`, relayed with its receipts line. If I ask why a file looks
   the way it does, call `why` with that path.

Never claim a step happened that a tool did not confirm.
