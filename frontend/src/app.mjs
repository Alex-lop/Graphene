import {
  MAX_EDGES,
  MAX_NODES,
  NODE_HEIGHT,
  NODE_KINDS,
  NODE_WIDTH,
  edgeGeometry,
  filterGraph,
  layoutGraph,
  proofRows,
  validateGraphResponse,
  validateNodeDetail,
} from "./graph.mjs";
import {
  EXACT_CORRECTION,
  GoldenDemo,
  SCOPE_OPTIONS,
  TASKS,
} from "./workflow.mjs";

const SVG_NS = "http://www.w3.org/2000/svg";
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
let readToken = "";

const DETAIL_FIELDS = Object.freeze({
  agent_run: [
    "agent_profile_id", "task_id", "base_sha", "allowed_paths", "allowed_tools",
    "session_id", "fresh_session", "model_id",
  ],
  changeset: [
    "candidate_revision", "base_commit_sha", "candidate_patch_sha256",
    "candidate_tree_sha256", "candidate_tree_hash_version", "changed_file_count", "changed_paths", "lifecycle_state",
  ],
  file: ["path", "before_sha256", "after_sha256", "language"],
  hunk: [
    "path", "old_start", "old_lines", "new_start", "new_lines", "before_sha256",
    "after_sha256", "candidate_patch_sha256", "exact_hunk_sha256", "candidate_revision",
  ],
  feedback: [
    "feedback_id", "evidence_event_id", "exact_correction", "correction_sha256", "selected_hunk_id",
    "selected_scope_id",
  ],
  memory_revision: [
    "memory_id", "revision", "exact_text", "approval_state", "repo_id", "path_globs",
    "task_tags", "supersession_state",
  ],
  context_packet: [
    "packet_id", "consumer_run_id", "consumer_agent_profile_id", "task_id", "repo_id",
    "base_sha", "allowed_paths", "allowed_tools", "approved_memories", "related_files",
    "required_test_profile", "source_graph_revision", "source_graph_hash",
    "selected_node_ids", "decision", "packet_sha256",
  ],
  policy_check: [
    "policy_revision", "decision", "reason_codes", "candidate_patch_sha256",
    "context_packet_sha256", "test_receipt_sha256",
  ],
  test_receipt: [
    "required_test_profile", "command", "candidate_exit_code",
    "base_with_new_test_exit_code", "timed_out", "output_sha256", "output_truncated",
    "base_commit_sha", "candidate_patch_sha256", "receipt_sha256",
  ],
  human_decision: ["decision_id", "actor", "purpose", "decision", "bound_digest", "occurred_at"],
  promotion_receipt: [
    "base_commit_sha", "candidate_patch_sha256", "candidate_tree_sha256", "candidate_tree_hash_version", "memory_id",
    "memory_revision", "context_packet_id", "context_packet_sha256", "source_graph_revision",
    "source_graph_hash", "selected_node_ids", "test_receipt_sha256", "human_decision_id",
    "commit_sha", "commit_metadata",
  ],
});

const PROFILE_FIELDS = [
  "agent_profile_id", "owner_team", "purpose", "model_policy", "framework", "repo_ids",
  "allowed_paths", "allowed_tools", "memory_access", "data_classification", "policy_revision",
  "status",
];

const elements = {
  tokenForm: document.querySelector("#token-form"),
  tokenInput: document.querySelector("#demo-token"),
  tokenState: document.querySelector("#token-state"),
  forgetToken: document.querySelector("#forget-token"),
  workflowState: document.querySelector("#workflow-state"),
  showBaseline: document.querySelector("#show-baseline"),
  showAdapted: document.querySelector("#show-adapted"),
  baselineOutcome: document.querySelector("#baseline-outcome"),
  baselineProof: document.querySelector("#baseline-proof"),
  memoryOutcome: document.querySelector("#memory-outcome"),
  memoryProof: document.querySelector("#memory-proof"),
  adaptedOutcome: document.querySelector("#adapted-outcome"),
  adaptedProof: document.querySelector("#adapted-proof"),
  resetDemo: document.querySelector("#reset-demo"),
  runBaseline: document.querySelector("#run-baseline"),
  exactCorrection: document.querySelector("#exact-correction"),
  scopeChoice: document.querySelector("#scope-choice"),
  submitFeedback: document.querySelector("#submit-feedback"),
  approveMemory: document.querySelector("#approve-memory"),
  runAdapted: document.querySelector("#run-adapted"),
  promoteRun: document.querySelector("#promote-run"),
  runId: document.querySelector("#run-id"),
  revision: document.querySelector("#graph-revision"),
  graphHash: document.querySelector("#graph-hash"),
  globalState: document.querySelector("#global-state"),
  deniedState: document.querySelector("#denied-state"),
  filterFields: document.querySelector("#filter-fields"),
  currentRun: document.querySelector("#current-run-filter"),
  path: document.querySelector("#path-filter"),
  kind: document.querySelector("#kind-filter"),
  origin: document.querySelector("#origin-filter"),
  clearFilters: document.querySelector("#clear-filters"),
  refresh: document.querySelector("#refresh-graph"),
  boundedCount: document.querySelector("#bounded-count"),
  truncation: document.querySelector("#truncation-notice"),
  graphEmpty: document.querySelector("#graph-empty"),
  graphEmptyMessage: document.querySelector("#graph-empty-message"),
  graphScroll: document.querySelector("#graph-scroll"),
  graph: document.querySelector("#graph"),
  proofList: document.querySelector("#proof-list"),
  proofCount: document.querySelector("#proof-count"),
  proofEmpty: document.querySelector("#proof-empty"),
  drawer: document.querySelector("#evidence-drawer"),
  drawerKind: document.querySelector("#drawer-kind"),
  drawerTitle: document.querySelector("#drawer-title"),
  drawerState: document.querySelector("#drawer-state"),
  drawerContent: document.querySelector("#drawer-content"),
  closeDrawer: document.querySelector("#close-drawer"),
};

