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
  result: "handoff",
});

const text = (value, fallback = "") => typeof value === "string" && value.trim() ? value.trim() : fallback;
const count = (value, fallback = 1) => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : fallback;
const record = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const displayStatus = (value) => value === "PROMOTED" ? "GRAPHENE RECEIPT RECORDED" : value;
const reference = (value) => {
  if (typeof value === "string") return text(value) || null;
  const item = record(value);
  const identity = [text(item.kind), text(item.id)].filter(Boolean).join(":");
  return identity ? `${identity}${text(item.sha256) ? ` · sha256:${item.sha256}` : ""}` : null;
};

export const REVIEW_SECTIONS = Object.freeze([
  ["candidate", "Candidate / changed paths"],
  ["evidence", "Verified evidence"],
  ["human", "Recorded decisions and corrections"],
  ["context", "Inherited context: included and excluded"],
  ["outcome", "Outcome"],
  ["unknown", "Unknown / not captured"],
]);

const SUPPORT_CLASSES = new Set(["verified_support", "authorization"]);
const SUPPORT_KINDS = new Set(["supported_by", "authorized_by", "changes_path", "binds_path", "result_supported_by"]);
const PENDING_STATUSES = new Set(["asked", "awaiting_decision", "pending", "proposed", "ready_for_decision"]);
const DECISION_KINDS = new Set(["human", "feedback", "memory", "promotion"]);

export function truthLabel(value) {
  return ({
    simulated_fixture: "SIMULATED FIXTURE — NOT HUMAN ATTESTATION",
    human_attested: "HUMAN ATTESTED",
    policy_authoritative: "POLICY AUTHORITATIVE",
    runtime_observed: "RUNTIME OBSERVED",
    server_derived: "SERVER DERIVED",
    evidence_bound: "EVIDENCE BOUND",
    model_proposed: "MODEL PROPOSED",
  })[text(value).toLowerCase()] ?? text(value, "NOT ESTABLISHED").replaceAll("_", " ").toUpperCase();
}

export function kindGroup(kind) {
  return KIND_GROUPS[String(kind ?? "").toLowerCase()] ?? "evidence";
}

export function normalizeNode(raw) {
  const node = record(raw);
  if (!text(node.id)) throw new TypeError("node needs a stable id");
  const metadata = record(node.metadata ?? node.data);
  const label = text(node.public_label ?? node.label, "Unlabelled evidence")
    .replaceAll("Approved Handoff", "Handoff Boundary")
    .replace("Promotion Completed", "Graphene Receipt Recorded")
    .replace("Promotion Approved", "Candidate Approval Recorded")
    .replace("Promotion Denied", "Candidate Approval Denied");
  const rawStatus = text(node.status, "observed");
  return {
    id: text(node.id),
    kind: text(node.kind, "evidence"),
    group: kindGroup(node.kind),
    label,
    status: rawStatus,
    displayStatus: displayStatus(rawStatus),
    truthKind: text(node.truth_kind ?? node.provenance, "verified_event"),
    runId: text(node.run_id) || null,
    sequence: Number.isInteger(node.sequence ?? node.seq) ? (node.sequence ?? node.seq) : null,
    eventId: text(node.event_id) || null,
    recordedAt: text(node.recorded_at) || null,
    stage: text(node.stage) || null,
    activity: Math.min(1000, count(node.activity_count ?? node.activity, 1)),
    sourceRef: reference(node.source_ref ?? node.evidence_ref),
    digest: text(node.digest ?? node.sha256 ?? node.source_ref?.sha256 ?? node.evidence_ref?.sha256) || null,
    metadata,
  };
}

export function latestNodeId(nodes) {
  return [...nodes].sort((left, right) =>
    (Date.parse(left.recordedAt) || -Infinity) - (Date.parse(right.recordedAt) || -Infinity) ||
    Number(!left.id.startsWith("run:")) - Number(!right.id.startsWith("run:")) ||
    left.id.localeCompare(right.id)
  ).at(-1)?.id ?? null;
}

