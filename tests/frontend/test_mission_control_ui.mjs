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
  finalDecisionOptions,
  finalResultBinding,
  finalReviewModel,
  graphPositions,
  graphView,
  missionBrief,
  renderFinalReview,
  snapshotHashPayload,
  stateBuckets,
  taskEvidenceTarget,
  visibleStateBuckets,
} from "../../backend/graphene/orchestration/static/mission_reducer.mjs";

const replay = JSON.parse(readFileSync(new URL("../../backend/graphene/orchestration/static/mission-replay.json", import.meta.url), "utf8"));

function adkFinalState() {
  const state = applyThrough(replay.snapshot, replay.deltas, replay.deltas.length - 1);
  const candidate = { id: "publication_runtime_patch", kind: "artifact-envelope-v2", sha256: "c".repeat(64) };
  const verification = { id: "publication_runtime_verification", kind: "artifact-envelope-v2", sha256: "d".repeat(64) };
  const bundle = { id: "artifact_bundle_proof", kind: "final-result-bundle", sha256: "e".repeat(64) };
  const snapshot = {
    view_version: 1, mission: state.mission, head: state.head, cursor: state.cursor,
    tasks: [...state.tasks.values()], attempts: [...state.attempts.values()], workers: [...state.workers.values()],
    gates: [...state.gates.values()], publications: [...state.publications.values()], relationships: [...state.relationships.values()],
    integration: state.integration, verification: state.verification, resources: state.resources, needs_you: state.needsYou,
    critical_path_task_ids: state.criticalPathTaskIds,
    result: {
      ...state.result,
      bundle_id: `final_result_${"1".repeat(32)}`,
      bundle_sha256: "2".repeat(64),
      evidence_refs: [candidate, verification, bundle],
    },
    unknowns: ["Windows checkout behavior is not established."], snapshot_sha256: state.snapshotSha256,
  };
  snapshot.publications.push({
    publication_id: candidate.id, task_id: "assemble", attempt_id: "attempt_assemble_1",
    output_name: "assembled_output", kind: "patch", state: "accepted", sha256: "a".repeat(64),
    paths: ["backend/runtime.py", "tests/test_runtime.py"], consumers: ["verify"],
  });
  snapshot.publications.push({
    publication_id: verification.id, task_id: "verify", attempt_id: "attempt_verify_1",
    output_name: "bound_check", kind: "test-receipt", state: "accepted", sha256: "b".repeat(64),
    paths: ["receipts/runtime.json"], consumers: [],
  });
  snapshot.publications.sort((left, right) => left.publication_id.localeCompare(right.publication_id));
  snapshot.snapshot_sha256 = createHash("sha256").update(canonicalJson(snapshotHashPayload(snapshot))).digest("hex");
  return createState(snapshot);
}

class TestElement {
  constructor(tagName) { this.tagName = tagName; this.children = []; this._text = ""; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ""; this.children = [...children]; }
}

const testDocument = { createElement: (tagName) => new TestElement(tagName) };

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
  const awaiting = states.at(-2);
  assert.equal(awaiting.mission.status, "awaiting_result");
  assert.equal(awaiting.result.state, "awaiting_decision");
  assert.equal(awaiting.needsYou.gate_id, "final_result_recorded_fixture");
  assert.equal(awaiting.needsYou.truth_kind, "simulated_fixture");
  assert.equal(replay.meta.human_attestation, false);
  const final = states.at(-1);
  assert.equal(final.integration.state, "done"); assert.equal(final.verification.state, "done"); assert.equal(final.result.state, "commit_created");
});

test("table buckets and graph use exact states and explicit typed relationships", () => {
  const state = createState(replay.snapshot);
  assert.deepEqual(stateBuckets(state).map((item) => item.status), TASK_STATES);
  assert.ok(visibleStateBuckets(state).every((item) => item.count > 0));
  assert.equal(missionBrief(state).progress, "0/6 complete · 0 running · 1 blocked");
  assert.match(missionBrief(state).needs, /redact note text/i);
  const graph = graphView(state); const ids = new Set(graph.nodes.map((item) => item.id));
  assert.ok(graph.edges.some((item) => item.kind === "decomposed_into"));
  assert.ok(graph.edges.every((item) => ids.has(item.source) && ids.has(item.target)));
  assert.deepEqual(taskEvidenceTarget(applyThrough(replay.snapshot, replay.deltas), "render_markdown"), { kind: "generic", attemptId: "attempt_render_markdown_2" });
  const positions = graphPositions(state);
  assert.equal(positions.get("task:redact_notes").x, positions.get("task:render_json").x, "parallel roots share a DAG-depth lane");
  assert.ok(positions.get("task:wire_cli").x > positions.get("task:render_json").x);
  assert.ok(positions.get(`result:${state.missionId}`).x > positions.get(`verification:${state.missionId}`).x);
  assert.deepEqual(graphPositions(state), positions, "layout is deterministic");
});

