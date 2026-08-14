import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { activityRadius, applyDelta, applyThrough, createState, deltaSubjectId, deterministicPositions, directedEvidenceIds, evidenceInvalidResponse, headSummary, statePositions, statusBadgeData, visibleGraph } from "../../backend/graphene/viewer/static/reducer.mjs";

const snapshot = {
  view_version: 1,
  root_run_id: "run-a",
  cursor: 2,
  nodes: [
    { id: "agent-a", kind: "agent_run", public_label: "Agent A", run_id: "run-a", activity_count: 1 },
    { id: "file-a", kind: "file", public_label: "auth.py", run_id: "run-a", activity_count: 4 },
  ],
  edges: [{ id: "read-a", source: "agent-a", target: "file-a", kind: "READ", interaction_count: 2 }],
};

test("deltas are idempotent and status updates are stable", () => {
  const state = createState(snapshot);
  const delta = { op: "upsert_node", identity: "run-a:3:event-a", cursor: 3, payload: { id: "test-a", kind: "test_receipt", label: "Tests pass", status: "verified" } };
  applyDelta(state, delta);
  applyDelta(state, delta);
  assert.equal(state.nodes.size, 3);
  assert.equal(state.cursor, 3);
  applyDelta(state, { op: "set_status", identity: "run-a:4:event-b", payload: { id: "test-a", status: "completed" } });
  assert.equal(state.nodes.get("test-a").status, "completed");
});

test("the live NDJSON envelope and structured references are accepted", () => {
  const state = createState(snapshot);
  applyDelta(state, {
    type: "delta", cursor: "opaque-3", delta: {
      op: "upsert_node", id: "human-a", run_id: "run-a", seq: 3, event_id: "event-3",
      node: { id: "human-a", kind: "human", label: "Approval", status: "approved", truth_kind: "human_attested", activity_count: 1, source_ref: { kind: "event", id: "event-3", sha256: "a".repeat(64) } },
    },
  });
  assert.equal(state.cursor, "opaque-3");
  assert.equal(state.nodes.get("human-a").sequence, 3);
  assert.match(state.nodes.get("human-a").sourceRef, /event:event-3/);
  const reset = applyDelta(state, { type: "reset", cursor: "opaque-1", snapshot });
  assert.equal(reset.nodes.has("human-a"), false);
});

test("atomic reset envelopes replace the complete graph", () => {
  const state = createState(snapshot);
  const replacement = { ...snapshot, cursor: "reset-2", nodes: [snapshot.nodes[0]], edges: [] };
  const reset = applyDelta(state, { type: "reset", cursor: "reset-2", snapshot: replacement });
  assert.deepEqual([...reset.nodes], [["agent-a", reset.nodes.get("agent-a")]]);
  assert.equal(reset.cursor, "reset-2");
  assert.equal(deltaSubjectId({ type: "reset", current_id: "agent-a", snapshot: replacement }), "agent-a");
});

test("HTTP invalid-evidence responses are parsed as terminal reasons", async () => {
  assert.equal(await evidenceInvalidResponse(new Response(JSON.stringify({ code: "EVIDENCE_INVALID", detail: "hash mismatch" }), { status: 409 })), "hash mismatch");
  assert.match(await evidenceInvalidResponse(new Response("not json", { status: 409 })), /malformed invalid-evidence JSON/);
  assert.equal(await evidenceInvalidResponse(new Response("ok", { status: 200 })), null);
});

test("positions are deterministic and preserved incrementally", () => {
  const state = createState(snapshot);
  const first = deterministicPositions([...state.nodes.values()], [...state.edges.values()]);
  const second = deterministicPositions([...state.nodes.values()].reverse(), [...state.edges.values()].reverse());
  assert.deepEqual(first, second);
  const before = first.get("agent-a");
  applyDelta(state, { op: "upsert_node", payload: { id: "human-a", kind: "feedback", label: "Correction" } });
  const next = deterministicPositions([...state.nodes.values()], [...state.edges.values()], first);
  assert.deepEqual(next.get("agent-a"), before);
  assert.ok(next.has("human-a"));
});

test("organized story positions fill a landscape canvas by run and semantic order", () => {
  const storyNodes = Array.from({ length: 53 }, (_, index) => ({
    id: `node-${String(index).padStart(2, "0")}`,
    group: ["agent", "tool", "evidence", "human", "policy", "test", "handoff"][index % 7],
    runId: `run-${Math.floor(index / 18)}`,
  }));
  const positions = deterministicPositions(storyNodes, [], new Map(), true);
  const points = [...positions.values()];
  const width = Math.max(...points.map(({ x }) => x)) - Math.min(...points.map(({ x }) => x));
  const height = Math.max(...points.map(({ y }) => y)) - Math.min(...points.map(({ y }) => y));
  assert.ok(width / height > 1.35 && width / height < 2.8, `expected landscape bounds, got ${width}×${height}`);
  const shuffled = deterministicPositions([...storyNodes].reverse(), [], new Map(), true);
  assert.deepEqual(positions, shuffled);
  assert.ok(positions.get("node-00").x < positions.get("node-18").x, "runs occupy distinct grid cells");
});

