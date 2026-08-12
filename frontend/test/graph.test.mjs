import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  filterGraph,
  layoutGraph,
  pathMatches,
  proofRows,
  validateGraphResponse,
} from "../src/graph.mjs";

const SHA = "a".repeat(64);
const NOW = "2026-08-11T12:00:00Z";

function node(id, kind, runId, data = {}) {
  return {
    id,
    kind,
    label: id,
    repo_id: "reviewlatch-demo",
    run_id: runId,
    provenance: "server_observed",
    source_ref: `records/${id}`,
    digest: SHA,
    status: "completed",
    created_at: NOW,
    data,
  };
}

function edge(id, source, kind, target) {
  return {
    id,
    source,
    kind,
    target,
    provenance: "server_observed",
    source_ref: `records/${id}`,
    digest: SHA,
    advisory: false,
  };
}

const nodes = [
  node("n.agent.current", "agent_run", "run.current", { fresh_session: true }),
  node("n.agent.origin", "agent_run", "run.origin", { fresh_session: false }),
  node("n.change.current", "changeset", "run.current"),
  node("n.file.config", "file", "run.current", { path: "app/config.py" }),
  node("n.file.current", "file", "run.current", { path: "app/auth/limiter.py" }),
  node("n.hunk.current", "hunk", "run.current", { path: "app/auth/limiter.py" }),
  node("n.memory", "memory_revision", null),
].sort((left, right) => left.id.localeCompare(right.id));

const edges = [
  edge("e.1", "n.agent.current", "PRODUCED", "n.change.current"),
  edge("e.2", "n.change.current", "CONTAINS", "n.hunk.current"),
  edge("e.3", "n.hunk.current", "MODIFIES", "n.file.current"),
  edge("e.4", "n.agent.origin", "PACKED_IN", "n.memory"),
].sort((left, right) => left.id.localeCompare(right.id));

const graph = {
  revision: 1,
  graph_hash: SHA,
  nodes,
  edges,
  truncated: false,
  omitted_counts: {},
};

test("coordinates are deterministic regardless of response iteration order", () => {
  validateGraphResponse(graph);
  const first = layoutGraph({ nodes, edges }, { runId: "run.current" });
  const second = layoutGraph(
    { nodes: [...nodes].reverse(), edges: [...edges].reverse() },
    { runId: "run.current" },
  );
  assert.deepEqual(first, second);
  assert.equal(first.focusId, "n.change.current");
});

test("filtered edges remain resolvable and are a strict API subset", () => {
  const view = filterGraph(graph, {
    runId: "run.current",
    currentRunOnly: true,
    showMemoryOrigin: true,
  });
  const apiEdgeIds = new Set(graph.edges.map((item) => item.id));
  const visibleNodeIds = new Set(view.nodes.map((item) => item.id));
  assert.ok(view.edges.every((item) => apiEdgeIds.has(item.id)));
  assert.ok(view.edges.every((item) => visibleNodeIds.has(item.source) && visibleNodeIds.has(item.target)));
  assert.ok(!view.nodes.some((item) => item.id === "n.agent.origin"));
  assert.ok(view.nodes.some((item) => item.id === "n.memory"), "run-neutral evidence remains visible");

  const dangling = structuredClone(graph);
  dangling.edges[0].target = "n.missing";
  assert.throws(() => validateGraphResponse(dangling), /unknown target/);
});

test("current-run, origin, path, and kind filters have frozen behavior", () => {
  const noOrigin = filterGraph(graph, {
    runId: "run.current",
    showMemoryOrigin: false,
  });
  assert.ok(!noOrigin.nodes.some((item) => item.run_id === "run.origin"));

  const authPath = filterGraph(graph, {
    runId: "run.current",
    pathPrefix: "app/auth",
    showMemoryOrigin: true,
  });
  assert.ok(authPath.nodes.some((item) => item.id === "n.file.current"));
  assert.ok(!authPath.nodes.some((item) => item.id === "n.file.config"));
  assert.ok(authPath.nodes.some((item) => item.id === "n.change.current"), "non-path proof nodes remain");
  assert.equal(pathMatches("app/authx/limiter.py", "app/auth"), false);

  const hunks = filterGraph(graph, {
    runId: "run.current",
    kind: "hunk",
    showMemoryOrigin: true,
  });
  assert.deepEqual(hunks.nodes.map((item) => item.id), ["n.hunk.current"]);
  assert.deepEqual(hunks.edges, []);
});

test("accessible proof rows are exactly one-to-one with visible API edges", () => {
  const view = filterGraph(graph, {
    runId: "run.current",
    pathPrefix: "app/auth",
    showMemoryOrigin: true,
  });
  const rows = proofRows(view);
  assert.deepEqual(rows.map((row) => row.edgeId), view.edges.map((item) => item.id));
  assert.equal(new Set(rows.map((row) => row.edgeId)).size, view.edges.length);
  assert.ok(rows.every((row) => row.text.includes("→")));
});

test("renderer never uses innerHTML", () => {
  const source = readFileSync(new URL("../src/app.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\binnerHTML\b/);
});