const state = {
  runId: null,
  api: null,
  graph: null,
  view: null,
  contextPacket: null,
  contextError: null,
  catalog: [],
  catalogError: null,
  selectedId: null,
  detailCache: new Map(),
  loadToken: 0,
  detailToken: 0,
};

const demo = new GoldenDemo({
  mutate: mutateJson,
  onChange: renderWorkflow,
});

function clear(element) {
  while (element.firstChild) element.removeChild(element.firstChild);
}

function html(tag, className = "", text = null) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== null) element.textContent = String(text);
  return element;
}

function svg(tag, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value));
  return element;
}

function humanize(value) {
  return String(value ?? "").replaceAll("_", " ").replaceAll("-", " ");
}

function short(value, limit) {
  const text = String(value ?? "");
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function toneForStatus(status) {
  const value = String(status).toLowerCase();
  if (["approved", "allowed", "completed", "exact", "modified", "created", "passed", "promoted", "active"].includes(value)) return "success";
  if (["denied", "denied_out_of_scope", "failed", "rejected"].includes(value)) return "danger";
  if (["pending", "queued", "running", "waiting_for_promotion", "promoting", "proposed"].includes(value)) return "warn";
  return "neutral";
}

function provenanceLabel(provenance) {
  return {
    server_observed: "observed",
    server_derived: "derived",
    human_attested: "human",
    model_proposed: "proposed",
  }[provenance] ?? provenance;
}

function provenanceTone(provenance) {
  return {
    server_observed: "observed",
    server_derived: "derived",
    human_attested: "human",
  }[provenance] ?? "neutral";
}

function setGlobal(message, tone = "neutral") {
  elements.globalState.textContent = message;
  elements.globalState.dataset.tone = tone;
}

async function fetchJson(url) {
  const response = await fetch(url, {
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${readToken}`,
    },
  });
  if (!response.ok) throw new Error(`Read endpoint returned HTTP ${response.status}`);
  try {
    return await response.json();
  } catch {
    throw new Error("Read endpoint returned invalid JSON");
  }
}

async function mutateJson(path, payload, token) {
  const response = await fetch(path, {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = `: ${body.detail.slice(0, 240)}`;
    } catch {
      // Status is sufficient when the server does not return JSON.
    }
    throw new Error(`Demo action returned HTTP ${response.status}${detail}`);
  }
  try {
    return await response.json();
  } catch {
    throw new Error("Demo action returned invalid JSON");
  }
}

function listRuns() {
  return fetchJson("/api/runs");
}

function createApi(runId) {
  const runPath = `/api/runs/${encodeURIComponent(runId)}`;
  return {
    graph: () => fetchJson(`${runPath}/graph`),
    node: (nodeId) => fetchJson(`${runPath}/graph/nodes/${encodeURIComponent(nodeId)}`),
    contextPacket: () => fetchJson(`${runPath}/context-packet`),
    catalog: () => fetchJson("/api/agent-catalog"),
  };
}

function validateContextPacket(packet) {
  if (!packet || typeof packet !== "object" || Array.isArray(packet)) throw new TypeError("context packet must be an object");
  if (typeof packet.packet_id !== "string" || !IDENTIFIER.test(packet.packet_id)) throw new TypeError("context packet has an invalid id");
  if (!Array.isArray(packet.approved_memories) || !Array.isArray(packet.related_files)) throw new TypeError("context packet lists are invalid");
  if (!Array.isArray(packet.allowed_paths) || !Array.isArray(packet.allowed_tools)) throw new TypeError("context permissions are invalid");
  if (!["allowed", "denied_out_of_scope"].includes(packet.decision)) throw new TypeError("context packet decision is invalid");
  return packet;
}

function validateCatalog(catalog) {
  if (!Array.isArray(catalog)) throw new TypeError("runtime catalog must be an array");
  for (const profile of catalog) {
    if (!profile || typeof profile !== "object" || typeof profile.agent_profile_id !== "string") throw new TypeError("runtime catalog profile is invalid");
    if (!Array.isArray(profile.allowed_paths) || !Array.isArray(profile.allowed_tools)) throw new TypeError("runtime catalog scope is invalid");
  }
  return catalog;
}

function currentFilters() {
  return {
    runId: state.runId,
    currentRunOnly: elements.currentRun.checked,
    pathPrefix: elements.path.value,
    kind: elements.kind.value,
    showMemoryOrigin: elements.origin.checked,
  };
}

function baselineHunkId() {
  const baseline = demo.snapshot.baseline;
  if (!baseline || state.runId !== baseline.run_id) return null;
  return state.graph?.nodes.find(
    (node) => node.kind === "hunk" && node.run_id === baseline.run_id,
  )?.id ?? null;
}

function runProof(run) {
  if (!run) return "No server evidence yet";
  const candidate = run.candidate;
  if (!candidate) return `Revision ${run.revision}`;
  const exit = candidate.test_receipt?.candidate_exit_code;
  return `${candidate.changed_paths.length} changed file${candidate.changed_paths.length === 1 ? "" : "s"} · test exit ${exit}`;
}

function workflowInstruction(snapshot) {
  if (!snapshot.hasToken) return "Enter the runtime demo token to begin.";
  if (!snapshot.baseline) return "Ready to reset or run the recorded baseline task.";
  if (snapshot.baseline.state === "queued") return "Baseline is queued and can be resumed.";
  if (!snapshot.memory) return baselineHunkId()
    ? "Select the server-owned scope, then submit the exact anchored correction."
    : "Open the baseline run so its exact hunk can anchor feedback.";
  if (snapshot.memory.state === "proposed") return "Memory revision 1 is proposed and awaits explicit compatibility approval.";
  if (!snapshot.adapted) return "Approved memory is ready for a fresh compatibility fixture run.";
  if (snapshot.adapted.state === "queued") return "The fresh adapted run is queued and can be resumed.";
  if (snapshot.adapted.state === "waiting_for_promotion") return "Tests passed, completion was denied, and the bound candidate awaits explicit compatibility promotion.";
  if (snapshot.adapted.state === "completed") return "Golden loop complete: the exact bound candidate was promoted.";
  return `Adapted run status: ${humanize(snapshot.adapted.state)}.`;
}

function renderWorkflow(snapshot = demo.snapshot) {
  const controls = demo.controls(baselineHunkId());
  elements.tokenState.textContent = snapshot.hasToken ? "Held only in this page's JS memory" : "Not held";
  elements.forgetToken.disabled = !snapshot.hasToken;
  elements.workflowState.textContent = snapshot.error
    ? snapshot.error
    : snapshot.busy
      ? `${humanize(snapshot.busy)} in progress…`
      : workflowInstruction(snapshot);
  elements.workflowState.dataset.tone = snapshot.error ? "error" : snapshot.busy ? "busy" : "neutral";

  elements.resetDemo.disabled = !controls.reset;
  elements.runBaseline.disabled = !controls.baseline;
  elements.submitFeedback.disabled = !controls.feedback;
  elements.scopeChoice.disabled = !controls.feedback;
  elements.approveMemory.disabled = !controls.approveMemory;
  elements.runAdapted.disabled = !controls.adapted;
  elements.promoteRun.disabled = !controls.promote;
  elements.showBaseline.disabled = !controls.switchBaseline;
  elements.showAdapted.disabled = !controls.switchAdapted;
  elements.showBaseline.setAttribute("aria-pressed", snapshot.activeTask === TASKS.baseline ? "true" : "false");
  elements.showAdapted.setAttribute("aria-pressed", snapshot.activeTask === TASKS.adapted ? "true" : "false");
  elements.runBaseline.textContent = snapshot.baseline?.state === "queued" ? "Resume baseline" : "Run baseline";
  elements.runAdapted.textContent = snapshot.adapted?.state === "queued" ? "Resume fresh fixture" : "Run fresh fixture";

  elements.baselineOutcome.textContent = snapshot.baseline ? humanize(snapshot.baseline.state) : "Not created";
  elements.baselineProof.textContent = runProof(snapshot.baseline);
  elements.memoryOutcome.textContent = snapshot.memory
    ? `${humanize(snapshot.memory.state)} · revision ${snapshot.memory.revision}`
    : "Not proposed";
  elements.memoryProof.textContent = snapshot.memory?.path_globs?.length
    ? snapshot.memory.path_globs.join(", ")
    : "Explicit compatibility approval required";
  elements.adaptedOutcome.textContent = snapshot.adapted ? humanize(snapshot.adapted.state) : "Not created";
  elements.adaptedProof.textContent = snapshot.adapted
    ? `${runProof(snapshot.adapted)} · ${snapshot.adapted.injected_memories?.length ?? 0} injected memory`
    : "No context injected yet";
}

function hydrateMemoryFromGraph(graph) {
  const node = graph.nodes.find((item) => item.kind === "memory_revision");
  if (!node) return;
  demo.hydrateMemory({
    memory_id: node.data.memory_id,
    revision: node.data.revision,
    state: node.data.approval_state,
    rule: node.data.exact_text,
    path_globs: node.data.path_globs,
    task_tags: node.data.task_tags,
  });
}

function renderTruncation() {
  if (!state.graph?.truncated) {
    elements.truncation.hidden = true;
    elements.truncation.textContent = "";
    return;
  }
  const counts = Object.entries(state.graph.omitted_counts)
    .filter(([, count]) => count > 0)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, count]) => `${count} ${humanize(key)} omitted`);
  elements.truncation.textContent = `Truncated bounded view: ${counts.join(" · ")}`;
  elements.truncation.hidden = false;
}

function renderDeniedState() {
  const deniedPolicies = state.graph?.nodes.filter(
    (node) => node.kind === "policy_check" && (node.status === "denied" || node.data.decision === "denied"),
  ) ?? [];
  const contextDenied = state.contextPacket?.decision === "denied_out_of_scope";
  const messages = [];
  if (contextDenied) {
    messages.push(
      `Context denied out of scope: ${state.contextPacket.approved_memories.length} memories, ` +
      `${state.contextPacket.related_files.length} related files, and no disclosed permissions.`,
    );
  }
  if (deniedPolicies.length) messages.push(`${deniedPolicies.length} fail-closed policy denial${deniedPolicies.length === 1 ? "" : "s"} recorded for this evidence graph.`);
  elements.deniedState.textContent = messages.join(" ");
  elements.deniedState.hidden = messages.length === 0;
}

function edgeClass(edge) {
  if (edge.advisory) return "edge--advisory";
  if (edge.kind === "DENIED") return "edge--denied";
  if (edge.kind === "ALLOWED") return "edge--allowed";
  if (edge.kind === "VALIDATED") return "edge--validated";
  if (edge.kind === "PROMOTED_AS") return "edge--promoted";
  return "";
}

function marker(defs, id, color) {
  const element = svg("marker", {
    id,
    viewBox: "0 0 10 10",
    refX: 9,
    refY: 5,
    markerWidth: 7,
    markerHeight: 7,
    orient: "auto-start-reverse",
  });
  const path = svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: color });
  element.append(path);
  defs.append(element);
}

function addBadge(group, label, x, tone) {
  const visible = short(humanize(label), 13);
  const width = Math.max(42, Math.min(92, 16 + visible.length * 5.4));
  const badge = svg("g", { class: `node-badge badge--${tone}`, transform: `translate(${x} 27)` });
  badge.append(svg("rect", { x: 0, y: 0, width, height: 20, rx: 10 }));
  const text = svg("text", { x: width / 2, y: 13.5 });
  text.textContent = visible;
  badge.append(text);
  group.append(badge);
  return width;
}

function renderSvg(view) {
  clear(elements.graph);
  const description = svg("desc", { id: "graph-description" });
  description.textContent = "Directional graph of API-provided evidence. Use Tab to reach nodes and Enter to open exact evidence.";
  elements.graph.append(description);

  const layout = layoutGraph(view, { runId: state.runId, selectedId: state.selectedId });
  elements.graph.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
  elements.graph.style.aspectRatio = `${layout.width} / ${layout.height}`;

  const defs = svg("defs");
  marker(defs, "arrow", "#55727d");
  marker(defs, "arrow-danger", "#ff7185");
  marker(defs, "arrow-success", "#62e09e");
  marker(defs, "arrow-advisory", "#60717a");
  elements.graph.append(defs);

  for (const edge of view.edges) {
    const source = layout.positions[edge.source];
    const target = layout.positions[edge.target];
    const geometry = edgeGeometry(source, target);
    const group = svg("g", { "data-edge-id": edge.id });
    const className = edgeClass(edge);
    const markerId = edge.advisory
      ? "arrow-advisory"
      : edge.kind === "DENIED"
        ? "arrow-danger"
        : ["ALLOWED", "VALIDATED", "PROMOTED_AS"].includes(edge.kind)
          ? "arrow-success"
          : "arrow";
    group.append(svg("line", {
      ...geometry,
      class: `edge-line ${className}`.trim(),
      "marker-end": `url(#${markerId})`,
    }));
    const label = svg("text", {
      class: "edge-label",
      x: (geometry.x1 + geometry.x2) / 2,
      y: (geometry.y1 + geometry.y2) / 2 - 7,
    });
    label.textContent = edge.advisory ? `${edge.kind} · advisory` : edge.kind;
    group.append(label);
    elements.graph.append(group);
  }

  for (const node of view.nodes) {
    const position = layout.positions[node.id];
    const group = svg("g", {
      class: [
        "node",
        `node--${node.kind}`,
        node.id === layout.focusId ? "node--focus" : "",
        node.id === state.selectedId ? "node--selected" : "",
      ].filter(Boolean).join(" "),
      transform: `translate(${position.x} ${position.y})`,
      tabindex: 0,
      role: "button",
      "aria-pressed": node.id === state.selectedId ? "true" : "false",
      "aria-label": `${humanize(node.kind)}: ${node.label}. Status ${humanize(node.status)}. Provenance ${humanize(node.provenance)}.`,
      "data-node-id": node.id,
    });
    const title = svg("title");
    title.textContent = `${node.label} · ${humanize(node.status)} · ${humanize(node.provenance)}`;
    group.append(title);
    group.append(svg("rect", {
      class: "node-shell",
      x: -NODE_WIDTH / 2,
      y: -NODE_HEIGHT / 2,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      rx: 26,
    }));
    const kind = svg("text", { class: "node-kind", x: -88, y: -24 });
    kind.textContent = humanize(node.kind).toUpperCase();
    group.append(kind);
    const label = svg("text", { class: "node-label", x: -88, y: 2 });
    label.textContent = short(node.label, 29);
    group.append(label);

    const statusWidth = Math.max(42, Math.min(92, 16 + short(humanize(node.status), 13).length * 5.4));
    const provenanceWidth = Math.max(42, Math.min(92, 16 + provenanceLabel(node.provenance).length * 5.4));
    const start = -(statusWidth + provenanceWidth + 7) / 2;
    addBadge(group, node.status, start, toneForStatus(node.status));
    addBadge(group, provenanceLabel(node.provenance), start + statusWidth + 7, provenanceTone(node.provenance));

    group.addEventListener("click", () => openNode(node));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openNode(node);
      }
    });
    elements.graph.append(group);
  }
  return layout;
}

