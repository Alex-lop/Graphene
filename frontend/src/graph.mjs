export const MAX_NODES = 25;
export const MAX_EDGES = 40;

export const NODE_KINDS = Object.freeze([
  "agent_run",
  "changeset",
  "file",
  "hunk",
  "feedback",
  "memory_revision",
  "context_packet",
  "policy_check",
  "test_receipt",
  "human_decision",
  "promotion_receipt",
]);

export const EDGE_KINDS = Object.freeze([
  "PRODUCED",
  "CONTAINS",
  "MODIFIES",
  "IMPORTS",
  "TRIGGERED",
  "LEARNED_AS",
  "APPROVED",
  "PACKED_IN",
  "INJECTED_INTO",
  "VALIDATED",
  "DENIED",
  "ALLOWED",
  "AUTHORIZED",
  "PROMOTED_AS",
]);

export const NODE_WIDTH = 218;
export const NODE_HEIGHT = 104;

const NODE_KIND_SET = new Set(NODE_KINDS);
const EDGE_KIND_SET = new Set(EDGE_KINDS);
const PROVENANCE = new Set([
  "server_observed",
  "server_derived",
  "human_attested",
  "model_proposed",
]);
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function assert(condition, message) {
  if (!condition) throw new TypeError(message);
}

function validateNode(node, label = "graph node") {
  assert(isRecord(node), `${label} must be an object`);
  assert(typeof node.id === "string" && IDENTIFIER.test(node.id), `${label} has an invalid id`);
  assert(NODE_KIND_SET.has(node.kind), `${label} has an unknown kind`);
  assert(typeof node.label === "string" && node.label.length > 0, `${label} needs a label`);
  assert(typeof node.repo_id === "string" && IDENTIFIER.test(node.repo_id), `${label} has an invalid repo_id`);
  assert(node.run_id === null || (typeof node.run_id === "string" && IDENTIFIER.test(node.run_id)), `${label} has an invalid run_id`);
  assert(PROVENANCE.has(node.provenance), `${label} has unknown provenance`);
  assert(typeof node.source_ref === "string" && node.source_ref.length > 0, `${label} needs a source_ref`);
  assert(typeof node.digest === "string" && SHA256.test(node.digest), `${label} has an invalid digest`);
  assert(typeof node.status === "string", `${label} has an invalid status`);
  assert(typeof node.created_at === "string" && node.created_at.length > 0, `${label} needs created_at`);
  assert(isRecord(node.data), `${label} data must be an object`);
}

export function validateGraphResponse(graph) {
  assert(isRecord(graph), "graph response must be an object");
  assert(Number.isInteger(graph.revision) && graph.revision >= 1, "graph revision must be positive");
  assert(typeof graph.graph_hash === "string" && SHA256.test(graph.graph_hash), "graph_hash must be SHA-256");
  assert(Array.isArray(graph.nodes) && graph.nodes.length <= MAX_NODES, `graph exceeds ${MAX_NODES} nodes`);
  assert(Array.isArray(graph.edges) && graph.edges.length <= MAX_EDGES, `graph exceeds ${MAX_EDGES} edges`);
  assert(typeof graph.truncated === "boolean", "graph truncated flag must be boolean");
  assert(isRecord(graph.omitted_counts), "graph omitted_counts must be an object");

  const nodeIds = new Set();
  for (const node of graph.nodes) {
    validateNode(node);
    assert(!nodeIds.has(node.id), `duplicate node id: ${node.id}`);
    nodeIds.add(node.id);
  }

  const edgeIds = new Set();
  for (const edge of graph.edges) {
    assert(isRecord(edge), "graph edge must be an object");
    assert(typeof edge.id === "string" && IDENTIFIER.test(edge.id), "graph edge has an invalid id");
    assert(!edgeIds.has(edge.id), `duplicate edge id: ${edge.id}`);
    edgeIds.add(edge.id);
    assert(typeof edge.source === "string" && nodeIds.has(edge.source), `edge ${edge.id} has an unknown source`);
    assert(typeof edge.target === "string" && nodeIds.has(edge.target), `edge ${edge.id} has an unknown target`);
    assert(EDGE_KIND_SET.has(edge.kind), `edge ${edge.id} has an unknown kind`);
    assert(PROVENANCE.has(edge.provenance), `edge ${edge.id} has unknown provenance`);
    assert(typeof edge.source_ref === "string" && edge.source_ref.length > 0, `edge ${edge.id} needs a source_ref`);
    assert(typeof edge.digest === "string" && SHA256.test(edge.digest), `edge ${edge.id} has an invalid digest`);
    assert(typeof edge.advisory === "boolean", `edge ${edge.id} advisory must be boolean`);
  }

  for (const [key, value] of Object.entries(graph.omitted_counts)) {
    assert(key.length > 0 && Number.isInteger(value) && value >= 0, "omitted counts must be non-negative integers");
  }
  const hasOmissions = Object.values(graph.omitted_counts).some((value) => value > 0);
  assert(graph.truncated === hasOmissions, "truncated must match omitted_counts");
  return graph;
}

export function validateNodeDetail(detail, summary) {
  validateNode(detail, "node detail");
  assert(detail.id === summary.id, "node detail id does not match the selected node");
  assert(detail.kind === summary.kind, "node detail kind does not match the selected node");
  assert(detail.digest === summary.digest, "node detail digest does not match the graph node");
  if (detail.kind === "hunk") {
    assert(typeof detail.data.unified_diff === "string", "hunk detail is missing unified_diff");
    assert(typeof detail.data.exact_hunk_sha256 === "string" && SHA256.test(detail.data.exact_hunk_sha256), "hunk detail is missing its exact digest");
  }
  return detail;
}

