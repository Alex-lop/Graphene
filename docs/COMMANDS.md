# Command map

Every `graphene` verb, in one place. The [README](../README.md) shows the loop;
this page is the reference `tests/unit/test_readme_contract.py` holds the CLI to.

## Taskmaster entrypoints

`graphene init`, `graphene doctor`, `graphene plan`, `graphene status`,
`graphene bundle`, `graphene cancel`, `graphene mission`, `graphene request-replan`,
`graphene retry`, `graphene run`, `graphene task`, `graphene watch`, `graphene why`,
and `graphene ui` (the terminal view; see the README).

```bash
graphene plan GOAL --repo PATH --success-criterion CRITERION
graphene plan show MISSION_ID [--detail]         # the full contract of every node
graphene plan export MISSION_ID [--output FILE]  # canonical YAML — edit it
graphene plan revise EDITED_PLAN_FILE            # -> immutable revision N+1, new digest
graphene plan edit MISSION_ID                    # $EDITOR wrapper over export + revise
graphene plan diff MISSION_ID PREVIOUS_REVISION REVISION
graphene plan lint MISSION_ID                    # atomic: cycles, scopes, checks, budgets
graphene plan approve MISSION_ID --revision N    # binds mission + base_sha + revision + digest
graphene run MISSION_ID
graphene task input MISSION_ID TASK_ID --gate GATE_ID --file INPUT_FILE
graphene bundle verify FINAL_RESULT_ID
graphene why PATH --mission MISSION_ID [--json]
```

Approval binds four things at once: the mission, the `base_sha` the plan was
written against, the revision number, and the plan's SHA-256. Change any one of
them and the approval is void. Editing an approved plan produces immutable
revision N+1 with a new digest that needs its own approval; editing after
dispatch has begun fails closed; and no worker can claim a node of a revision
nobody approved.

`graphene plan show/diff/lint` reads verified revisions. `plan export` writes the
canonical YAML a person edits, `plan revise` compiles the edited file into
immutable revision N+1, and `plan edit` is a thin `$EDITOR` wrapper over exactly
that path — there is no second way to change a plan. `request-replan` only
pauses dispatch and records the request: it generates no linked replacement
revision, and nothing in Graphene asks a model to produce one. The revision a
`revise` compiles is the user's, not the planner's. `graphene task input`
accepts 1–4096 private UTF-8 bytes from a regular file or stdin and commits only
their evidence reference.

## Mission commands

`graphene mission start`, `graphene mission status`, `graphene mission watch`,
`graphene mission open`, `graphene mission pause`, `graphene mission resume`,
`graphene mission cancel`, `graphene mission retry`,
`graphene mission request-replan`, `graphene mission approve-plan`,
`graphene mission decide-gate`, `graphene mission approve-result`,
`graphene mission reject-result`, `graphene mission result`,
`graphene mission capsule`, `graphene mission db`, `graphene mission replay`,
`graphene mission demo`, and `graphene mission executor`.

Use `graphene mission result show MISSION_ID` to verify the candidate. Use
`graphene mission approve-result MISSION_ID --bundle-id FINAL_RESULT_ID` or
`graphene mission reject-result MISSION_ID --bundle-id FINAL_RESULT_ID`; both
bind the exact bundle. `graphene mission result export ...` and
`graphene bundle create/verify` write only create-new mode-`0600` review
artifacts and never mutate the checkout.

`graphene mission capsule export MISSION_ID --output DIR` writes a private
`MISSION_ID.graphene-capsule` directory holding the hash-chained mission events,
every attempt's evidence chain, trusted check and sanitized worker receipts,
publication envelope digests, plan revisions, and the registered final bundle,
with no prompts, source bytes, diffs, or command output.
`graphene mission capsule verify CAPSULE_DIR` recomputes every digest and chain
link from those files alone without opening the mission store.

The outbound surface is `graphene mission executor connect --repo PATH
--mission MISSION_ID --coordinator-url URL --audience AUDIENCE --workers 2`. It
touches local workspaces; Cloud Run does not.

## Watching for a change

```bash
graphene watch inbox --dir PATH [--once] [--poll 5]
graphene watch github --repo OWNER/NAME --label graphene-mission --target-repo PATH --driver DRIVER [--once] [--poll 60] [--state PATH]
```

A `*.yaml` dropped in the inbox or an open issue carrying the label creates one
proposed mission through the same `mission start` path and commits a
`mission.triggered` annotation that `graphene why` lists as the first stage.
The watcher only creates; plan approval stays with the operator. Proof status
for both paths is in [PROOF.md](PROOF.md).

## The MCP surface

`graphene-mcp` with no arguments serves the mission control plane over stdio
(the committed [`.mcp.json`](../.mcp.json) launches it as
`uv run --frozen graphene-mcp`): tools `plan_goal`, `get_digest`,
`approve_plan`, `mission_status`, `why`, `mission_summary`, and the prompt
`goal`, which instructs the calling agent to compile, show the digest, **stop
and ask the human to sign**, run inside the map, and relay the summary.
`approve_plan` requires the digest string and the store refuses any other.
Every argument is a string; forged or extra keys are rejected before dispatch.
The state root is the CLI's (`GRAPHENE_STATE_DIR` or `~/.graphene/state`), so
`graphene ui` sees the same missions. `graphene-mcp --task … --profile …` and
`--run RUN` remain the compatibility-only lineage tour
([`mcp_client_config.example.json`](mcp_client_config.example.json)).

## Compatibility-only commands

The compatibility-only Auth tour commands remain: `graphene inspect`,
`graphene replay`, `graphene review`, `graphene feedback`, `graphene answer`,
`graphene memory`, `graphene handoff`, `graphene promote`, and
`graphene demo --driver verified-replay|scripted-local|adk-fake`.
`graphene demo --live` is not one of them: it is the live mission sequence
described in [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

Automatic expiry and purge are not implemented. Current mission-plan validation
rejects `legacy_auth_v2`. Cloud streaming uses per-client polling; there is no
shared listener or fan-out.
