export const TASK_STATES = Object.freeze([
  "queued", "ready", "running", "blocked", "retrying", "needs_input",
  "verifying", "done", "failed", "cancelled",
]);

export const RELATIONSHIP_KINDS = Object.freeze([
  "decomposed_into", "depends_on", "assigned_to", "blocked_by", "produced", "accepted_from",
  "verified_by", "inherited",
]);

const taskStates = new Set(TASK_STATES);
const relationshipKinds = new Set(RELATIONSHIP_KINDS);
const record = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
const text = (value) => typeof value === "string" && value.trim() ? value.trim() : null;

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (record(value)) return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]));
  return value;
}

export function canonicalJson(value) { return JSON.stringify(canonicalValue(value)); }
export function snapshotHashPayload(snapshot) {
  const { cursor: _cursor, snapshot_sha256: _digest, ...publicValue } = snapshot;
  return publicValue;
}

function requireRecord(value, label) {
  if (!record(value)) throw new TypeError(`${label} must be an object`);
  return value;
}

function requireText(value, label) {
  const result = text(value);
  if (!result) throw new TypeError(`${label} must be nonempty text`);
  return result;
}


function values(items, key, label) {
  if (!Array.isArray(items)) throw new TypeError(`${label} must be an array`);
  const result = new Map();
  for (const item of items) {
    requireRecord(item, `${label} item`);
    const id = requireText(item[key], `${label} ${key}`);
    if (result.has(id)) throw new TypeError(`${label} contains duplicate ${key}`);
    result.set(id, structuredClone(item));
  }
  return result;
}


function normalizeSnapshot(raw) {
  const snapshot = requireRecord(raw, "mission snapshot");
  if (snapshot.view_version !== 1) throw new TypeError("mission view version is unsupported");
  const mission = requireRecord(snapshot.mission, "mission");
  const missionId = requireText(mission.mission_id, "mission id");
  const head = requireRecord(snapshot.head, "mission head");
  if (head.mission_id !== missionId || !Number.isInteger(head.seq) || head.seq < 1) {
    throw new TypeError("mission head does not match the mission");
  }
  const tasks = values(snapshot.tasks, "task_id", "tasks");
  for (const task of tasks.values()) {
    if (!taskStates.has(task.state)) throw new TypeError(`unknown task state: ${task.state}`);
  }
  const relationships = values(snapshot.relationships, "relationship_id", "relationships");
  const nodeIds = new Set([
    `mission:${missionId}`,
    ...[...tasks.keys()].map((id) => `task:${id}`),
    ...(snapshot.workers ?? []).map((item) => `worker:${item.worker_id}`),
    ...(snapshot.gates ?? []).map((item) => `gate:${item.gate_id}`),
    `integration:${missionId}`,
    `verification:${missionId}`,
    `result:${missionId}`,
  ]);
  for (const relationship of relationships.values()) {
    if (!relationshipKinds.has(relationship.kind)) throw new TypeError(`unknown relationship kind: ${relationship.kind}`);
    if (!nodeIds.has(relationship.source) || !nodeIds.has(relationship.target)) {
      throw new TypeError(`relationship ${relationship.relationship_id} has an unknown endpoint`);
    }
  }
  return {
    viewVersion: 1,
    missionId,
    mission: structuredClone(mission),
    head: structuredClone(head),
    cursor: requireText(snapshot.cursor, "mission cursor"),
    snapshotSha256: requireText(snapshot.snapshot_sha256, "snapshot digest"),
    tasks,
    attempts: values(snapshot.attempts ?? [], "attempt_id", "attempts"),
    workers: values(snapshot.workers ?? [], "worker_id", "workers"),
    gates: values(snapshot.gates ?? [], "gate_id", "gates"),
    publications: values(snapshot.publications ?? [], "publication_id", "publications"),
    relationships,
    integration: structuredClone(snapshot.integration ?? { state: "queued", summary: "Integration has not started." }),
    verification: structuredClone(snapshot.verification ?? { state: "queued", summary: "Verification has not started." }),
    resources: structuredClone(snapshot.resources ?? { status: "unavailable", summary: "Resource receipts are unavailable.", metrics: [] }),
    needsYou: snapshot.needs_you ? structuredClone(snapshot.needs_you) : null,
    criticalPathTaskIds: [...(snapshot.critical_path_task_ids ?? [])],
    result: structuredClone(snapshot.result ?? { state: "pending", summary: "No result is available." }),
    unknowns: [...(snapshot.unknowns ?? [])],
  };
}


export function createState(snapshot) {
  return normalizeSnapshot(snapshot);
}


function patchCollection(collection, patch, key, label) {
  const value = requireRecord(patch, `${label} patch`);
  if (!Array.isArray(value.upsert) || !Array.isArray(value.remove)) {
    throw new TypeError(`${label} patch must contain upsert and remove arrays`);
  }
  for (const id of value.remove) collection.delete(requireText(id, `${label} removal id`));
  for (const item of value.upsert) {
    requireRecord(item, `${label} upsert`);
    collection.set(requireText(item[key], `${label} ${key}`), structuredClone(item));
  }
  const ordered = [...collection.entries()].sort(([left], [right]) => left.localeCompare(right));
  collection.clear();
  for (const [id, item] of ordered) collection.set(id, item);
}