function renderProofList(view) {
  clear(elements.proofList);
  const rows = proofRows(view);
  elements.proofCount.textContent = `${rows.length} API relationship${rows.length === 1 ? "" : "s"}`;
  elements.proofEmpty.hidden = rows.length !== 0;
  for (const row of rows) {
    const item = html("li");
    item.dataset.edgeId = row.edgeId;
    const button = html("button");
    button.type = "button";
    button.setAttribute("aria-label", `Open target evidence. ${row.text}`);
    button.append(html("span", "proof-list__relationship", row.text));
    const advisory = row.advisory ? " · advisory" : "";
    const meta = html(
      "span",
      `proof-list__meta${row.advisory ? " proof-list__advisory" : ""}`,
      `${humanize(row.provenance)}${advisory} · ${row.sourceRef} · ${row.digest}`,
    );
    button.append(meta);
    button.addEventListener("click", () => {
      const target = view.nodes.find((node) => node.id === row.targetId);
      if (target) openNode(target);
    });
    item.append(button);
    elements.proofList.append(item);
  }
}

function renderView() {
  if (!state.graph) return;
  const view = filterGraph(state.graph, currentFilters());
  state.view = view;
  elements.boundedCount.textContent =
    `Showing ${view.nodes.length} of ${state.graph.nodes.length} returned nodes (${MAX_NODES} max) · ` +
    `${view.edges.length} of ${state.graph.edges.length} returned edges (${MAX_EDGES} max)`;
  renderTruncation();
  renderDeniedState();
  renderProofList(view);

  if (view.nodes.length === 0) {
    elements.graphScroll.hidden = true;
    elements.graphEmpty.hidden = false;
    elements.graphEmptyMessage.textContent = state.graph.nodes.length === 0
      ? "The API returned a valid empty graph for this run."
      : "No nodes match the current filters. Clear a filter to restore evidence.";
    if (state.selectedId) closeDrawer(false);
    return null;
  }

  elements.graphEmpty.hidden = true;
  elements.graphScroll.hidden = false;
  const layout = renderSvg(view);
  if (state.selectedId && !view.nodes.some((node) => node.id === state.selectedId)) closeDrawer(false);
  return layout;
}