test("ADK patch publication renders an exact, consequence-complete final review", () => {
  const state = adkFinalState();
  const binding = finalResultBinding(state);
  assert.equal(binding.candidate.publication.kind, "patch", "candidate authority does not depend on a candidate-named kind");
  assert.equal(binding.candidate.reference.kind, "artifact-envelope-v2");
  assert.equal(binding.candidate.publication.task_id, "assemble");
  assert.equal(binding.verification.publication.task_id, "verify");
  assert.equal(binding.bundle.id, `final_result_${"1".repeat(32)}`);
  assert.equal(binding.bundle.digest, "2".repeat(64));
  assert.deepEqual(finalDecisionOptions(state).map(({ label, action }) => ({ label, action })), [
    { label: "Approve exact bundle", action: "approve_final" },
    { label: "Reject exact bundle", action: "reject_final" },
  ]);
  const review = finalReviewModel(state);
  assert.deepEqual(review.changedPaths, ["backend/runtime.py", "tests/test_runtime.py"]);
  const container = new TestElement("section");
  assert.equal(renderFinalReview(testDocument, container, state), true);
  assert.match(container.textContent, new RegExp(`final_result_${"1".repeat(32)}`));
  assert.match(container.textContent, new RegExp(`sha256:${"2".repeat(64)}`));
  assert.match(container.textContent, /final-result-bundle:artifact_bundle_proof/);
  assert.match(container.textContent, new RegExp(`sha256:${"a".repeat(64)}`));
  assert.match(container.textContent, /artifact-envelope-v2:publication_runtime_patch/);
  assert.match(container.textContent, /artifact-envelope-v2:publication_runtime_verification/);
  assert.match(container.textContent, /backend\/runtime\.py, tests\/test_runtime\.py/);
  assert.match(container.textContent, /Windows checkout behavior is not established/);
  assert.match(container.textContent, /Approve: create and record one verified isolated local commit/);
  assert.match(container.textContent, /Reject: record the final rejection and create no local result commit/);
  state.result.state = "approved";
  assert.deepEqual(finalDecisionOptions(state).map(({ label, action }) => ({ label, action })), [
    { label: "Finish approved isolated commit", action: "approve_final" },
  ], "an approved result cannot expose another rejection decision");
});

test("Mission Control is DOM-safe, table-first, keyboard reachable, responsive, and stale-explicit", () => {
  const source = readFileSync(new URL("../../backend/graphene/orchestration/static/mission_control.mjs", import.meta.url), "utf8");
  const html = readFileSync(new URL("../../backend/graphene/orchestration/static/mission_control.html", import.meta.url), "utf8");
  const css = readFileSync(new URL("../../backend/graphene/orchestration/static/mission_control.css", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\binnerHTML\b|insertAdjacentHTML|\.html\s*\(/);
  assert.doesNotMatch(html, /https?:\/\//);
  assert.ok(html.indexOf('id="tasks-heading"') < html.indexOf('id="graph-heading"'), "accessible task table is primary");
  assert.ok(html.indexOf('id="replay-controls"') < html.indexOf('id="status-heading"'), "replay play control is above the work board");
  assert.match(html, /<table>/); assert.match(html, /aria-label="Accessible relationship list"/); assert.match(html, /role="application"/);
  assert.match(html, /id="stale-banner"[^>]*role="alert"/); assert.match(source, /markStale\(/); assert.match(source, /await freshSnapshot\(\)/);
  assert.match(source, /event\.key === "Escape"/); assert.match(source, /"ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"/);
  assert.match(source, /sessionStorage/); assert.match(source, /location\.hash/); assert.match(source, /history\.replaceState/);
  assert.match(source, /config\.cancelEnabled === true/);
  assert.doesNotMatch(source, /localStorage|document\.cookie/);
  assert.match(source, /missionPath\("\/replay"\)/); assert.match(source, /Load generic attempt evidence/);
  assert.match(source, /rebuildReplay\(0\)/);
  assert.match(source, /Continue with recorded simulated approval/);
  assert.match(source, /recordedDecisionCheckpoint\(\)/);
  assert.match(source, /visibleStateBuckets\(state\)/);
  assert.match(source, /node\.critical/);
  assert.doesNotMatch(JSON.stringify(replay), /"label":"Approve"/);
  assert.match(html, /<dialog id="command-dialog"/);
  assert.match(html, /id="command-confirmation"/);
  assert.match(html, /id="command-final-review"/);
  assert.match(source, /graphene-mission-command-token/);
  assert.match(source, /\/commands\/session/);
  assert.match(source, /X-CSRF-Token/);
  assert.match(source, /MISSION_HEAD_STALE/);
  assert.match(source, /finalDecisionOptions\(state\)/);
  assert.doesNotMatch(source, /reference\.kind\.includes\("candidate"\)/);
  assert.match(html, /id="command-input"/);
  assert.match(source, /supply_input/);
  assert.match(source, /private artifact/);
  assert.match(source, /\["Contract", detail\.task\.contract\]/);
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