export function normalizeEdge(raw) {
  const edge = record(raw);
  if (!text(edge.id) || !text(edge.source) || !text(edge.target)) throw new TypeError("edge needs stable id, source, and target");
  return {
    id: text(edge.id),
    source: text(edge.source),
    target: text(edge.target),
    kind: text(edge.kind, "RELATED_TO"),
    relationshipClass: text(edge.relationship_class ?? edge.relation_class).toLowerCase() || null,
    relationshipLabel: text(edge.relationship_label) || null,
    supportDirection: text(edge.support_direction, "source_to_target"),
    supportPath: edge.support_path === true,
    truthKind: text(edge.truth_kind ?? edge.provenance, "verified_event"),
    activity: Math.min(1000, count(edge.activity_count ?? edge.interaction_count, 1)),
    sourceRef: reference(edge.source_ref ?? edge.evidence_ref),
    digest: text(edge.digest ?? edge.sha256 ?? edge.evidence_ref?.sha256) || null,
    runId: text(edge.run_id) || null,
    sequence: Number.isInteger(edge.seq ?? edge.sequence) ? (edge.seq ?? edge.sequence) : null,
    eventId: text(edge.event_id) || null,
    metadata: record(edge.metadata),
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
  const reviewBrief = record(snapshot.review_brief);
  return {
    viewVersion: String(snapshot.view_version ?? "1"),
    rootRunId: text(snapshot.root_run_id) || null,
    heads: Array.isArray(snapshot.heads) ? snapshot.heads : snapshot.heads ? [snapshot.heads] : [],
    cursor: snapshot.cursor ?? null,
    graphSha256: text(snapshot.graph_sha256),
    omittedCounts: record(snapshot.omitted_counts),
    collapsedCounts: record(snapshot.collapsed_counts),
    totalCounts: record(reviewBrief.counts ?? snapshot.total_counts),
    unknowns: Array.isArray(snapshot.unknowns) ? snapshot.unknowns : [],
    reviewBrief,
    attention: record(reviewBrief.attention ?? snapshot.attention),
    stages: Array.isArray(snapshot.stages) ? snapshot.stages : [],
    currentNeighborhood: Array.isArray(snapshot.current_neighborhood) ? snapshot.current_neighborhood.filter((id) => typeof id === "string") : [],
    currentId: text(snapshot.current_id) || latestNodeId(nodes.values()),
    supportPaths: Array.isArray(snapshot.support_paths) ? snapshot.support_paths.map(record) : [],
    captureBoundary: Array.isArray(snapshot.capture_boundary) ? snapshot.capture_boundary : [],
    nodes,
    edges,
    seen: new Set(),
    invalidReason: null,
  };
}

function identity(delta, operation, payload) {
  return text(delta.identity) || [delta.run_id, delta.seq ?? delta.sequence, delta.event_id, operation, payload?.id].filter((value) => value !== undefined && value !== null).join(":");
}

function cloneState(state) {
  return { ...state, nodes: new Map(state.nodes), edges: new Map(state.edges), seen: new Set(state.seen) };
}

function verifiedHeads(state, envelope) {
  if (!Array.isArray(envelope.heads)) throw new TypeError("delta envelope needs verified heads");
  const previous = new Map(state.heads.map((head) => [text(head.run_id), head]));
  const incoming = new Map();
  for (const head of envelope.heads) {
    const runId = text(head?.run_id);
    if (!runId || !Number.isInteger(head?.seq) || head.seq < 1 || incoming.has(runId)) {
      throw new TypeError("delta envelope has invalid verified heads");
    }
    incoming.set(runId, head);
  }
  for (const [runId, head] of previous) {
    const next = incoming.get(runId);
    if (!next || next.seq < head.seq) throw new TypeError(`stale or out-of-order delta head for ${runId}`);
    if (next.seq === head.seq && text(head.event_sha256) && text(next.event_sha256) && head.event_sha256 !== next.event_sha256) {
      throw new TypeError(`conflicting delta head for ${runId}`);
    }
  }
  return envelope.heads;
}

export function applyDelta(state, rawDelta) {
  if (state.invalidReason) return state;
  const envelope = record(rawDelta);
  const envelopeType = text(envelope.type).toLowerCase();
  if (envelopeType === "delta" && Array.isArray(envelope.deltas)) {
    const heads = verifiedHeads(state, envelope);
    let next = cloneState(state);
    for (const delta of envelope.deltas) next = applyDelta(next, { type: "delta", cursor: envelope.cursor, delta });
    const reviewBrief = record(envelope.review_brief);
    next.cursor = envelope.cursor ?? next.cursor;
    next.currentId = text(envelope.current_id) || next.currentId;
    next.heads = heads;
    next.graphSha256 = text(envelope.graph_sha256, next.graphSha256);
    next.omittedCounts = record(envelope.omitted_counts ?? next.omittedCounts);
    next.unknowns = Array.isArray(envelope.unknowns) ? envelope.unknowns : next.unknowns;
    next.reviewBrief = Object.keys(reviewBrief).length ? reviewBrief : next.reviewBrief;
    next.attention = record(reviewBrief.attention ?? next.attention);
    next.totalCounts = record(reviewBrief.counts ?? next.totalCounts);
    next.supportPaths = Array.isArray(envelope.support_paths) ? envelope.support_paths.map(record) : next.supportPaths;
    return next;
  }
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
    const status = text(payload.status, existing.status);
    state.nodes.set(id, { ...existing, status, displayStatus: displayStatus(status) });
  } else if (operation === "remove") {
    const id = text(payload.id);
    const removeKind = text(payload.remove_kind ?? delta.remove_kind).toLowerCase();
    if (removeKind === "edge") state.edges.delete(id);
    else if (removeKind === "node") {
      state.nodes.delete(id);
      for (const [edgeId, edge] of state.edges) if (edge.source === id || edge.target === id) state.edges.delete(edgeId);
    } else throw new TypeError(`remove needs a typed target: ${removeKind || "(missing)"}`);
  } else throw new TypeError(`unknown delta operation: ${operation || "(missing)"}`);
  return state;
}