function appendValue(parent, value, key = "") {
  if (value === null || value === undefined) {
    parent.append(html("span", "", "Not recorded"));
    return;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      parent.append(html("span", "", "None"));
      return;
    }
    const list = html("ul");
    for (const item of value) {
      const entry = html("li");
      appendValue(entry, item, key);
      list.append(entry);
    }
    parent.append(list);
    return;
  }
  if (typeof value === "object") {
    const list = html("dl", "nested-evidence");
    for (const [nestedKey, nestedValue] of Object.entries(value).sort(([left], [right]) => left.localeCompare(right))) {
      list.append(html("dt", "", humanize(nestedKey)));
      const definition = html("dd");
      appendValue(definition, nestedValue, nestedKey);
      list.append(definition);
    }
    parent.append(list);
    return;
  }
  const text = typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
  const codeLike = /(sha|hash|digest|_id$|source_ref|commit|path|command)/.test(key);
  parent.append(html(codeLike ? "code" : "span", "", text));
}

function evidenceSection(title, entries) {
  const section = html("section", "evidence-section");
  section.append(html("h3", "", title));
  const list = html("dl", "evidence-list");
  for (const [key, value] of entries) {
    list.append(html("dt", "", humanize(key)));
    const definition = html("dd");
    appendValue(definition, value, key);
    list.append(definition);
  }
  section.append(list);
  return section;
}

