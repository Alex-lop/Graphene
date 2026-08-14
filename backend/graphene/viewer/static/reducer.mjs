const KIND_GROUPS = Object.freeze({
  agent: "agent",
  agent_run: "agent",
  invocation: "agent",
  tool: "tool",
  tool_operation: "tool",
  file: "evidence",
  evidence: "evidence",
  evidence_reference: "evidence",
  changeset: "tool",
  hunk: "tool",
  feedback: "human",
  human: "human",
  human_decision: "human",
  memory: "human",
  memory_revision: "human",
  policy: "policy",
  policy_decision: "policy",
  policy_check: "policy",
  test: "test",
  test_receipt: "test",
  handoff: "handoff",
  context_brief: "handoff",
  context_packet: "handoff",
  promotion: "handoff",
  promotion_receipt: "handoff",
});

const text = (value, fallback = "") => typeof value === "string" && value.trim() ? value.trim() : fallback;
const count = (value, fallback = 1) => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : fallback;
const record = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const reference = (value) => {
  if (typeof value === "string") return text(value) || null;
  const item = record(value);
  const identity = [text(item.kind), text(item.id)].filter(Boolean).join(":");
  return identity ? `${identity}${text(item.sha256) ? ` · sha256:${item.sha256}` : ""}` : null;
};

export function kindGroup(kind) {
  return KIND_GROUPS[String(kind ?? "").toLowerCase()] ?? "evidence";
}

export function normalizeNode(raw) {
  const node = record(raw);
  if (!text(node.id)) throw new TypeError("node needs a stable id");
  const metadata = record(node.metadata ?? node.data);
  return {
    id: text(node.id),
    kind: text(node.kind, "evidence"),
    group: kindGroup(node.kind),
    label: text(node.public_label ?? node.label, "Unlabelled evidence"),
    status: text(node.status, "observed"),
    truthKind: text(node.truth_kind ?? node.provenance, "verified_event"),
    runId: text(node.run_id) || null,
    sequence: Number.isInteger(node.sequence ?? node.seq) ? (node.sequence ?? node.seq) : null,
    eventId: text(node.event_id) || null,
    activity: Math.min(1000, count(node.activity_count ?? node.activity, 1)),
    sourceRef: reference(node.source_ref ?? node.evidence_ref),
    digest: text(node.digest ?? node.sha256 ?? node.source_ref?.sha256 ?? node.evidence_ref?.sha256) || null,
    metadata,
  };
}

export function normalizeEdge(raw) {
  const edge = record(raw);
  if (!text(edge.id) || !text(edge.source) || !text(edge.target)) throw new TypeError("edge needs stable id, source, and target");
  return {
    id: text(edge.id),
    source: text(edge.source),
    target: text(edge.target),
    kind: text(edge.kind, "RELATED_TO"),
    truthKind: text(edge.truth_kind ?? edge.provenance, "verified_event"),
    activity: Math.min(1000, count(edge.activity_count ?? edge.interaction_count, 1)),
    sourceRef: reference(edge.source_ref ?? edge.evidence_ref),
    digest: text(edge.digest ?? edge.sha256 ?? edge.evidence_ref?.sha256) || null,
  };
}

export function createState(snapshot = {}) {
  const nodes = new Map();
  const edges = new Map();
  for (const raw of snapshot.nodes ?? []) {
    const node = normalizeNode(raw);
    nodes.set(node.id, node);
  }
  for (const raw of snapshot.edges ?? []) {
    const edge = normalizeEdge(raw);
    if (nodes.has(edge.source) && nodes.has(edge.target)) edges.set(edge.id, edge);
  }
  return {
    viewVersion: String(snapshot.view_version ?? "1"),
    rootRunId: text(snapshot.root_run_id) || null,
    heads: Array.isArray(snapshot.heads) ? snapshot.heads : snapshot.heads ? [snapshot.heads] : [],
    cursor: snapshot.cursor ?? null,
    graphSha256: text(snapshot.graph_sha256),
    omittedCounts: record(snapshot.omitted_counts),
    unknowns: Array.isArray(snapshot.unknowns) ? snapshot.unknowns : [],
    nodes,
    edges,
    seen: new Set(),
    invalidReason: null,
  };
}

function identity(delta, operation, payload) {
  return text(delta.identity) || [delta.run_id, delta.seq ?? delta.sequence, delta.event_id, operation, payload?.id].filter((value) => value !== undefined && value !== null).join(":");
}

