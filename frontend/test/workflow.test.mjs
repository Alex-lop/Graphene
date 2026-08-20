import assert from "node:assert/strict";
import test from "node:test";

import {
  EXACT_CORRECTION,
  GoldenDemo,
  TASKS,
  deriveControls,
  promotionPayload,
} from "../src/workflow.mjs";

const SHA = "b".repeat(64);
const BASE = "a".repeat(40);

function baselineRun(state = "waiting_for_promotion") {
  return {
    run_id: "run.baseline",
    task_id: TASKS.baseline,
    state,
    revision: state === "queued" ? 0 : 2,
    proof: state === "queued" ? [] : [
      {
        event_id: "event.write",
        type: "tool.file_written",
        payload: { path: "app/auth/limiter.py" },
      },
    ],
    injected_memories: [],
  };
}

function adaptedRun(state = "waiting_for_promotion") {
  return {
    run_id: "run.adapted",
    task_id: TASKS.adapted,
    state,
    revision: state === "queued" ? 0 : 2,
    context_packet_id: "ctx.adapted",
    context_packet_sha256: SHA,
    source_graph_revision: 1,
    source_graph_hash: SHA,
    selected_node_ids: ["node.memory"],
    injected_memories: [{ memory_id: "mem_auth_review", revision: 1 }],
    candidate: {
      base_commit_sha: BASE,
      candidate_patch_sha256: SHA,
      candidate_tree_sha256: SHA,
      candidate_tree_hash_version: "graphene.tree.v2",
      changed_paths: ["app/auth/limiter.py", "tests/test_security_policy.py"],
      test_receipt: { receipt_sha256: SHA, candidate_exit_code: 0 },
    },
    proof: [],
  };
}

const proposedMemory = {
  memory_id: "mem_auth_review",
  revision: 1,
  state: "proposed",
  path_globs: ["app/auth/**"],
};

const approvedMemory = { ...proposedMemory, state: "approved" };

test("golden workflow sends the frozen requests in order using server-returned bindings", async () => {
  const calls = [];
  let key = 0;
  const mutate = async (path, payload, token) => {
    calls.push({ path, payload, token });
    if (path === "/api/demo/reset") return { status: "reset" };
    if (path === "/api/runs" && payload.task_id === TASKS.baseline) return baselineRun("queued");
    if (path === "/api/runs/run.baseline/execute") return baselineRun();
    if (path === "/api/runs/run.baseline/feedback") return proposedMemory;
    if (path === "/api/memories/mem_auth_review/decision") return approvedMemory;
    if (path === "/api/runs" && payload.task_id === TASKS.adapted) return adaptedRun("queued");
    if (path === "/api/runs/run.adapted/execute") return adaptedRun();
    if (path === "/api/runs/run.adapted/promote") return adaptedRun("completed");
    throw new Error(`unexpected request: ${path}`);
  };
  const demo = new GoldenDemo({
    mutate,
    keyFactory: () => `abcdefghijklmnop${++key}`,
  });

  demo.setToken("runtime-secret");
  await demo.reset();
  await demo.runBaseline();
  await demo.submitFeedback("hunk.exact", "all_auth");
  await demo.approveMemory();
  await demo.runAdapted();
  await demo.promote();

  assert.deepEqual(calls.map((call) => call.path), [
    "/api/demo/reset",
    "/api/runs",
    "/api/runs/run.baseline/execute",
    "/api/runs/run.baseline/feedback",
    "/api/memories/mem_auth_review/decision",
    "/api/runs",
    "/api/runs/run.adapted/execute",
    "/api/runs/run.adapted/promote",
  ]);
  assert.ok(calls.every((call) => call.token === "runtime-secret"));
  assert.equal("token" in demo.snapshot, false, "the public state never exposes the token");

  assert.equal(calls[1].payload.task_id, TASKS.baseline);
  assert.equal(calls[2].payload.expected_run_revision, 0);
  assert.deepEqual(
    {
      correction: calls[3].payload.correction,
      evidence_event_id: calls[3].payload.evidence_event_id,
      selected_hunk_id: calls[3].payload.selected_hunk_id,
      scope_id: calls[3].payload.scope_id,
      expected_run_revision: calls[3].payload.expected_run_revision,
    },
    {
      correction: EXACT_CORRECTION,
      evidence_event_id: "event.write",
      selected_hunk_id: "hunk.exact",
      scope_id: "all_auth",
      expected_run_revision: 2,
    },
  );
  assert.deepEqual(
    { decision: calls[4].payload.decision, expected_revision: calls[4].payload.expected_revision },
    { decision: "approve", expected_revision: 1 },
  );
  assert.deepEqual(
    { ...calls[7].payload, idempotency_key: "ignored" },
    { ...promotionPayload(adaptedRun(), approvedMemory, "ignored") },
  );
});

test("controls stay disabled until their authoritative prerequisites exist", () => {
  const empty = deriveControls({
    hasToken: false,
    busy: null,
    baseline: null,
    memory: null,
    adapted: null,
    selectedHunkId: null,
  });
  assert.ok(Object.values(empty).every((value) => value === false));

  const feedback = deriveControls({
    hasToken: true,
    busy: null,
    baseline: baselineRun(),
    memory: null,
    adapted: null,
    selectedHunkId: "hunk.exact",
  });
  assert.equal(feedback.feedback, true);
  assert.equal(feedback.approveMemory, false);

  const approval = deriveControls({
    hasToken: true,
    busy: null,
    baseline: baselineRun(),
    memory: proposedMemory,
    adapted: null,
    selectedHunkId: "hunk.exact",
  });
  assert.equal(approval.approveMemory, true);

  const handoff = deriveControls({
    hasToken: true,
    busy: null,
    baseline: baselineRun(),
    memory: approvedMemory,
    adapted: null,
    selectedHunkId: "hunk.exact",
  });
  assert.equal(handoff.adapted, true);

  const promotion = deriveControls({
    hasToken: true,
    busy: null,
    baseline: baselineRun(),
    memory: approvedMemory,
    adapted: adaptedRun(),
    selectedHunkId: "hunk.exact",
  });
  assert.equal(promotion.promote, true);

  const busy = deriveControls({
    hasToken: true,
    busy: "adapted",
    baseline: baselineRun(),
    memory: approvedMemory,
    adapted: adaptedRun(),
    selectedHunkId: "hunk.exact",
  });
  assert.equal(busy.reset, false);
  assert.equal(busy.promote, false);
  assert.equal(busy.switchBaseline, false);
});

test("request errors clear busy state, remain visible, and allow a safe retry", async () => {
  const demo = new GoldenDemo({
    mutate: async () => { throw new Error("HTTP 409: stale revision"); },
    keyFactory: () => "abcdefghijklmnop",
  });
  demo.setToken("runtime-secret");
  await assert.rejects(() => demo.runBaseline(), /stale revision/);
  assert.equal(demo.snapshot.busy, null);
  assert.equal(demo.snapshot.error, "HTTP 409: stale revision");
  assert.equal(demo.controls().baseline, true);
});