function commonEntries(node) {
  return [
    ["node_id", node.id],
    ["kind", node.kind],
    ["status", node.status],
    ["provenance", node.provenance],
    ["repository", node.repo_id],
    ["run_id", node.run_id],
    ["source_ref", node.source_ref],
    ["digest", node.digest],
    ["created_at", node.created_at],
  ];
}

function renderDrawerDetail(detail) {
  clear(elements.drawerContent);
  elements.drawerContent.append(evidenceSection("Evidence envelope", commonEntries(detail)));

  let data = detail.data;
  let title = `${humanize(detail.kind)} evidence`;
  if (
    detail.kind === "context_packet" &&
    state.contextPacket?.packet_id === detail.data.packet_id
  ) {
    data = state.contextPacket;
    title = "Context packet endpoint";
  }
  const fields = DETAIL_FIELDS[detail.kind] ?? [];
  elements.drawerContent.append(
    evidenceSection(title, fields.filter((field) => field !== "unified_diff").map((field) => [field, data[field]])),
  );

  if (detail.kind === "agent_run") {
    const profile = state.catalog.find(
      (item) => item.agent_profile_id === detail.data.agent_profile_id,
    );
    if (profile) {
      elements.drawerContent.append(
        evidenceSection("Server-owned runtime catalog", PROFILE_FIELDS.map((field) => [field, profile[field]])),
      );
    } else if (state.catalogError) {
      elements.drawerContent.append(html("p", "evidence-warning", `Runtime catalog unavailable: ${state.catalogError.message}`));
    }
  }

  if (detail.kind === "context_packet" && state.contextError) {
    elements.drawerContent.append(html("p", "evidence-warning", `Context packet endpoint unavailable: ${state.contextError.message}`));
  }

  if (detail.kind === "hunk") {
    const section = html("section", "evidence-section");
    const heading = html("div", "diff-heading");
    heading.append(html("h3", "", "Exact unified diff"));
    heading.append(html("code", "", detail.data.exact_hunk_sha256));
    section.append(heading);
    const pre = html("pre", "exact-diff");
    const code = html("code");
    code.textContent = detail.data.unified_diff;
    pre.append(code);
    section.append(pre);
    elements.drawerContent.append(section);
  }
}