test("filtering keeps only resolvable explicit relationships", () => {
  const state = createState(snapshot);
  const before = statePositions(state, new Map(), true);
  const view = visibleGraph(state, new Set(["agent"]));
  assert.deepEqual(view.nodes.map(({ id }) => id), ["agent-a"]);
  assert.deepEqual(view.edges, []);
  const after = statePositions(state, before);
  assert.deepEqual(after.get("file-a"), before.get("file-a"), "hide/show does not discard hidden positions");
  assert.ok(activityRadius(1000) <= 72);
  assert.ok(activityRadius(8) > activityRadius(1));
});

test("directed evidence paths exclude unrelated undirected branches", () => {
  const nodes = ["a", "b", "c", "d", "x"].map((id) => ({ id }));
  const edges = [
    { source: "a", target: "b" }, { source: "b", target: "c" }, { source: "b", target: "d" }, { source: "x", target: "a" },
  ];
  assert.deepEqual([...directedEvidenceIds(nodes, edges, "c")].sort(), ["a", "b", "c", "x"]);
  assert.deepEqual([...directedEvidenceIds(nodes, edges, "b")].sort(), ["a", "b", "c", "d", "x"]);
});

test("head summary names the root and whole family", () => {
  const heads = [{ run_id: "z-consumer", seq: 9 }, { run_id: "a-root", seq: 4 }];
  assert.equal(headSummary(heads, "a-root"), "Root a-root · seq 4 · 2 family heads");
});

test("scrub and resume rebuild through every received delta", () => {
  const deltas = [
    { op: "set_status", identity: "1", payload: { id: "agent-a", status: "paused" } },
    { op: "set_status", identity: "2", payload: { id: "agent-a", status: "completed" } },
  ];
  assert.equal(applyThrough(snapshot, deltas, 1).nodes.get("agent-a").status, "paused");
  assert.equal(applyThrough(snapshot, deltas, deltas.length).nodes.get("agent-a").status, "completed");
});

test("status badges are fully encoded data URLs", () => {
  const badge = statusBadgeData("#ef746f");
  assert.match(badge, /^data:image\/svg\+xml,%3Csvg/);
  assert.doesNotMatch(badge, /[\s"']/);
  assert.match(decodeURIComponent(badge), /fill="#ef746f"/);
});

test("invalid evidence freezes the reducer", () => {
  const state = createState(snapshot);
  applyDelta(state, { op: "evidence_invalid", identity: "invalid:1", reason: "hash mismatch" });
  applyDelta(state, { op: "upsert_node", identity: "later", payload: { id: "fabricated", kind: "file", label: "No" } });
  assert.equal(state.invalidReason, "hash mismatch");
  assert.equal(state.nodes.has("fabricated"), false);
});

test("malformed deltas throw instead of fabricating or skipping graph truth", () => {
  const state = createState(snapshot);
  assert.throws(() => applyDelta(state, {
    type: "delta",
    delta: { op: "upsert_edge", edge: { id: "bad-edge", source: "agent-a", target: "missing", kind: "INVOKED" } },
  }), /unknown node/);
  assert.throws(() => applyDelta(state, { type: "delta", delta: { op: "surprise" } }), /unknown delta operation/);
  assert.equal(state.edges.has("bad-edge"), false);
});

test("viewer rendering is DOM-safe and offline", () => {
  const source = readFileSync(new URL("../../backend/graphene/viewer/static/viewer.mjs", import.meta.url), "utf8");
  const html = readFileSync(new URL("../../backend/graphene/viewer/static/index.html", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\binnerHTML\b|insertAdjacentHTML|\.html\s*\(/);
  assert.doesNotMatch(source, /\.style\./);
  assert.doesNotMatch(html, /https?:\/\//);
  assert.match(source, /vendor\/cytoscape\.esm\.min\.mjs/);
  assert.match(source, /showInvalid\(`Malformed viewer payload:/);
  assert.match(source, /evidenceInvalidResponse\(response\)/);
  assert.match(html, /EVIDENCE_INVALID/);
  assert.match(html, /Google ADK Runner: not used/);
  assert.match(html, /Gemini calls: 0/);
});

test("the checked-in sanitized replay traverses the live reducer", () => {
  const replay = JSON.parse(readFileSync(new URL("../../backend/graphene/viewer/static/replay.json", import.meta.url), "utf8"));
  let state = createState(replay.snapshot);
  for (const delta of replay.deltas) state = applyDelta(state, delta);
  assert.equal(replay.meta.mode, "VERIFIED REPLAY — NO LIVE AGENT");
  assert.equal(replay.meta.decision_proof, "SIMULATED OPERATOR — NOT HUMAN ATTESTATION");
  assert.equal(state.graphSha256, replay.meta.final_graph_sha256);
  assert.ok([...state.nodes.values()].some((node) => node.id.startsWith("run:") && node.status === "PROMOTED"));
  assert.ok([...state.nodes.values()].some((node) => node.kind === "promotion" && node.status === "PROMOTED"));
  assert.ok([...state.edges.values()].some((edge) => edge.kind === "continued_as"));
});