export function applyDelta(state, rawDelta) {
  if (state.invalidReason) return state;
  const envelope = record(rawDelta);
  const envelopeType = text(envelope.type).toLowerCase();
  const delta = envelopeType === "delta"
    ? { ...record(envelope.delta), cursor: envelope.cursor ?? envelope.delta?.cursor }
    : envelopeType === "reset"
      ? { op: "reset", snapshot: envelope.snapshot, cursor: envelope.cursor }
      : envelopeType === "evidence_invalid"
        ? { op: "evidence_invalid", reason: envelope.detail }
        : envelope;
  const operation = text(delta.op ?? delta.type ?? delta.kind).toLowerCase();
  const payload = delta.payload ?? delta.node ?? delta.edge ?? delta.snapshot ?? delta;
  const key = identity(delta, operation, payload);
  if (key && state.seen.has(key)) return state;
  if (key) state.seen.add(key);
  state.cursor = delta.cursor ?? state.cursor;

  if (operation === "evidence_invalid" || operation === "invalid") {
    state.invalidReason = text(delta.reason ?? payload.reason, "Verified evidence changed.");
  } else if (operation === "reset") {
    return createState(payload.snapshot ?? payload);
  } else if (operation === "upsert_node") {
    const node = normalizeNode(payload);
    node.runId ??= text(delta.run_id) || null;
    node.sequence ??= Number.isInteger(delta.seq ?? delta.sequence) ? (delta.seq ?? delta.sequence) : null;
    node.eventId ??= text(delta.event_id) || null;
    state.nodes.set(node.id, { ...state.nodes.get(node.id), ...node });
  } else if (operation === "upsert_edge") {
    const edge = normalizeEdge(payload);
    if (!state.nodes.has(edge.source) || !state.nodes.has(edge.target)) throw new TypeError(`edge ${edge.id} references an unknown node`);
    state.edges.set(edge.id, { ...state.edges.get(edge.id), ...edge });
  } else if (operation === "set_status") {
    const id = text(payload.id ?? payload.node_id);
    const existing = state.nodes.get(id);
    if (!existing) throw new TypeError(`status references an unknown node: ${id || "(missing)"}`);
    state.nodes.set(id, { ...existing, status: text(payload.status, existing.status) });
  } else if (operation === "remove") {
    const id = text(payload.id);
    state.nodes.delete(id);
    state.edges.delete(id);
    for (const [edgeId, edge] of state.edges) if (edge.source === id || edge.target === id) state.edges.delete(edgeId);
  } else throw new TypeError(`unknown delta operation: ${operation || "(missing)"}`);
  return state;
}

export function deltaSubjectId(rawDelta) {
  const envelope = record(rawDelta);
  if (text(envelope.current_id)) return text(envelope.current_id);
  const delta = text(envelope.type).toLowerCase() === "delta" ? record(envelope.delta) : envelope;
  return text(delta.current_id ?? delta.node?.id ?? delta.edge?.target ?? delta.id) || null;
}

export async function evidenceInvalidResponse(response) {
  if (response.status !== 409) return null;
  try {
    const payload = await response.json();
    return payload?.code === "EVIDENCE_INVALID" ? text(payload.detail, "Verified evidence is invalid.") : "Viewer evidence request was rejected.";
  } catch {
    return "Viewer evidence request returned malformed invalid-evidence JSON.";
  }
}

export function applyThrough(snapshot, deltas, index) {
  let state = createState(snapshot);
  for (const delta of deltas.slice(0, index)) state = applyDelta(state, delta);
  return state;
}

export function headSummary(heads, rootRunId) {
  if (!heads.length) return "—";
  const root = heads.find((head) => head.run_id === rootRunId) ?? heads[0];
  const sequence = root.seq ?? root.sequence ?? root.verified_sequence;
  return `Root ${root.run_id} · seq ${sequence ?? "—"} · ${heads.length} family head${heads.length === 1 ? "" : "s"}`;
}

export function directedEvidenceIds(nodes, edges, selectedId) {
  const visibleIds = new Set(nodes.map(({ id }) => id));
  if (!visibleIds.has(selectedId)) return new Set();
  const result = new Set([selectedId]);
  for (const direction of ["ancestors", "descendants"]) {
    const queue = [selectedId];
    while (queue.length) {
      const current = queue.shift();
      for (const edge of edges) {
        const candidate = direction === "ancestors" && edge.target === current ? edge.source
          : direction === "descendants" && edge.source === current ? edge.target : null;
        if (candidate && visibleIds.has(candidate) && !result.has(candidate)) { result.add(candidate); queue.push(candidate); }
      }
    }
  }
  return result;
}