async function loadDetail(node) {
  if (state.detailCache.has(node.id)) return state.detailCache.get(node.id);
  const detail = validateNodeDetail(await state.api.node(node.id), node);
  state.detailCache.set(node.id, detail);
  return detail;
}

async function preloadDetail(node) {
  try {
    await loadDetail(node);
  } catch {
    // A visible drawer request retries and presents the read error.
  }
}

async function openNode(node) {
  state.selectedId = node.id;
  renderView();
  elements.drawer.hidden = false;
  elements.drawerKind.textContent = humanize(node.kind);
  elements.drawerTitle.textContent = node.label;
  elements.drawerState.textContent = "Loading authoritative node detail…";
  elements.drawerState.dataset.tone = "neutral";
  clear(elements.drawerContent);
  elements.closeDrawer.focus();
  const token = ++state.detailToken;
  try {
    const detail = await loadDetail(node);
    if (token !== state.detailToken || state.selectedId !== node.id) return;
    elements.drawerState.textContent = "Detail digest matches the graph response.";
    elements.drawerState.dataset.tone = "success";
    renderDrawerDetail(detail);
  } catch (error) {
    if (token !== state.detailToken || state.selectedId !== node.id) return;
    elements.drawerState.textContent = `Could not load exact evidence: ${error.message}`;
    elements.drawerState.dataset.tone = "error";
    elements.drawerContent.append(evidenceSection("Graph summary", commonEntries(node)));
  }
}