export function deltaSubjectId(rawDelta) {
  const envelope = record(rawDelta);
  if (text(envelope.current_id)) return text(envelope.current_id);
  const delta = text(envelope.type).toLowerCase() === "delta" ? record(envelope.delta) : envelope;
  return text(delta.current_id ?? delta.node?.id ?? delta.edge?.target ?? delta.id) || null;
}

function nodeFact(node, value = node.label) {
  return {
    id: `node:${node.id}`,
    label: node.label,
    value: String(value),
    truthKind: node.truthKind,
    nodeIds: [node.id],
    edgeIds: [],
  };
}

function normalizeFact(raw, key, index) {
  if (typeof raw === "string") return { id: `${key}:${index}`, label: raw, value: raw, truthKind: "server_derived", nodeIds: [], edgeIds: [] };
  const fact = record(raw);
  const labels = {
    "candidate:paths": "Changed paths", "candidate:hunks": "Hunk receipt", "candidate:bound_test": "Fixed-test binding",
    "context:included": "Included context", "context:opened": "Opened context", "context:excluded": "Excluded context",
    "outcome:current": "Recorded outcome",
  };
  return {
    id: text(fact.id, `${key}:${index}`),
    label: text(fact.label ?? fact.title, labels[fact.id] ?? (String(fact.id ?? "").startsWith("human:") ? "Recorded decision / correction" : "Captured fact")),
    value: text(fact.value ?? fact.text ?? fact.summary, "not established by captured evidence"),
    status: text(fact.status),
    truthKind: text(fact.truth_kind, "server_derived"),
    nodeIds: Array.isArray(fact.node_ids) ? fact.node_ids.filter((id) => typeof id === "string") : [],
    edgeIds: Array.isArray(fact.edge_ids) ? fact.edge_ids.filter((id) => typeof id === "string") : [],
    metadata: record(fact.metadata),
  };
}

function explicitFacts(state, key) {
  const contractKey = ({ evidence: "verified_evidence", human: "human_intervention", context: "inherited_context" })[key] ?? key;
  const section = Array.isArray(state.reviewBrief.sections) ? state.reviewBrief.sections.find((item) => item?.key === contractKey) : null;
  const raw = section?.facts ?? record(state.reviewBrief.sections)[contractKey] ?? state.reviewBrief[contractKey];
  if (Array.isArray(raw)) return raw.map((fact, index) => normalizeFact(fact, key, index));
  if (raw !== undefined) return [normalizeFact(raw, key, 0)];
  return [];
}