export function activityRadius(activity) {
  return Math.round(Math.min(72, 38 + Math.log2(1 + Math.max(0, activity)) * 7));
}

export function statusBadgeData(color) {
  const fill = /^#[0-9a-f]{6}$/i.test(color) ? color : "#73aa91";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"><circle cx="9" cy="9" r="7" fill="${fill}" stroke="#252a2e" stroke-width="3"/></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function hash(value) {
  let result = 2166136261;
  for (const char of value) result = Math.imul(result ^ char.charCodeAt(0), 16777619);
  return result >>> 0;
}

export function deterministicPositions(nodes, edges, previous = new Map(), organize = false) {
  const positions = new Map(previous);
  const groups = ["agent", "tool", "evidence", "human", "policy", "test", "handoff"];
  const incoming = new Map();
  for (const edge of edges) if (!incoming.has(edge.target)) incoming.set(edge.target, edge.source);
  const ordered = [...nodes].sort((left, right) =>
    String(left.runId ?? "shared").localeCompare(String(right.runId ?? "shared")) ||
    groups.indexOf(left.group) - groups.indexOf(right.group) ||
    left.id.localeCompare(right.id)
  );

  if (organize || positions.size === 0) {
    positions.clear();
    const byRun = new Map();
    for (const node of ordered) {
      const run = node.runId ?? "shared";
      if (!byRun.has(run)) byRun.set(run, []);
      byRun.get(run).push(node);
    }
    const runs = [...byRun].sort(([left], [right]) => left.localeCompare(right));
    const metrics = runs.map(([run, runNodes]) => {
      const columns = Math.min(10, Math.max(4, Math.ceil(Math.sqrt(runNodes.length * 1.8))));
      const rows = Math.ceil(runNodes.length / columns);
      return { run, runNodes, columns, rows, width: columns * 112 + 120, height: rows * 104 + 120 };
    });
    const cellWidth = Math.max(...metrics.map(({ width }) => width), 568);
    const cellHeight = Math.max(...metrics.map(({ height }) => height), 432);
    const runColumns = Math.min(metrics.length, Math.max(1, Math.ceil(Math.sqrt(metrics.length * 1.7 * cellHeight / cellWidth))));
    metrics.forEach(({ runNodes, columns }, runIndex) => {
      const originX = 50 + (runIndex % runColumns) * cellWidth;
      const originY = 50 + Math.floor(runIndex / runColumns) * cellHeight;
      runNodes.forEach((node, nodeIndex) => positions.set(node.id, {
        x: originX + 60 + (nodeIndex % columns) * 112,
        y: originY + 60 + Math.floor(nodeIndex / columns) * 104,
      }));
    });
  } else for (const node of ordered) {
    if (positions.has(node.id)) continue;
    const parent = positions.get(incoming.get(node.id));
    const seed = hash(node.id);
    if (parent) {
      const angle = (seed % 360) * Math.PI / 180;
      positions.set(node.id, { x: parent.x + Math.cos(angle) * 150, y: parent.y + Math.sin(angle) * 120 });
      continue;
    }
    const cluster = ordered.filter((candidate) => candidate.runId === node.runId && positions.has(candidate.id));
    const center = cluster.length ? cluster.reduce((sum, candidate) => {
      const point = positions.get(candidate.id);
      return { x: sum.x + point.x / cluster.length, y: sum.y + point.y / cluster.length };
    }, { x: 0, y: 0 }) : { x: 110, y: 110 };
    const angle = ((seed % 41) - 20) * Math.PI / 180;
    const radius = 120 + (seed % 4) * 42;
    positions.set(node.id, {
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
    });
  }
  for (const id of [...positions.keys()]) if (!nodes.some((node) => node.id === id)) positions.delete(id);
  return positions;
}

export function visibleGraph(state, enabledGroups) {
  const nodes = [...state.nodes.values()].filter((node) => enabledGroups.has(node.group));
  const ids = new Set(nodes.map((node) => node.id));
  return { nodes, edges: [...state.edges.values()].filter((edge) => ids.has(edge.source) && ids.has(edge.target)) };
}

export function statePositions(state, previous = new Map(), organize = false) {
  return deterministicPositions([...state.nodes.values()], [...state.edges.values()], previous, organize);
}