function closeDrawer(restoreFocus = true) {
  const selectedId = state.selectedId;
  state.detailToken += 1;
  state.selectedId = null;
  elements.drawer.hidden = true;
  if (state.graph) renderView();
  if (restoreFocus && selectedId) {
    const target = [...elements.graph.querySelectorAll(".node")]
      .find((node) => node.dataset.nodeId === selectedId);
    target?.focus();
  }
}

async function loadGraph() {
  const token = ++state.loadToken;
  state.graph = null;
  state.view = null;
  state.contextPacket = null;
  state.contextError = null;
  state.catalog = [];
  state.catalogError = null;
  state.detailCache.clear();
  renderWorkflow();
  closeDrawer(false);
  elements.filterFields.disabled = true;
  elements.graphScroll.hidden = true;
  elements.graphEmpty.hidden = false;
  elements.graphEmptyMessage.textContent = "Loading the bounded evidence projection…";
  clear(elements.proofList);
  elements.proofEmpty.hidden = false;
  setGlobal("Loading graph, context packet, and server-owned runtime catalog…");

  const auxiliary = Promise.allSettled([
    state.api.contextPacket(),
    state.api.catalog(),
  ]);

  try {
    const graph = validateGraphResponse(await state.api.graph());
    if (token !== state.loadToken) return;
    state.graph = graph;
    hydrateMemoryFromGraph(graph);
    renderWorkflow();
    elements.revision.textContent = String(graph.revision);
    elements.graphHash.textContent = graph.graph_hash;
    elements.filterFields.disabled = false;
    const layout = renderView();
    const preloadId = layout?.focusId ?? graph.nodes[0]?.id;
    const preload = graph.nodes.find((node) => node.id === preloadId);
    if (preload) void preloadDetail(preload);
  } catch (error) {
    await auxiliary;
    if (token !== state.loadToken) return;
    elements.filterFields.disabled = false;
    elements.graphEmpty.hidden = false;
    elements.graphEmptyMessage.textContent = "The graph read failed. No fixture or cached response was substituted.";
    elements.boundedCount.textContent = `Bounded response: 0 / ${MAX_NODES} nodes · 0 / ${MAX_EDGES} edges`;
    setGlobal(`Graph unavailable: ${error.message}. Use Refresh proof to retry.`, "error");
    renderWorkflow();
    return;
  }

  const [contextResult, catalogResult] = await auxiliary;
  if (token !== state.loadToken) return;
  if (contextResult.status === "fulfilled") {
    try {
      state.contextPacket = validateContextPacket(contextResult.value);
    } catch (error) {
      state.contextError = error;
    }
  } else {
    state.contextError = contextResult.reason;
  }
  if (catalogResult.status === "fulfilled") {
    try {
      state.catalog = validateCatalog(catalogResult.value);
    } catch (error) {
      state.catalogError = error;
    }
  } else {
    state.catalogError = catalogResult.reason;
  }
  renderDeniedState();
  if (state.selectedId && state.detailCache.has(state.selectedId)) {
    renderDrawerDetail(state.detailCache.get(state.selectedId));
  }
  const warnings = [state.contextError && "context packet", state.catalogError && "runtime catalog"].filter(Boolean);
  setGlobal(
    warnings.length
      ? `Graph loaded. Auxiliary read unavailable: ${warnings.join(" and ")}. Node relationships remain API-only.`
      : `Loaded ${state.graph.nodes.length} nodes and ${state.graph.edges.length} API relationships.`,
    warnings.length ? "neutral" : "success",
  );
}

function resetFilters() {
  elements.currentRun.checked = false;
  elements.path.value = "";
  elements.kind.value = "";
  elements.origin.checked = true;
  renderView();
}