function missingFact(key) {
  return { id: `missing:${key}`, label: "Evidence gap", value: "not established by captured evidence", truthKind: "not_established", nodeIds: [], edgeIds: [] };
}

export function attentionFact(state) {
  if (state.invalidReason) return { id: "evidence-invalid", label: "EVIDENCE_INVALID", value: state.invalidReason, truthKind: "invalid", nodeIds: [], edgeIds: [] };
  if (Object.keys(state.attention).length) return normalizeFact(state.attention, "attention", 0);
  const allNodes = [...state.nodes.values()];
  const matched = (node) => allNodes.some((candidate) =>
    candidate.runId === node.runId && (candidate.sequence ?? 0) > (node.sequence ?? 0) && (
      (node.kind === "human" && node.status.toLowerCase() === "asked" && candidate.kind === "human" && candidate.status.toLowerCase() === "answered") ||
      (node.kind === "memory" && node.status.toLowerCase() === "proposed" && candidate.kind === "memory" && ["approved", "rejected"].includes(candidate.status.toLowerCase())) ||
      (node.kind === "promotion" && PENDING_STATUSES.has(node.status.toLowerCase()) && candidate.kind === "promotion" && ["approved", "denied", "rejected"].includes(candidate.status.toLowerCase()))
    )
  );
  const pending = allNodes
    .filter((node) => DECISION_KINDS.has(node.kind) && PENDING_STATUSES.has(node.status.toLowerCase()) && !matched(node))
    .sort((left, right) => (right.sequence ?? 0) - (left.sequence ?? 0) || left.id.localeCompare(right.id));
  return pending.length ? nodeFact(pending[0]) : { id: "attention-clear", label: "Decision state", value: "No unresolved Graphene decision", truthKind: "server_derived", nodeIds: [], edgeIds: [] };
}

export function reviewBriefFacts(state) {
  const sections = Object.fromEntries(REVIEW_SECTIONS.map(([key]) => [key, explicitFacts(state, key)]));
  const nodes = [...state.nodes.values()];
  if (!sections.candidate.length && Array.isArray(state.reviewBrief.changed_paths)) sections.candidate.push(...state.reviewBrief.changed_paths.map((fact, index) => normalizeFact(fact, "changed-path", index)));
  if (!sections.evidence.length && Array.isArray(state.reviewBrief.bound_paths)) sections.evidence.push(...state.reviewBrief.bound_paths.map((fact, index) => normalizeFact(fact, "bound-path", index)));
  if (!sections.candidate.length) {
    sections.candidate.push(...nodes.filter((node) => node.kind === "file" && (Number(node.metadata.added_lines) > 0 || Number(node.metadata.deleted_lines) > 0 || node.metadata.changed === true)).map((node) => nodeFact(node, node.metadata.path ?? node.label)));
    sections.candidate.push(...nodes.filter((node) => node.kind === "changeset").map((node) => nodeFact(node, [node.metadata.changed_path_count !== undefined ? `${node.metadata.changed_path_count} changed path(s)` : null, node.metadata.hunk_count !== undefined ? `${node.metadata.hunk_count} hunk(s)` : null].filter(Boolean).join(" · ") || node.label)));
  }
  if (!sections.evidence.length) {
    sections.evidence.push(...nodes.filter((node) => node.kind === "test").map((node) => nodeFact(node, node.metadata.passed === true ? `${node.label} · passing result` : node.label)));
    sections.evidence.push(...nodes.filter((node) => node.kind === "file" && node.metadata.bound_test_pass === true).map((node) => nodeFact(node, `${node.metadata.path ?? node.label} · bound passing test`)));
  }
  if (!sections.human.length) sections.human.push(...nodes.filter((node) => ["feedback", "human", "memory"].includes(node.kind)).map((node) => nodeFact(node)));
  if (!sections.context.length) sections.context.push(...nodes.filter((node) => node.kind === "handoff" || (node.kind === "policy" && /denied|blocked/i.test(node.status))).map((node) => nodeFact(node)));
  if (!sections.outcome.length) sections.outcome.push(...nodes.filter((node) => node.kind === "promotion").map((node) => nodeFact(node)));
  if (!sections.unknown.length) {
    sections.unknown.push(...state.unknowns.map((unknown, index) => ({ id: `unknown:${index}`, label: "Explicit unknown", value: String(unknown), truthKind: "server_derived", nodeIds: [], edgeIds: [] })));
    sections.unknown.push(...state.captureBoundary.map((item, index) => ({ id: `boundary:${index}`, label: "Capture boundary", value: String(item), truthKind: "server_derived", nodeIds: [], edgeIds: [] })));
  }
  for (const [key] of REVIEW_SECTIONS) if (!sections[key].length) sections[key].push(missingFact(key));
  return sections;
}

