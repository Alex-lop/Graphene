import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  TASK_STATES,
  applyDelta,
  applyThrough,
  canonicalJson,
  createState,
  graphView,
  snapshotHashPayload,
  stateBuckets,
  taskEvidenceTarget,
} from "../../backend/graphene/orchestration/static/mission_reducer.mjs";

const replay = JSON.parse(readFileSync(new URL("../../backend/graphene/orchestration/static/mission-replay.json", import.meta.url), "utf8"));

test("Python and JavaScript agree on every replay snapshot hash", () => {
  let state = createState(replay.snapshot);
  const snapshots = [replay.snapshot];
  for (const envelope of replay.deltas) {
    state = applyDelta(state, envelope);
    snapshots.push({
      view_version: 1, mission: state.mission, head: state.head, cursor: state.cursor,
      tasks: [...state.tasks.values()], attempts: [...state.attempts.values()], workers: [...state.workers.values()],
      gates: [...state.gates.values()], publications: [...state.publications.values()], relationships: [...state.relationships.values()],
      integration: state.integration, verification: state.verification, resources: state.resources, needs_you: state.needsYou,
      critical_path_task_ids: state.criticalPathTaskIds, result: state.result, unknowns: state.unknowns, snapshot_sha256: state.snapshotSha256,
    });
  }
  for (const snapshot of snapshots) {
    const digest = createHash("sha256").update(canonicalJson(snapshotHashPayload(snapshot))).digest("hex");
    assert.equal(digest, snapshot.snapshot_sha256);
  }
  assert.equal(state.snapshotSha256, replay.meta.final_snapshot_sha256);
});

test("replay shows concurrency, denial, retry, one decision, and ordered result", () => {
  const states = replay.deltas.map((_, index) => applyThrough(replay.snapshot, replay.deltas, index + 1));
  assert.equal([...states[0].tasks.values()].filter((item) => item.state === "running").length, 2);
  assert.equal(createState(replay.snapshot).needsYou.gate_id, "gate_privacy_default");
  assert.equal(states[0].needsYou, null);
  assert.ok([...states[1].attempts.values()].some((item) => item.evidence_refs.some((ref) => ref.kind === "command_denial")));
  assert.equal(states[2].tasks.get("render_markdown").state, "retrying");
  assert.equal([...states[3].attempts.values()].filter((item) => item.task_id === "render_markdown").length, 2);
  const final = states.at(-1);
  assert.equal(final.integration.state, "done"); assert.equal(final.verification.state, "done"); assert.equal(final.result.state, "commit_created");
});

test("table buckets and graph use exact states and explicit typed relationships", () => {
  const state = createState(replay.snapshot);
  assert.deepEqual(stateBuckets(state).map((item) => item.status), TASK_STATES);
  const graph = graphView(state); const ids = new Set(graph.nodes.map((item) => item.id));
  assert.ok(graph.edges.some((item) => item.kind === "decomposed_into"));
  assert.ok(graph.edges.every((item) => ids.has(item.source) && ids.has(item.target)));
  assert.deepEqual(taskEvidenceTarget(applyThrough(replay.snapshot, replay.deltas), "render_markdown"), { kind: "generic", attemptId: "attempt_render_markdown_2" });
});

test("Mission Control is DOM-safe, table-first, keyboard reachable, responsive, and stale-explicit", () => {
  const source = readFileSync(new URL("../../backend/graphene/orchestration/static/mission_control.mjs", import.meta.url), "utf8");
  const html = readFileSync(new URL("../../backend/graphene/orchestration/static/mission_control.html", import.meta.url), "utf8");
  const css = readFileSync(new URL("../../backend/graphene/orchestration/static/mission_control.css", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\binnerHTML\b|insertAdjacentHTML|\.html\s*\(/);
  assert.doesNotMatch(html, /https?:\/\//);
  assert.ok(html.indexOf('id="tasks-heading"') < html.indexOf('id="graph-heading"'), "accessible task table is primary");
  assert.match(html, /<table>/); assert.match(html, /aria-label="Accessible relationship list"/); assert.match(html, /role="application"/);
  assert.match(html, /id="stale-banner"[^>]*role="alert"/); assert.match(source, /markStale\(/); assert.match(source, /await freshSnapshot\(\)/);
  assert.match(source, /event\.key === "Escape"/); assert.match(source, /"ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"/);
  assert.match(source, /sessionStorage/); assert.match(source, /location\.hash/); assert.match(source, /history\.replaceState/);
  assert.doesNotMatch(source, /localStorage|document\.cookie/);
  assert.match(source, /missionPath\("\/replay"\)/); assert.match(source, /Load generic attempt evidence/);
  assert.match(source, /Mission state advanced\. This drawer remains at an earlier committed head/);
  assert.match(source, /const openingState = state; const openingCursor = openingState\.cursor/);
  assert.match(source, /evidence\?cursor=\$\{encodeURIComponent\(openingCursor\)\}/);
  assert.match(source, /value\.head\.seq !== detail\.head\.seq/);
  assert.match(source, /const generation = \+\+drawerGeneration/);
  assert.ok((source.match(/generation !== drawerGeneration \|\| drawerTaskId !== taskId/g) ?? []).length >= 5);
  assert.match(source, /function closeDrawer\(\) \{\s*drawerGeneration \+= 1;/);
  assert.match(source, /generation === drawerGeneration && drawerTaskId === taskId/);
  assert.match(source, /querySelectorAll\("\[data-task-id\]"\)/);
  assert.match(source, /button\.dataset\.taskId === drawerTaskId/);
  assert.match(source, /if \(drawerWasOpen && previousCursor !== state\.cursor\) closeDrawer\(\)/);
  assert.doesNotMatch(source, /applyDelta\(state, envelope\).*closeDrawer\(\).*render\(\)/s);
  assert.match(html, /id="result-evidence"/);
  assert.match(css, /@media \(max-width: 620px\)/); assert.match(css, /prefers-reduced-motion/); assert.match(css, /forced-colors/); assert.match(css, /focus-visible/);
  assert.doesNotMatch(html, /aria-modal="true"/);
});