function clearActiveRun(message = "No run selected. Start the baseline to create server evidence.") {
  state.loadToken += 1;
  state.graph = null;
  state.view = null;
  state.runId = null;
  state.api = null;
  state.contextPacket = null;
  state.catalog = [];
  state.detailCache.clear();
  closeDrawer(false);
  elements.runId.textContent = "Not selected";
  elements.revision.textContent = "—";
  elements.graphHash.textContent = "—";
  elements.filterFields.disabled = true;
  elements.graphScroll.hidden = true;
  elements.graphEmpty.hidden = false;
  elements.graphEmptyMessage.textContent = message;
  elements.boundedCount.textContent = `Bounded response: 0 / ${MAX_NODES} nodes · 0 / ${MAX_EDGES} edges`;
  elements.truncation.hidden = true;
  elements.deniedState.hidden = true;
  clear(elements.proofList);
  elements.proofEmpty.hidden = false;
  elements.proofCount.textContent = "0 API relationships";
  setGlobal(message);
  renderWorkflow();
}

async function activateRun(runId, taskId = null) {
  if (!IDENTIFIER.test(runId)) throw new TypeError("Server returned an invalid run ID");
  state.runId = runId;
  state.api = createApi(runId);
  elements.runId.textContent = runId;
  if (taskId) demo.setActiveTask(taskId);
  const url = new URL(window.location.href);
  url.searchParams.set("run_id", runId);
  history.replaceState(null, "", url);
  await loadGraph();
}

async function runAction(action, after) {
  try {
    const result = await action();
    if (after) await after(result);
  } catch {
    // GoldenDemo exposes the bounded server error through its live state.
  }
}

async function initialize() {
  renderWorkflow();
  const requestedRunId = new URLSearchParams(window.location.search).get("run_id");
  if (requestedRunId && !IDENTIFIER.test(requestedRunId)) {
    clearActiveRun("The supplied run ID is not a valid server identifier.");
    setGlobal("Invalid run_id. No run-specific API request was sent.", "error");
    return;
  }

  let runs = [];
  try {
    const response = await listRuns();
    if (!Array.isArray(response)) throw new TypeError("Run list is invalid");
    runs = response;
    demo.hydrateRuns(runs);
  } catch (error) {
    setGlobal(`Could not list existing runs: ${error.message}`, "error");
  }

  if (requestedRunId) {
    const known = runs.find((run) => run.run_id === requestedRunId);
    await activateRun(requestedRunId, known?.task_id ?? null);
    return;
  }
  const known = demo.snapshot.adapted ?? demo.snapshot.baseline;
  if (known) {
    await activateRun(known.run_id, known.task_id);
  } else {
    clearActiveRun();
  }
}

for (const kind of NODE_KINDS) {
  const option = html("option", "", humanize(kind));
  option.value = kind;
  elements.kind.append(option);
}

elements.exactCorrection.textContent = EXACT_CORRECTION;
for (const scope of SCOPE_OPTIONS) {
  const option = html("option", "", scope.label);
  option.value = scope.value;
  elements.scopeChoice.append(option);
}

elements.currentRun.addEventListener("change", renderView);
elements.path.addEventListener("input", renderView);
elements.kind.addEventListener("change", renderView);
elements.origin.addEventListener("change", renderView);
elements.clearFilters.addEventListener("click", resetFilters);
elements.refresh.addEventListener("click", () => {
  if (state.api) void loadGraph();
});
elements.closeDrawer.addEventListener("click", () => closeDrawer());
elements.tokenForm.addEventListener("submit", (event) => {
  event.preventDefault();
  readToken = elements.tokenInput.value;
  demo.setToken(readToken);
  elements.tokenInput.value = "";
  void initialize();
});
elements.forgetToken.addEventListener("click", () => {
  readToken = "";
  demo.clearToken();
});
elements.resetDemo.addEventListener("click", () => runAction(
  () => demo.reset(),
  async () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("run_id");
    history.replaceState(null, "", url);
    clearActiveRun("Demo reset complete. Run the baseline to begin.");
  },
));
elements.runBaseline.addEventListener("click", () => runAction(
  () => demo.runBaseline(),
  (run) => activateRun(run.run_id, run.task_id),
));
elements.submitFeedback.addEventListener("click", () => runAction(
  () => demo.submitFeedback(baselineHunkId(), elements.scopeChoice.value),
  () => loadGraph(),
));
elements.approveMemory.addEventListener("click", () => runAction(
  () => demo.approveMemory(),
  () => loadGraph(),
));
elements.runAdapted.addEventListener("click", () => runAction(
  () => demo.runAdapted(),
  (run) => activateRun(run.run_id, run.task_id),
));
elements.promoteRun.addEventListener("click", () => runAction(
  () => demo.promote(),
  (run) => activateRun(run.run_id, run.task_id),
));
elements.showBaseline.addEventListener("click", () => {
  const run = demo.snapshot.baseline;
  if (run) void activateRun(run.run_id, run.task_id);
});
elements.showAdapted.addEventListener("click", () => {
  const run = demo.snapshot.adapted;
  if (run) void activateRun(run.run_id, run.task_id);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.drawer.hidden) closeDrawer();
});

void initialize();