export function decisionReceipt(state) {
  const sections = reviewBriefFacts(state);
  const attention = attentionFact(state);
  const outcomeKind = text(state.reviewBrief.outcome_kind, "not_established");
  const changedPaths = Array.isArray(state.reviewBrief.changed_paths) ? state.reviewBrief.changed_paths.filter((path) => typeof path === "string") : [];
  const boundPaths = new Set(Array.isArray(state.reviewBrief.bound_paths) ? state.reviewBrief.bound_paths.filter((path) => typeof path === "string") : []);
  const testFact = sections.candidate.find((fact) => fact.id === "candidate:bound_test");
  const receiptPassed = testFact?.status === "established" && testFact.metadata?.passed === true;
  const pending = attention.status === "pending" || count(attention.metadata?.pending_count, 0) > 0;
  return {
    state: pending ? "required" : outcomeKind === "not_established" ? "not_open" : "recorded",
    outcomeKind,
    paths: changedPaths.map((path) => ({ path, boundToPassingReceipt: receiptPassed && boundPaths.has(path) })),
    explicitLimitCount: sections.unknown.filter((fact) => fact.status === "not_established").length,
  };
}

export function outcomeLabel(value) {
  return ({
    graphene_receipt_only: "Graphene receipt recorded · no commit established",
    isolated_local_commit: "Isolated local commit recorded",
    rejected: "Candidate rejected",
    failed: "Run failed",
  })[text(value)] ?? null;
}

export function stageGroups(state) {
  if (state.stages.length) return state.stages.map((stage, index) => {
    const item = record(stage);
    return { id: text(item.id, `stage-${index}`), label: text(item.label, `Captured stage ${index + 1}`), status: text(item.status), nodeIds: Array.isArray(item.node_ids) ? item.node_ids.filter((id) => typeof id === "string") : [] };
  });
  const stageLabels = {
    source_work: "Source work",
    human_correction_scope: "Human correction / scope",
    approved_handoff: "Handoff boundary",
    consumer_work: "Isolated consumer work",
    candidate_decision: "Candidate decision",
    local_result: "Local result",
  };
  const projectedStages = new Map();
  for (const node of state.nodes.values()) if (node.stage) {
    if (!projectedStages.has(node.stage)) projectedStages.set(node.stage, []);
    projectedStages.get(node.stage).push(node.id);
  }
  if (projectedStages.size) return Object.entries(stageLabels).map(([stage, label]) => ({ id: stage, label, status: projectedStages.has(stage) ? "captured" : "not established", nodeIds: projectedStages.get(stage) ?? [] }));
  const runs = new Map();
  for (const node of state.nodes.values()) {
    const run = node.runId ?? "shared";
    if (!runs.has(run)) runs.set(run, []);
    runs.get(run).push(node.id);
  }
  return [...runs].map(([runId, nodeIds], index) => ({ id: runId, label: `Captured stage ${index + 1}`, status: "", nodeIds }));
}