export function applyDelta(state, envelope) {
  const packet = requireRecord(envelope, "mission stream envelope");
  if (packet.type === "reset") return createState(packet.snapshot);
  if (packet.type !== "delta") throw new TypeError("unknown mission stream envelope");
  const delta = requireRecord(packet.delta, "mission delta");
  if (delta.view_version !== 1 || delta.mission_id !== state.missionId) throw new TypeError("mission delta identity is invalid");
  if (delta.to_seq === state.head.seq && delta.snapshot_sha256 === state.snapshotSha256) return state;
  if (delta.from_seq !== state.head.seq || delta.from_head_sha256 !== state.head.event_sha256) {
    throw new TypeError("mission delta does not continue the current head");
  }
  if (!Number.isInteger(delta.to_seq) || delta.to_seq <= delta.from_seq) throw new TypeError("mission delta sequence is invalid");

  const next = structuredClone(state);
  for (const [name, key] of [
    ["tasks", "task_id"], ["attempts", "attempt_id"], ["workers", "worker_id"],
    ["gates", "gate_id"], ["publications", "publication_id"],
    ["relationships", "relationship_id"],
  ]) patchCollection(next[name], delta[name], key, name);
  next.mission = structuredClone(delta.mission);
  next.head = structuredClone(delta.head);
  next.cursor = requireText(delta.cursor, "mission delta cursor");
  next.snapshotSha256 = requireText(delta.snapshot_sha256, "mission delta digest");
  next.integration = structuredClone(delta.integration);
  next.verification = structuredClone(delta.verification);
  next.resources = structuredClone(delta.resources);
  next.needsYou = delta.needs_you ? structuredClone(delta.needs_you) : null;
  next.criticalPathTaskIds = [...delta.critical_path_task_ids];
  next.result = structuredClone(delta.result);
  next.unknowns = [...delta.unknowns];

  return normalizeSnapshot({
    view_version: 1,
    mission: next.mission,
    head: next.head,
    cursor: next.cursor,
    snapshot_sha256: next.snapshotSha256,
    tasks: [...next.tasks.values()],
    attempts: [...next.attempts.values()],
    workers: [...next.workers.values()],
    gates: [...next.gates.values()],
    publications: [...next.publications.values()],
    relationships: [...next.relationships.values()],
    integration: next.integration,
    verification: next.verification,
    resources: next.resources,
    needs_you: next.needsYou,
    critical_path_task_ids: next.criticalPathTaskIds,
    result: next.result,
    unknowns: next.unknowns,
  });
}


export function applyThrough(snapshot, envelopes, count = envelopes.length) {
  let state = createState(snapshot);
  for (const envelope of envelopes.slice(0, count)) state = applyDelta(state, envelope);
  return state;
}


export function stateBuckets(state) {
  return TASK_STATES.map((status) => {
    const tasks = [...state.tasks.values()].filter((task) => task.state === status).sort((left, right) => left.title.localeCompare(right.title) || left.task_id.localeCompare(right.task_id));
    return { status, count: tasks.length, names: tasks.map((task) => task.title), taskIds: tasks.map((task) => task.task_id) };
  });
}


export function taskEvidenceTarget(state, taskId) {
  const attempts = [...state.attempts.values()].filter((attempt) => attempt.task_id === taskId).sort((left, right) => Number(right.number ?? 0) - Number(left.number ?? 0) || right.attempt_id.localeCompare(left.attempt_id));
  const attempt = attempts[0];
  if (!attempt?.evidence) return null;
  if (attempt.evidence.kind === "generic_attempt_v1") return { kind: "generic", attemptId: attempt.attempt_id };
  if (attempt.evidence.kind === "legacy_v2" && text(attempt.evidence.href) && text(attempt.evidence.run_id)) {
    return { kind: "legacy", href: attempt.evidence.href, runId: attempt.evidence.run_id };
  }
  throw new TypeError("attempt evidence discriminator is invalid");
}


export function graphView(state) {
  const nodes = [
    { id: `mission:${state.missionId}`, kind: "goal", label: state.mission.goal, status: state.mission.status },
    ...[...state.tasks.values()].map((task) => ({ id: `task:${task.task_id}`, kind: "task", label: task.title, status: task.state, taskId: task.task_id })),
    ...[...state.workers.values()].map((worker) => ({ id: `worker:${worker.worker_id}`, kind: "worker", label: worker.label, status: worker.status })),
    ...[...state.gates.values()].map((gate) => ({ id: `gate:${gate.gate_id}`, kind: "gate", label: gate.reason, status: gate.status })),
    { id: `integration:${state.missionId}`, kind: "integration", label: "Integration", status: state.integration.state },
    { id: `verification:${state.missionId}`, kind: "verification", label: "Verification", status: state.verification.state },
    { id: `result:${state.missionId}`, kind: "result", label: "Result", status: state.result.state },
  ];
  const edges = [...state.relationships.values()].map((edge) => structuredClone(edge));
  return { nodes, edges };
}