export function pathMatches(path, rawPrefix) {
  const prefix = String(rawPrefix ?? "").trim().replace(/\/+$/, "");
  if (!prefix) return true;
  return path === prefix || path.startsWith(`${prefix}/`);
}

export function filterGraph(graph, filters = {}) {
  const runId = filters.runId ?? null;
  const hideOrigin = filters.currentRunOnly === true || filters.showMemoryOrigin === false;
  const pathPrefix = String(filters.pathPrefix ?? "").trim();
  const kind = NODE_KIND_SET.has(filters.kind) ? filters.kind : "";

  const nodes = graph.nodes.filter((node) => {
    if (hideOrigin && node.run_id !== null && node.run_id !== runId) return false;
    if (kind && node.kind !== kind) return false;
    if (
      pathPrefix &&
      (node.kind === "file" || node.kind === "hunk") &&
      !pathMatches(String(node.data.path ?? ""), pathPrefix)
    ) return false;
    return true;
  });

  const visibleIds = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
  );
  return { nodes, edges };
}

function focusNode(nodes, runId, selectedId) {
  const ordered = [...nodes].sort((left, right) => left.id.localeCompare(right.id));
  const selected = ordered.find(
    (node) => node.id === selectedId && (node.kind === "changeset" || node.kind === "hunk"),
  );
  return selected ??
    ordered.find((node) => node.run_id === runId && node.kind === "changeset") ??
    ordered.find((node) => node.run_id === runId && node.kind === "hunk") ??
    ordered.find((node) => node.kind === "changeset" || node.kind === "hunk") ??
    null;
}

function laneFor(node, edges, runId) {
  if (node.kind === "agent_run") return node.data.fresh_session ? "future" : "origin";
  if (node.kind === "changeset") return node.run_id === runId ? "middle" : "origin";
  if (node.kind === "feedback" || node.kind === "memory_revision") return "origin";
  if (node.kind === "context_packet") return "future";
  if (node.kind === "file" || node.kind === "hunk") return "right";
  if (node.kind === "human_decision") {
    return edges.some((edge) => edge.source === node.id && edge.kind === "APPROVED")
      ? "origin"
      : "bottom";
  }
  if (
    node.kind === "policy_check" ||
    node.kind === "test_receipt" ||
    node.kind === "promotion_receipt"
  ) return "bottom";
  return "middle";
}

function placeGrid(positions, ids, xs, startY, stepY, lane) {
  ids.sort().forEach((id, index) => {
    positions[id] = {
      x: xs[index % xs.length],
      y: startY + Math.floor(index / xs.length) * stepY,
      lane,
    };
  });
}

export function layoutGraph(view, { runId = null, selectedId = null } = {}) {
  const focus = focusNode(view.nodes, runId, selectedId);
  const lanes = { origin: [], future: [], right: [], bottom: [], middle: [] };
  for (const node of view.nodes) {
    if (node.id !== focus?.id) lanes[laneFor(node, view.edges, runId)].push(node.id);
  }

  const positions = {};
  if (focus) positions[focus.id] = { x: 650, y: 370, lane: "focus" };
  placeGrid(positions, lanes.origin, [130, 360], 100, 130, "origin");
  placeGrid(positions, lanes.future, [800, 1030], 100, 130, "future");
  placeGrid(positions, lanes.right, [1260, 1485], 100, 130, "right");
  placeGrid(positions, lanes.middle, [555, 775], 100, 130, "middle");

  const verticalRows = Math.max(
    Math.ceil(lanes.origin.length / 2),
    Math.ceil(lanes.future.length / 2),
    Math.ceil(lanes.right.length / 2),
    Math.ceil(lanes.middle.length / 2),
    1,
  );
  const bottomY = Math.max(700, 100 + verticalRows * 130 + 100);
  placeGrid(
    positions,
    lanes.bottom,
    [140, 385, 630, 875, 1120, 1365],
    bottomY,
    130,
    "bottom",
  );
  const bottomRows = Math.max(Math.ceil(lanes.bottom.length / 6), 1);

  return {
    positions,
    focusId: focus?.id ?? null,
    width: 1600,
    height: Math.max(860, bottomY + bottomRows * 130),
  };
}

export function edgeGeometry(source, target) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  if (dx === 0 && dy === 0) return { x1: source.x, y1: source.y, x2: target.x, y2: target.y };
  const horizontal = dx === 0 ? Infinity : (NODE_WIDTH / 2) / Math.abs(dx);
  const vertical = dy === 0 ? Infinity : (NODE_HEIGHT / 2) / Math.abs(dy);
  const offset = Math.min(horizontal, vertical);
  return {
    x1: source.x + dx * offset,
    y1: source.y + dy * offset,
    x2: target.x - dx * offset,
    y2: target.y - dy * offset,
  };
}

export function proofRows(view) {
  const nodes = new Map(view.nodes.map((node) => [node.id, node]));
  return view.edges.map((edge) => {
    const source = nodes.get(edge.source);
    const target = nodes.get(edge.target);
    if (!source || !target) throw new TypeError(`edge ${edge.id} is not resolvable`);
    return {
      edgeId: edge.id,
      sourceId: source.id,
      targetId: target.id,
      kind: edge.kind,
      provenance: edge.provenance,
      advisory: edge.advisory,
      sourceRef: edge.source_ref,
      digest: edge.digest,
      text: `${source.label} — ${edge.kind} → ${target.label}`,
    };
  });
}