export function verifiedSupportPath(state, selectedId) {
  if (!state.nodes.has(selectedId)) return { nodeIds: new Set(), edgeIds: new Set() };
  const projected = state.supportPaths.find((path) => (path.node_ids ?? []).includes(selectedId));
  if (projected) return {
    nodeIds: new Set((projected.node_ids ?? []).filter((id) => state.nodes.has(id))),
    edgeIds: new Set((projected.edge_ids ?? []).filter((id) => state.edges.has(id))),
  };
  const nodeIds = new Set([selectedId]);
  const edgeIds = new Set();
  const queue = [selectedId];
  while (queue.length) {
    const source = queue.shift();
    for (const edge of state.edges.values()) {
      if (!SUPPORT_CLASSES.has(edge.relationshipClass) || !SUPPORT_KINDS.has(edge.kind) || edge.supportPath !== true || edge.supportDirection !== "source_to_target" || edge.source !== source) continue;
      edgeIds.add(edge.id);
      if (!nodeIds.has(edge.target)) { nodeIds.add(edge.target); queue.push(edge.target); }
    }
  }
  return { nodeIds, edgeIds };
}

export function relationshipReceipt(state, edgeId) {
  const edge = state.edges.get(edgeId);
  const source = edge && state.nodes.get(edge.source);
  const target = edge && state.nodes.get(edge.target);
  if (!edge || !source || !target) return null;
  return {
    source: source.label,
    target: target.label,
    kind: edge.kind,
    relationshipClass: edge.relationshipClass ?? "not established",
    supportPath: edge.supportPath,
    runId: edge.runId,
    sequence: edge.sequence,
    eventId: edge.eventId,
    sourceRef: edge.sourceRef,
    digest: edge.digest,
  };
}

export function storyNodeIds(state, currentId, selectedId = null, focusedFact = null) {
  const ids = new Set();
  if (focusedFact) {
    for (const id of focusedFact.nodeIds ?? []) if (state.nodes.has(id)) ids.add(id);
    for (const id of focusedFact.edgeIds ?? []) {
      const edge = state.edges.get(id);
      if (edge) { ids.add(edge.source); ids.add(edge.target); }
    }
  }
  const attention = attentionFact(state);
  const outcome = reviewBriefFacts(state).outcome.find((fact) => fact.status === "established");
  const roots = focusedFact ? [] : attention.status === "pending" ? attention.nodeIds : outcome?.nodeIds ?? [currentId];
  for (const id of [...roots, selectedId]) if (id && state.nodes.has(id)) {
    ids.add(id);
    for (const supportId of verifiedSupportPath(state, id).nodeIds) ids.add(supportId);
  }
  if (!ids.size && currentId && state.nodes.has(currentId)) ids.add(currentId);
  return ids;
}

export function projectionCounts(state, view, enabledGroups, storyIds = null) {
  const omitted = count(state.totalCounts.omitted_nodes, Object.values(state.omittedCounts).reduce((sum, value) => sum + count(value, 0), 0));
  const serverCollapsed = count(state.totalCounts.collapsed_nodes, Object.values(state.collapsedCounts).reduce((sum, value) => sum + count(value, 0), 0));
  const filtered = [...state.nodes.values()].filter((node) => !enabledGroups.has(node.group)).length;
  const clientCollapsed = storyIds ? [...state.nodes.values()].filter((node) => enabledGroups.has(node.group) && !storyIds.has(node.id)).length : 0;
  return {
    total: count(state.totalCounts.total_nodes, state.nodes.size + omitted + serverCollapsed),
    visible: view.nodes.length,
    filtered,
    collapsed: serverCollapsed + clientCollapsed,
    omitted,
    totalEdges: count(state.totalCounts.total_edges, state.edges.size),
    visibleEdges: view.edges.length,
  };
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

export function visibleGraph(state, enabledGroups, allowedIds = null) {
  const nodes = [...state.nodes.values()].filter((node) => enabledGroups.has(node.group) && (!allowedIds || allowedIds.has(node.id)));
  const ids = new Set(nodes.map((node) => node.id));
  return { nodes, edges: [...state.edges.values()].filter((edge) => ids.has(edge.source) && ids.has(edge.target)) };
}

export function statePositions(state, previous = new Map(), organize = false) {
  return deterministicPositions([...state.nodes.values()], [...state.edges.values()], previous, organize);
}
