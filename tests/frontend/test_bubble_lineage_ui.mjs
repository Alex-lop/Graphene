import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  applyDelta, applyThrough, attentionFact, createState, decisionReceipt, deltaSubjectId,
  deterministicPositions, evidenceInvalidResponse, headSummary, projectionCounts,
  latestNodeId, outcomeLabel, relationshipReceipt, reviewBriefFacts, stageGroups, statePositions, storyNodeIds,
  searchProvenance, truthLabel, verifiedSupportPath, visibleGraph,
} from "../../backend/graphene/viewer/static/reducer.mjs";

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

const proofSnapshot = {
  ...snapshot,
  current_id: "result-a",
  nodes: [
    { id: "result-a", kind: "result", label: "Isolated local result", status: "committed", truth_kind: "runtime_observed", stage: "local_result", activity_count: 1 },
    { id: "approval-a", kind: "promotion", label: "Candidate approval", status: "approved", truth_kind: "simulated_fixture", stage: "candidate_decision", activity_count: 1 },
    { id: "candidate-a", kind: "changeset", label: "Candidate", status: "verified", truth_kind: "runtime_observed", stage: "candidate_decision", activity_count: 2 },
    { id: "test-a", kind: "test", label: "Bound test", status: "passed", truth_kind: "runtime_observed", stage: "consumer_work", activity_count: 1 },
    { id: "file-a", kind: "file", label: "app/example.py", status: "changed", truth_kind: "runtime_observed", stage: "consumer_work", activity_count: 3, metadata: { path: "app/example.py", added_lines: 2, bound_test_pass: true } },
    { id: "billing-a", kind: "policy", label: "Excluded handoff", status: "denied", truth_kind: "policy_authoritative", stage: "approved_handoff", activity_count: 1 },
  ],
  edges: [
    { id: "support-1", source: "result-a", target: "approval-a", kind: "supported_by", relationship_class: "verified_support", support_path: true, activity_count: 1 },
    { id: "support-2", source: "approval-a", target: "candidate-a", kind: "authorized_by", relationship_class: "authorization", support_path: true, activity_count: 1 },
    { id: "support-3", source: "candidate-a", target: "test-a", kind: "supported_by", relationship_class: "verified_support", support_path: true, activity_count: 1 },
    { id: "support-4", source: "test-a", target: "file-a", kind: "binds_path", relationship_class: "verified_support", support_path: true, activity_count: 1 },
    { id: "membership-billing", source: "billing-a", target: "candidate-a", kind: "recorded", relationship_class: "membership", support_path: false, activity_count: 1 },
  ],
  unknowns: ["No PR, push, deployment, or activity outside captured operations was observed."],
  review_brief: {
    attention: { id: "attention:clear", section: "attention", status: "established", text: "No unresolved Graphene decision.", truth_kind: "server_derived", node_ids: [], edge_ids: [], metadata: {} },
    sections: [
      { key: "attention", title: "Needs attention now", facts: [] },
      { key: "candidate", title: "Candidate / changed paths", facts: [{ id: "candidate:path", section: "candidate", status: "established", text: "Captured changed path: app/example.py.", truth_kind: "runtime_observed", node_ids: ["file-a"], edge_ids: ["support-4"], metadata: {} }] },
      { key: "verified_evidence", title: "Verified evidence", facts: [{ id: "evidence:test", section: "verified_evidence", status: "established", text: "Bound test passed.", truth_kind: "runtime_observed", node_ids: ["test-a"], edge_ids: ["support-3"], metadata: {} }] },
      { key: "human_intervention", title: "Human intervention", facts: [{ id: "human:approval", section: "human_intervention", status: "historical", text: "Fixture approval recorded.", truth_kind: "simulated_fixture", node_ids: ["approval-a"], edge_ids: ["support-2"], metadata: {} }] },
      { key: "inherited_context", title: "Inherited context", facts: [{ id: "context:excluded", section: "inherited_context", status: "historical", text: "One handoff excluded with zero dispatch.", truth_kind: "policy_authoritative", node_ids: ["billing-a"], edge_ids: [], metadata: { model_dispatch_count: 0 } }] },
      { key: "outcome", title: "Outcome", facts: [{ id: "outcome:local", section: "outcome", status: "established", text: "An isolated local commit was recorded.", truth_kind: "runtime_observed", node_ids: ["result-a"], edge_ids: ["support-1"], metadata: { outcome_kind: "isolated_local_commit" } }] },
      { key: "unknown", title: "Unknown", facts: [{ id: "unknown:1", section: "unknown", status: "not_established", text: "No PR, push, or deployment was observed.", truth_kind: "server_derived", node_ids: [], edge_ids: [], metadata: {} }] },
    ],
    changed_paths: ["app/example.py"], bound_paths: ["app/example.py"], stage: "local_result", outcome_kind: "isolated_local_commit",
    counts: { total_nodes: 8, visible_nodes: 6, filtered_nodes: 0, collapsed_nodes: 1, omitted_nodes: 1, total_edges: 7, visible_edges: 5 },
  },
  support_paths: [{ root_node_id: "result-a", label: "Verified support relationships", node_ids: ["result-a", "approval-a", "candidate-a", "test-a", "file-a"], edge_ids: ["support-1", "support-2", "support-3", "support-4"] }],
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

test("batched live deltas reconcile atomically with summary fields and deduplication", () => {
  const state = createState(snapshot);
  const envelope = {
    type: "delta", cursor: "batch-3", current_id: "test-a",
    deltas: [
      { op: "upsert_node", id: "test-a", run_id: "run-a", seq: 3, event_id: "event-3", node: { id: "test-a", kind: "test", label: "Bound test", status: "passed", truth_kind: "runtime_observed", activity_count: 1 } },
      { op: "upsert_edge", id: "edge-test", run_id: "run-a", seq: 3, event_id: "event-3", edge: { id: "edge-test", source: "agent-a", target: "test-a", kind: "supported_by", relationship_class: "verified_support", support_path: true, activity_count: 1 } },
    ],
    heads: [{ run_id: "run-a", seq: 3 }], graph_sha256: "b".repeat(64), omitted_counts: {}, unknowns: ["Exact unknown"],
    review_brief: proofSnapshot.review_brief, support_paths: proofSnapshot.support_paths,
  };
  const next = applyDelta(state, envelope);
  const duplicate = applyDelta(next, envelope);
  assert.equal(next.nodes.get("test-a").status, "passed");
  assert.equal(next.edges.get("edge-test").supportPath, true);
  assert.equal(next.currentId, "test-a");
  assert.equal(next.reviewBrief.outcome_kind, "isolated_local_commit");
  assert.deepEqual(duplicate.nodes, next.nodes);

  const malformed = { ...envelope, cursor: "bad", deltas: [envelope.deltas[0], { op: "upsert_edge", id: "bad", edge: { id: "bad", source: "test-a", target: "missing", kind: "bad", relationship_class: "verified_support", support_path: true } }] };
  assert.throws(() => applyDelta(state, malformed), /unknown node/);
  assert.equal(state.nodes.has("test-a"), false, "failed batch leaves prior state untouched");
});

test("stale and conflicting batched delta heads fail before mutation", () => {
  const prior = {
    ...snapshot,
    heads: [{ run_id: "run-a", seq: 3, event_sha256: "a".repeat(64) }],
    graph_sha256: "b".repeat(64),
  };
  const stale = {
    type: "delta", cursor: "stale", heads: [{ run_id: "run-a", seq: 2, event_sha256: "c".repeat(64) }],
    deltas: [{ op: "upsert_node", id: "stale-a", node: { id: "stale-a", kind: "test", label: "Stale" } }],
  };
  const state = createState(prior);
  assert.throws(() => applyDelta(state, stale), /stale or out-of-order/);
  assert.equal(state.nodes.has("stale-a"), false);
  assert.equal(state.heads[0].seq, 3);

  const conflicting = {
    ...stale,
    cursor: "conflict",
    heads: [{ run_id: "run-a", seq: 3, event_sha256: "c".repeat(64) }],
  };
  assert.throws(() => applyDelta(state, conflicting), /conflicting delta head/);
  assert.equal(state.nodes.has("stale-a"), false);
});

test("remove deltas delete only their typed target and dangling node relationships", () => {
  const collision = {
    ...proofSnapshot,
    nodes: [...proofSnapshot.nodes, { id: "membership-billing", kind: "evidence", label: "Same ID as edge" }],
  };
  let state = createState(collision);
  state = applyDelta(state, { op: "remove", id: "membership-billing", remove_kind: "edge", run_id: "run", seq: 8, event_id: "remove-edge" });
  assert.equal(state.edges.has("membership-billing"), false);
  assert.equal(state.nodes.has("membership-billing"), true, "edge removal preserves a same-ID node");
  state = applyDelta(state, { op: "remove", id: "billing-a", remove_kind: "node", run_id: "run", seq: 9, event_id: "remove-node" });
  assert.equal(state.nodes.has("billing-a"), false);
  assert.ok([...state.edges.values()].every((edge) => edge.source !== "billing-a" && edge.target !== "billing-a"));
  assert.throws(() => applyDelta(state, { op: "remove", id: "candidate-a" }), /typed target/);
});

test("atomic reset envelopes replace the complete graph", () => {
  const state = createState(snapshot);
  const replacement = { ...snapshot, cursor: "reset-2", nodes: [snapshot.nodes[0]], edges: [] };
  const reset = applyDelta(state, { type: "reset", cursor: "reset-2", snapshot: replacement });
  assert.deepEqual([...reset.nodes], [["agent-a", reset.nodes.get("agent-a")]]);
  assert.equal(reset.cursor, "reset-2");
  assert.equal(deltaSubjectId({ type: "reset", current_id: "agent-a", snapshot: replacement }), "agent-a");
});

test("settled snapshots derive the same latest visible decision anchor", () => {
  const state = createState({
    nodes: [
      { id: "run:z", kind: "agent", label: "Run", recorded_at: "2026-08-15T12:00:02Z" },
      { id: "event:a", kind: "promotion", label: "Decision A", recorded_at: "2026-08-15T12:00:02Z" },
      { id: "event:z", kind: "promotion", label: "Decision Z", recorded_at: "2026-08-15T12:00:02Z" },
      { id: "event:old", kind: "test", label: "Older", recorded_at: "2026-08-15T12:00:01Z" },
    ],
    edges: [],
  });
  assert.equal(state.currentId, "event:z", "ties prefer a non-run node and then stable ID");
  assert.equal(latestNodeId(state.nodes.values()), "event:z");
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
});

test("verified support paths use only projected directed allowlisted relationships", () => {
  const state = createState(proofSnapshot);
  const path = verifiedSupportPath(state, "result-a");
  assert.deepEqual([...path.nodeIds].sort(), ["approval-a", "candidate-a", "file-a", "result-a", "test-a"]);
  assert.deepEqual([...path.edgeIds].sort(), ["support-1", "support-2", "support-3", "support-4"]);
  assert.equal(path.nodeIds.has("billing-a"), false, "membership-only Billing branch is not support");
  assert.deepEqual([...verifiedSupportPath(state, "file-a").edgeIds].sort(), ["support-1", "support-2", "support-3", "support-4"], "selecting a leaf keeps its projected decision chain");
  const fallback = createState({
    ...proofSnapshot,
    support_paths: [],
    edges: [...proofSnapshot.edges, { id: "invented", source: "result-a", target: "billing-a", kind: "invented_relation", relationship_class: "verified_support", support_path: true }],
  });
  assert.deepEqual([...verifiedSupportPath(fallback, "result-a").edgeIds].sort(), ["support-1", "support-2", "support-3", "support-4"]);
  assert.equal(verifiedSupportPath(fallback, "result-a").edgeIds.has("invented"), false);
});

test("relationship receipts expose only committed public provenance", () => {
  const receipt = relationshipReceipt(createState(proofSnapshot), "support-4");
  assert.deepEqual(receipt, {
    source: "Bound test", target: "app/example.py", kind: "binds_path", relationshipClass: "verified_support", supportPath: true,
    runId: null, sequence: null, eventId: null, sourceRef: null, digest: null,
  });
  assert.equal(relationshipReceipt(createState(proofSnapshot), "missing"), null);
});

test("search is stable, bounded, and limited to projected public evidence", () => {
  const state = createState(proofSnapshot);
  const paths = searchProvenance(state, "app example").results;
  assert.ok(paths.some((result) => result.type === "node" && result.id === "file-a"));
  assert.ok(paths.some((result) => result.type === "fact" && result.id === "candidate:path"));

  const relationships = searchProvenance(state, "binds path").results;
  assert.ok(relationships.some((result) => result.type === "relationship" && result.id === "support-4"));
  assert.ok(searchProvenance(state, "model_dispatch_count").results.some((result) => result.id === "context:excluded"));
  assert.deepEqual(searchProvenance(state, ""), { query: "", total: 0, truncated: false, results: [] });
  const bounded = searchProvenance(state, "a", 2);
  assert.equal(bounded.results.length, 2);
  assert.equal(bounded.truncated, bounded.total > 2);
  assert.deepEqual(searchProvenance(state, "app example").results, paths, "repeat searches preserve order");
});

test("Review Brief renders contract facts, exact unknowns, attention, stages, and truth labels", () => {
  const state = createState(proofSnapshot);
  const brief = reviewBriefFacts(state);
  assert.equal(brief.candidate[0].value, "Captured changed path: app/example.py.");
  assert.equal(brief.evidence[0].value, "Bound test passed.");
  assert.equal(brief.context[0].metadata.model_dispatch_count, 0);
  assert.equal(brief.unknown[0].value, "No PR, push, or deployment was observed.");
  assert.equal(attentionFact(state).value, "No unresolved Graphene decision.");
  assert.deepEqual(stageGroups(state).map(({ id }) => id), ["source_work", "human_correction_scope", "approved_handoff", "consumer_work", "candidate_decision", "local_result"]);
  assert.equal(stageGroups(state)[0].status, "not established");
  assert.equal(truthLabel("simulated_fixture"), "SIMULATED FIXTURE — NOT HUMAN ATTESTATION");
  assert.equal(truthLabel("model_proposed"), "MODEL PROPOSED");
  assert.equal(truthLabel("evidence_bound"), "EVIDENCE BOUND");
  assert.notEqual(truthLabel("simulated_fixture"), truthLabel("human_attested"));
  assert.equal(stageGroups(state)[2].label, "Handoff boundary");
  assert.equal(outcomeLabel("graphene_receipt_only"), "Graphene receipt recorded · no commit established");
});

test("decision receipt distinguishes gates, terminal outcomes, and exact test bindings", () => {
  const recorded = decisionReceipt(createState(proofSnapshot));
  assert.equal(recorded.state, "recorded");
  assert.equal(recorded.outcomeKind, "isolated_local_commit");
  assert.deepEqual(recorded.paths, [{ path: "app/example.py", boundToPassingReceipt: false }]);
  assert.equal(recorded.explicitLimitCount, 1);

  const bound = structuredClone(proofSnapshot);
  bound.review_brief.sections.find(({ key }) => key === "candidate").facts.push({ id: "candidate:bound_test", section: "candidate", status: "established", text: "Passing receipt is bound.", truth_kind: "runtime_observed", node_ids: ["test-a", "file-a"], edge_ids: ["support-4"], metadata: { passed: true } });
  assert.equal(decisionReceipt(createState(bound)).paths[0].boundToPassingReceipt, true);
});

test("decision neighborhood and counts distinguish visible, filtered, collapsed, and omitted", () => {
  const state = createState(proofSnapshot);
  const story = storyNodeIds(state, "result-a");
  assert.deepEqual([...story].sort(), ["approval-a", "candidate-a", "file-a", "result-a", "test-a"], "default view is the exact projected decision spine");
  assert.equal(story.has("billing-a"), false, "historical denial stays out of the current outcome spine");
  const enabled = new Set(["handoff", "tool", "test", "evidence"]);
  const view = visibleGraph(state, enabled, story);
  const counts = projectionCounts(state, view, enabled, story);
  assert.equal(counts.total, 8);
  assert.equal(counts.visible, view.nodes.length);
  assert.ok(counts.filtered > 0);
  assert.ok(counts.collapsed >= 1);
  assert.equal(counts.omitted, 1);

  const billingFact = reviewBriefFacts(state).context[0];
  assert.deepEqual([...storyNodeIds(state, "result-a", null, billingFact)], ["billing-a"], "fact focus reveals exactly its committed support");
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
  const css = readFileSync(new URL("../../backend/graphene/viewer/static/viewer.css", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\binnerHTML\b|insertAdjacentHTML|\.html\s*\(/);
  assert.doesNotMatch(source, /\.style\./);
  assert.doesNotMatch(html, /https?:\/\//);
  assert.match(source, /vendor\/cytoscape\.esm\.min\.mjs/);
  assert.match(source, /showInvalid\(`Malformed viewer payload:/);
  assert.match(source, /evidenceInvalidResponse\(response\)/);
  assert.match(html, /EVIDENCE_INVALID/);
  assert.match(html, /Google ADK Runner: not used/);
  assert.match(html, /Gemini calls: 0/);
  assert.match(html, /Review Brief/);
  assert.match(html, /Needs attention now/);
  assert.match(html, /Candidate \/ changed paths/);
  assert.match(html, /Inherited context: included and excluded/);
  assert.match(html, /Decision Provenance/);
  assert.match(html, /Decision support bindings/);
  assert.match(html, /Recorded decisions and corrections/);
  assert.match(html, /aria-describedby="bounds selection-status"/);
  assert.match(html, /id="selection-status"[^>]*aria-live="polite"/);
  assert.doesNotMatch(html, /aria-modal="true"/);
  assert.match(html, /Focused review fact/);
  assert.doesNotMatch(html, />Evidence path</);
  assert.match(source, /existing\.data\(element\.data\)/, "normal updates reconcile existing Cytoscape elements");
  assert.doesNotMatch(source, /cy\.elements\(\)\.remove\(\)/, "normal updates do not rebuild the graph");
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(source, /config\.replay === true \? VERIFIED_REPLAY_LABEL/);
  assert.match(source, /VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION/);
  assert.match(source, /config\.replay === true \? "VERIFIED REPLAY" : live \? "EVENT FEED"/);
  assert.doesNotMatch(source, /pulseCurrent|setInterval/);
  assert.doesNotMatch(source, /activityRadius\(node\.activity\)/);
  assert.match(source, /setAttribute\("aria-current", "step"\)/);
  assert.match(source, /evidence class \$\{truthLabel\(node\.truthKind\)\}/);
  assert.match(css, /\[tabindex\]:focus-visible/);
  assert.match(source, /event\.target !== \$\("canvas"\)/, "graph keys are intercepted only while the canvas is focused");
  assert.match(source, /selectEdge\(edge\.id\)/, "relationship rows open their own provenance receipt");
  assert.match(source, /detail\.source_ref\?\.sha256/, "node detail compares the structured public reference digest");
  assert.match(source, /replayIndex = deltaLog\.length;\s*state = applyThrough\(initialSnapshot, deltaLog, replayIndex\)/, "verified replay opens on the final decision checkpoint");
});

test("the checked-in sanitized replay traverses the live reducer", () => {
  const replay = JSON.parse(readFileSync(new URL("../../backend/graphene/viewer/static/replay.json", import.meta.url), "utf8"));
  let state = createState(replay.snapshot);
  const attention = [state.attention];
  const receipts = [decisionReceipt(state)];
  for (const envelope of replay.deltas) {
    assert.equal(envelope.type, "delta");
    assert.ok(Array.isArray(envelope.deltas));
    state = applyDelta(state, envelope);
    attention.push(state.attention);
    receipts.push(decisionReceipt(state));
  }
  const replayTruth = "VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION";
  assert.equal(replay.meta.mode, replayTruth);
  assert.equal(replay.meta.truth_label, replayTruth);
  assert.equal(replay.meta.decision_proof, "SIMULATED FIXTURE — NOT HUMAN ATTESTATION");
  assert.equal(state.graphSha256, replay.meta.final_graph_sha256);
  assert.ok([...state.nodes.values()].some((node) => node.id.startsWith("run:") && node.status === "PROMOTED" && node.displayStatus === "GRAPHENE RECEIPT RECORDED"));
  assert.ok([...state.nodes.values()].some((node) => node.kind === "promotion" && node.label === "Graphene Receipt Recorded"));
  assert.ok([...state.edges.values()].some((edge) => edge.kind === "continued_as"));
  assert.ok([...state.nodes.values()].some((node) => node.metadata.operation === "open_evidence"));
  assert.ok([...state.edges.values()].some((edge) => edge.kind === "opens_reference" && edge.relationshipClass === "context_transfer"));
  assert.ok(attention.some((fact) => fact.status === "pending" && fact.metadata.pending_count === 1));
  assert.ok(receipts.some((receipt) => receipt.state === "required"));
  assert.equal(receipts.at(-1).state, "recorded");
  assert.ok(receipts.at(-1).paths.every(({ boundToPassingReceipt }) => boundToPassingReceipt));
  assert.deepEqual(state.reviewBrief.changed_paths, ["app/auth/limiter.py", "tests/test_security_policy.py"]);
  assert.match(reviewBriefFacts(state).context.find((fact) => fact.id === "context:included").value, /all_auth applies to app\/auth\/\*\*/);
  assert.match(attentionFact(state).value, /No unresolved Graphene decision/);
  assert.equal(storyNodeIds(state, state.currentId).size, 13, "final replay defaults to its bounded decision-support spine");
});
