import cytoscape from "/mission-vendor/cytoscape.esm.min.mjs";
import { applyDelta, applyThrough, canonicalJson, createState, finalDecisionOptions, finalResultBinding, graphPositions, graphView, missionBrief, renderFinalReview, snapshotHashPayload, taskEvidenceTarget, visibleStateBuckets } from "./mission_reducer.mjs";

const $ = (id) => document.getElementById(id);
const bootstrap = window.__GRAPHENE_MISSION_CONTROL__ ?? {};
const tokenKey = `graphene-mission-token:${bootstrap.missionId ?? "unknown"}`;
const commandTokenKey = `graphene-mission-command-token:${bootstrap.missionId ?? "unknown"}`;
const fragment = new URLSearchParams(window.location.hash.slice(1));
let readToken = fragment.get("token");
let commandToken = fragment.get("command");
try {
  if (!readToken) readToken = sessionStorage.getItem(tokenKey);
  if (readToken && /^[A-Za-z0-9_-]{16,512}$/.test(readToken)) sessionStorage.setItem(tokenKey, readToken);
  if (!commandToken) commandToken = sessionStorage.getItem(commandTokenKey);
  if (commandToken && /^[A-Za-z0-9_-]{16,512}$/.test(commandToken)) sessionStorage.setItem(commandTokenKey, commandToken);
} catch { /* The in-memory fragment token still works when session storage is blocked. */ }
if (!readToken || !/^[A-Za-z0-9_-]{16,512}$/.test(readToken)) readToken = null;
if (!commandToken || !/^[A-Za-z0-9_-]{16,512}$/.test(commandToken)) commandToken = null;
if (fragment.has("token") || fragment.has("command")) history.replaceState(null, "", `${location.pathname}${location.search}`);
const config = Object.freeze({ ...bootstrap, token: readToken, commandToken });
const colors = Object.freeze({ goal: "#155eef", task: "#6f8fa6", worker: "#7559a7", gate: "#b7791f", integration: "#087443", verification: "#0e7490", result: "#334155" });
let state;
let cy;
let selectedNodeId = null;
let lastFocused = null;
let initialSnapshot = null;
let replayDeltas = [];
let replayIndex = 0;
let replayTimer = null;
let staleAt = null;
let drawerTaskId = null;
let drawerGeneration = 0;
let csrfToken = null;
let pendingCommand = null;

function setText(id, value) { $(id).textContent = String(value ?? "—"); }
function humanize(value) { return String(value ?? "unknown").replaceAll("_", " "); }
function request(path, options = {}) {
  const headers = new Headers(options.headers);
  if (config.token) headers.set("Authorization", `Bearer ${config.token}`);
  return fetch(`${config.apiBase ?? "/api/mission-control"}${path}`, { ...options, headers, cache: "no-store" });
}
function missionPath(suffix) { return `/missions/${encodeURIComponent(state?.missionId ?? config.missionId)}${suffix}`; }

async function commandRequest(path, body = null) {
  const headers = new Headers({ Authorization: `Bearer ${config.commandToken}` });
  if (body !== null) {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRF-Token", csrfToken);
  }
  return fetch(`${config.apiBase ?? "/api/mission-control"}${path}`, {
    method: "POST", headers, body: body === null ? null : JSON.stringify(body), credentials: "same-origin", cache: "no-store",
  });
}

async function ensureCommandSession() {
  if (csrfToken) return;
  const response = await commandRequest(missionPath("/commands/session"));
  if (!response.ok) throw new Error("Authenticated command session was rejected.");
  const value = await response.json(); csrfToken = value.csrf_token;
  setText("command-status", `Ready for attributed commands as ${value.operator_label}.`);
}

function commandId() {
  if (crypto.randomUUID) return `browser_${crypto.randomUUID().replaceAll("-", "_")}`;
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  return `browser_${[...bytes].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

function snapshotDocument(value) {
  return {
    view_version: 1, mission: value.mission, head: value.head, cursor: value.cursor,
    tasks: [...value.tasks.values()], attempts: [...value.attempts.values()], workers: [...value.workers.values()],
    gates: [...value.gates.values()], publications: [...value.publications.values()], relationships: [...value.relationships.values()],
    integration: value.integration, verification: value.verification, resources: value.resources, needs_you: value.needsYou,
    critical_path_task_ids: value.criticalPathTaskIds, result: value.result, unknowns: value.unknowns,
    snapshot_sha256: value.snapshotSha256,
  };
}

async function verifyState(value) {
  if (!globalThis.crypto?.subtle) throw new Error("Web Crypto is required to verify committed mission state");
  const bytes = new TextEncoder().encode(canonicalJson(snapshotHashPayload(snapshotDocument(value))));
  const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  if (digest !== value.snapshotSha256) throw new Error("mission snapshot digest verification failed");
  return value;
}

function clear(element) { element.replaceChildren(); }
function element(tag, className = "", value = null) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (value !== null) result.textContent = String(value);
  return result;
}

function renderNeedsYou() {
  const body = $("needs-you-body"); clear(body);
  if (!state.needsYou) {
    if (state.result.state === "approved" && finalResultBinding(state)) {
      $("needs-you").dataset.state = "pending";
      body.append(element("strong", "", "Approved result needs finalization"), element("p", "", "The approval is committed. Finish the verified isolated local commit; the recorded approval attribution cannot be replaced."));
      const review = element("section", "final-review-summary"); renderFinalReview(document, review, state); body.append(review);
    } else {
      $("needs-you").dataset.state = "clear";
      body.append(element("strong", "", "No decision needed"), element("p", "", "Graphene can continue within the committed policy."));
    }
    return;
  }
  $("needs-you").dataset.state = "pending";
  body.append(element("strong", "", state.needsYou.reason));
  if (state.needsYou.evidence_summary) body.append(element("p", "", state.needsYou.evidence_summary));
  const heading = element("h3", "", "Options and consequences");
  const options = element("ol");
  for (const option of state.needsYou.options ?? []) {
    const item = element("li");
    item.append(element("strong", "", `${option.label}: `), document.createTextNode(option.consequence));
    if (config.replay !== true && config.commandsEnabled !== true && !option.value.endsWith("_result")) {
      const command = element("code", "", `graphene mission decide-gate ${state.missionId} --gate ${state.needsYou.gate_id} --decision ${option.value}`);
      item.append(element("br"), command);
    }
    options.append(item);
  }
  const review = element("section", "final-review-summary");
  if (renderFinalReview(document, review, state)) body.append(review);
  body.append(heading, options, element("p", "", config.replay === true
    ? "Replay is read-only. Continuing follows a recorded simulated decision; human attestation remains false."
    : config.commandsEnabled === true
      ? "Use the separately authenticated controls below. The server binds operator identity and truth attribution."
      : "This projection is read-only. Each command records a separate attributed decision event."));
}

function renderBuckets() {
  clear($("status-buckets"));
  for (const bucket of visibleStateBuckets(state)) {
    const group = element("div");
    const term = element("dt", "", humanize(bucket.status));
    const count = element("dd", "", bucket.count);
    const names = element("p", "", bucket.names.join(", "));
    group.append(term, count, names); $("status-buckets").append(group);
  }
}

function workerText(task) {
  const attempt = task.current_attempt_id ? state.attempts.get(task.current_attempt_id) : null;
  const worker = task.worker_id ? state.workers.get(task.worker_id) : null;
  return [worker?.label ?? task.assigned_role ?? "Unassigned", attempt ? `attempt ${attempt.number ?? "?"}` : null].filter(Boolean).join(" · ");
}

function renderTasks() {
  clear($("task-rows"));
  const tasks = [...state.tasks.values()].sort((left, right) => Number(right.priority ?? 0) - Number(left.priority ?? 0) || left.task_id.localeCompare(right.task_id));
  for (const task of tasks) {
    const row = element("tr");
    const title = element("td"); const button = element("button", "", task.title);
    button.type = "button"; button.dataset.taskId = task.task_id; button.addEventListener("click", () => openTask(task.task_id)); title.append(button);
    const status = element("td"); const badge = element("span", "state-label", humanize(task.state)); badge.dataset.state = task.state; status.append(badge);
    row.append(title, status, element("td", "", workerText(task)), element("td", "", task.dependency_ids?.join(", ") || "None"), element("td", "", task.blocker_reason ?? "None"));
    $("task-rows").append(row);
  }
}

function renderGraph() {
  const view = graphView(state); const positions = graphPositions(state);
  const items = [
    ...view.nodes.map((node) => {
      const classes = [];
      if (/failed|blocked|cancelled/.test(node.status)) classes.push("negative");
      if (node.taskId && state.criticalPathTaskIds.includes(node.taskId)) classes.push("critical");
      if (/running|verifying|retrying|needs_input/.test(node.status)) classes.push("active");
      return { group: "nodes", data: { ...node, display: `${node.label}\n${humanize(node.status)}`, color: colors[node.kind] }, position: positions.get(node.id), classes: classes.join(" ") };
    }),
    ...view.edges.map((edge) => ({ group: "edges", data: { id: edge.relationship_id, source: edge.source, target: edge.target, kind: edge.kind, label: humanize(edge.kind) } })),
  ];
  if (!cy) {
    cy = cytoscape({ container: $("mission-graph"), elements: items, layout: { name: "preset", fit: true, padding: 42 }, minZoom: .3, maxZoom: 2.2, style: [
      { selector: "node", style: { width: 58, height: 58, "background-color": "data(color)", label: "data(display)", color: "#14202b", "font-size": 9, "font-weight": 700, "text-wrap": "wrap", "text-max-width": 110, "text-valign": "bottom", "text-margin-y": 8, "border-width": 3, "border-color": "#fff" } },
      { selector: "node.negative", style: { "border-color": "#b42318", "border-width": 7, "border-style": "double" } },
      { selector: "node.critical", style: { "border-color": "#8a5700", "border-width": 7, "border-style": "dashed" } },
      { selector: "node.active", style: { shape: "round-rectangle", "border-width": 7 } },
      { selector: "edge", style: { width: 2, "line-color": "#64748b", "target-arrow-color": "#64748b", "target-arrow-shape": "triangle", "curve-style": "bezier", label: "data(label)", "font-size": 8, color: "#52606d", "text-background-color": "#fff", "text-background-opacity": .9 } },
      { selector: ":selected", style: { "border-color": "#155eef", "border-width": 7 } },
    ] });
    cy.on("tap", "node", (event) => selectGraphNode(event.target.id(), true));
  } else {
    cy.elements().remove(); cy.add(items); cy.fit(undefined, 42);
  }
  clear($("relationship-list"));
  const names = new Map(view.nodes.map((node) => [node.id, node.label]));
  for (const edge of view.edges) $("relationship-list").append(element("li", "", `${names.get(edge.source)} — ${humanize(edge.kind)} → ${names.get(edge.target)}`));
}

function renderStages() {
  setText("resource-status", humanize(state.resources.status)); setText("resource-summary", state.resources.summary);
  clear($("resource-metrics"));
  for (const metric of state.resources.metrics ?? []) $("resource-metrics").append(element("li", "", `${metric.label}: ${metric.display_value} · ${humanize(metric.category)} · ${humanize(metric.attribution_quality)}`));
  for (const name of ["integration", "verification"]) {
    setText(`${name}-state`, humanize(state[name].state)); setText(`${name}-summary`, state[name].summary);
    renderTechnicalProof(`${name}-evidence`, state[name].evidence_refs);
  }
  setText("result-state", humanize(state.result.state)); setText("result-summary", state.result.summary);
  renderTechnicalProof("result-evidence", state.result.evidence_refs);
}

function renderTechnicalProof(id, references = []) {
  const list = $(id); clear(list);
  if (!references.length) return;
  const item = element("li"); const details = element("details");
  details.append(element("summary", "", `Technical proof · ${references.length} committed reference${references.length === 1 ? "" : "s"}`));
  for (const reference of references) details.append(element("code", "proof-reference", `${reference.kind}:${reference.id} · sha256:${reference.sha256}`));
  item.append(details); list.append(item);
}

function confirmationPhrase(action, targetId, fields) {
  if (action === "decide_gate") return `${action}:${targetId}:${fields.decision}`;
  if (action === "approve_final" || action === "reject_final") return `${action}:${targetId}:${fields.expected_bundle_id}`;
  if (action === "supply_input") return `${action}:${targetId}:${fields.gate_id}`;
  return `${action}:${targetId}`;
}

function addCommand(label, action, targetId, consequence, fields = {}, destructive = false, needsInput = false) {
  const button = element("button", "", label); button.type = "button";
  if (destructive) button.dataset.destructive = "true";
  button.addEventListener("click", () => {
    pendingCommand = { action, targetId, consequence, fields, needsInput, head: structuredClone(state.head), commandId: commandId() };
    const phrase = confirmationPhrase(action, targetId, fields);
    setText("command-dialog-title", label); setText("command-consequence", consequence); setText("command-confirmation-phrase", phrase);
    const finalReview = $("command-final-review"); clear(finalReview);
    finalReview.hidden = !(action === "approve_final" || action === "reject_final") || !renderFinalReview(document, finalReview, state);
    $("command-input-fields").hidden = !needsInput; $("command-input").value = ""; $("command-confirmation").value = ""; $("command-rationale").value = ""; $("command-dialog").showModal(); (needsInput ? $("command-input") : $("command-confirmation")).focus();
  });
  $("command-actions").append(button);
}

function renderCommands() {
  const panel = $("command-controls"); clear($("command-actions"));
  if (config.replay === true || config.commandsEnabled !== true) { panel.hidden = true; return; }
  panel.hidden = false;
  if (!config.commandToken) {
    setText("command-status", "Command credential unavailable. Reopen the private operator URL."); $("command-status").dataset.state = "error"; return;
  }
  const status = state.mission.status; const mission = state.missionId; const revision = state.mission.plan_revision;
  if (status === "proposed") {
    addCommand("Approve plan", "approve_plan", `plan:${revision}`, `Approve exact plan revision ${revision} and allow scheduling.`, { expected_plan_revision: revision });
    addCommand("Reject plan", "reject_plan", `plan:${revision}`, `Reject exact plan revision ${revision}; no task execution is authorized.`, { expected_plan_revision: revision }, true);
  }
  if (status === "running") {
    addCommand("Pause mission", "pause", mission, "Pause new mission scheduling at the current committed head.");
    addCommand("Request plan revision", "request_replan", mission, "Record a replan request and leave execution paused.");
  }
  if (status === "paused") {
    addCommand("Resume mission", "resume", mission, "Resume scheduling from the current committed head.");
    addCommand("Request plan revision", "request_replan", mission, "Record a replan request; execution remains paused.");
  }
  if (config.cancelEnabled === true && ["proposed", "running", "paused", "awaiting_result"].includes(status) && state.mission.outcome !== "approved_pending_commit") addCommand("Cancel mission", "cancel", mission, `Stop Graphene-owned local processes, then cancel exactly mission ${mission}.`, {}, true);
  for (const task of state.tasks.values()) if (task.state === "failed") addCommand(`Retry ${task.title}`, "retry_task", task.task_id, `Retry only failed task ${task.task_id}.`);
  for (const task of state.tasks.values()) if (task.state === "needs_input" && task.blocker_reason?.startsWith("input:")) {
    const gateId = task.blocker_reason.slice(6);
    if (config.inputEnabled === true) addCommand(`Supply input to ${task.title}`, "supply_input", task.task_id, `Store bounded private input for task ${task.task_id} and exact gate ${gateId}.`, { gate_id: gateId }, false, true);
    else { setText("command-status", `Task ${task.task_id} needs private input, but this server has no writable private artifact resolver.`); $("command-status").dataset.state = "error"; }
  }
  if (state.needsYou && status !== "awaiting_result") for (const option of state.needsYou.options ?? []) addCommand(option.label, "decide_gate", state.needsYou.gate_id, option.consequence, { decision: option.value });
  if (status === "awaiting_result") {
    const binding = finalResultBinding(state);
    if (binding) {
      for (const option of finalDecisionOptions(state)) addCommand(option.label, option.action, `result:${mission}`, option.consequence, { expected_bundle_id: option.bundleId }, option.destructive);
    } else if (["awaiting_decision", "approved"].includes(state.result.state)) {
      setText("command-status", "Final-result authority is ambiguous. No decision command is available."); $("command-status").dataset.state = "error";
    }
  }
}

function render() {
  setText("goal-heading", state.mission.goal); clear($("success-criteria"));
  setText("mission-status", `Mission ${humanize(state.mission.status)}`);
  const brief = missionBrief(state); setText("mission-progress", brief.progress); setText("brief-current", brief.current); setText("brief-next", brief.next); setText("brief-needs", brief.needs);
  for (const criterion of state.mission.success_criteria ?? []) $("success-criteria").append(element("li", "", criterion));
  setText("head", `seq ${state.head.seq} · ${state.head.event_sha256.slice(0, 12)}…`);
  setText("critical-path", `Critical path: ${state.criticalPathTaskIds.map((id) => state.tasks.get(id)?.title ?? id).join(" → ") || "none established"}`);
  renderNeedsYou(); renderCommands(); renderBuckets(); renderTasks(); renderStages(); renderGraph();
  clear($("unknown-list")); for (const unknown of state.unknowns.length ? state.unknowns : ["No unresolved unknowns are recorded."]) $("unknown-list").append(element("li", "", unknown));
}

function appendListSection(parent, title, values) {
  const section = element("section"); section.append(element("h3", "", title)); const list = element("ul");
  for (const value of values?.length ? values : ["None recorded."]) list.append(element("li", "", typeof value === "string" ? value : value.summary ?? JSON.stringify(value)));
  section.append(list); parent.append(section);
}

async function openTask(taskId) {
  const generation = ++drawerGeneration;
  const openingState = state; const openingCursor = openingState.cursor; const openingHead = structuredClone(openingState.head);
  drawerTaskId = taskId; lastFocused = document.activeElement; setText("drawer-title", openingState.tasks.get(taskId)?.title ?? taskId); setText("drawer-state", "Loading bounded committed task evidence…");
  $("task-drawer").hidden = false; $("drawer-close").focus(); clear($("drawer-body"));
  try {
    const response = await request(missionPath(`/tasks/${encodeURIComponent(taskId)}?cursor=${encodeURIComponent(openingCursor)}`));
    if (generation !== drawerGeneration || drawerTaskId !== taskId) return;
    if (!response.ok) throw new Error(`task detail unavailable (${response.status})`);
    const detail = await response.json();
    if (generation !== drawerGeneration || drawerTaskId !== taskId) return;
    if (detail.head.seq !== openingHead.seq || detail.head.event_sha256 !== openingHead.event_sha256) throw new Error("task detail does not match its opening cursor");
    const facts = element("dl");
    for (const [label, value] of [["Contract", detail.task.contract], ["State", detail.task.state], ["Role", detail.task.assigned_role], ["Read scope", detail.read_scope?.join(", ")], ["Write scope", detail.write_scope?.join(", ")], ["Current attempt", detail.task.current_attempt_id]]) {
      facts.append(element("dt", "", label), element("dd", "", value || "Not established"));
    }
    $("drawer-body").append(facts);
    appendListSection($("drawer-body"), "Attempts", detail.attempts?.map((attempt) => `Attempt ${attempt.number} · ${attempt.worker_id} · ${humanize(attempt.status)} · fence ${attempt.fencing_token}`));
    appendListSection($("drawer-body"), "Allowlisted command templates", detail.task.allowed_command_templates);
    appendListSection($("drawer-body"), "Acceptance checks", detail.acceptance_checks);
    appendListSection($("drawer-body"), "Inherited evidence", detail.inherited_evidence);
    appendListSection($("drawer-body"), "Published artifacts", detail.publications);
    appendListSection($("drawer-body"), "Changed paths / hunks", detail.changed_hunks);
    appendListSection($("drawer-body"), "Command-template receipts", detail.command_receipts);
    appendListSection($("drawer-body"), "Test receipts", detail.test_receipts);
    appendListSection($("drawer-body"), "Resource summary", detail.resource_receipts);
    appendListSection($("drawer-body"), "Unknowns", detail.unknowns);
    const evidence = taskEvidenceTarget(openingState, taskId);
    if (evidence?.kind === "generic") {
      const button = element("button", "evidence-button", "Load generic attempt evidence");
      button.type = "button";
      button.addEventListener("click", async () => {
        if (generation !== drawerGeneration || drawerTaskId !== taskId) return;
        button.disabled = true;
        try {
          const path = missionPath(`/attempts/${encodeURIComponent(evidence.attemptId)}/evidence?cursor=${encodeURIComponent(openingCursor)}`);
          const response = await request(path);
          if (generation !== drawerGeneration || drawerTaskId !== taskId) return;
          if (!response.ok) throw new Error(`attempt evidence unavailable (${response.status})`);
          const value = await response.json();
          if (generation !== drawerGeneration || drawerTaskId !== taskId) return;
          if (value.head.seq !== detail.head.seq || value.head.event_sha256 !== detail.head.event_sha256) throw new Error("attempt evidence does not match the open task detail");
          appendListSection($("drawer-body"), "Generic attempt references", value.references?.map((reference) => `${reference.kind}:${reference.id} · sha256:${reference.sha256}`));
          appendListSection($("drawer-body"), "Generic evidence limits", value.limitations);
          button.remove();
        } catch (error) {
          if (generation === drawerGeneration && drawerTaskId === taskId) { button.disabled = false; setText("drawer-state", error.message); }
        }
      });
      $("drawer-body").append(button);
    } else if (evidence?.kind === "legacy") {
      const link = element("a", "", `Open legacy v2 evidence run ${evidence.runId}`); link.href = evidence.href; $("drawer-body").append(link);
    }
    setText("drawer-state", "Showing the bounded public projection. Raw prompts, environment, argv, output, and hidden reasoning are not exposed.");
  } catch (error) {
    if (generation === drawerGeneration && drawerTaskId === taskId) setText("drawer-state", error.message);
  }
}

function markDrawerStale() {
  if (!$("task-drawer").hidden) setText("drawer-state", "Mission state advanced. This drawer remains at an earlier committed head; close and reopen it to load current evidence.");
}
function closeDrawer() {
  drawerGeneration += 1;
  $("task-drawer").hidden = true;
  const replacement = [...document.querySelectorAll("[data-task-id]")].find((button) => button.dataset.taskId === drawerTaskId);
  drawerTaskId = null;
  if (replacement) replacement.focus(); else if (lastFocused?.isConnected) lastFocused.focus();
}
function selectGraphNode(id, open = false) {
  selectedNodeId = id; cy?.nodes().unselect(); cy?.getElementById(id).select();
  const node = graphView(state).nodes.find((item) => item.id === id); if (!node) return;
  setText("graph-status", `${node.kind}: ${node.label}; status ${humanize(node.status)}`);
  if (open && node.taskId) openTask(node.taskId);
}

function markStale(error) {
  staleAt ??= new Date(); $("stale-banner").hidden = false; setText("stale-since", `Last verified ${staleAt.toLocaleTimeString()}. ${error ?? ""}`);
  setText("connection", "Reconnecting"); $("connection").dataset.state = "stale";
}
function markFresh() { staleAt = null; $("stale-banner").hidden = true; setText("connection", "Watching committed state"); $("connection").dataset.state = "live"; }

async function freshSnapshot() {
  const previousCursor = state?.cursor; const drawerWasOpen = !$("task-drawer").hidden;
  const response = await request(missionPath("/snapshot")); if (!response.ok) throw new Error(`snapshot rejected (${response.status})`);
  state = createState(await response.json()); await verifyState(state); render();
  if (drawerWasOpen && previousCursor !== state.cursor) markDrawerStale();
  markFresh();
}

async function stream() {
  while (config.replay !== true) {
    try {
      const response = await request(missionPath(`/stream?cursor=${encodeURIComponent(state.cursor)}`), { headers: { Accept: "application/x-ndjson" } });
      if (response.status === 409) { markStale("Cursor expired."); await freshSnapshot(); continue; }
      if (!response.ok || !response.body) throw new Error(`stream rejected (${response.status})`);
      markFresh(); const reader = response.body.pipeThrough(new TextDecoderStream()).getReader(); let buffer = "";
      while (true) {
        const { value, done } = await reader.read(); if (done) throw new Error("stream ended"); buffer += value;
        const lines = buffer.split("\n"); buffer = lines.pop();
        for (const line of lines) if (line.trim()) {
          const envelope = JSON.parse(line); if (envelope.type === "heartbeat") continue;
          const drawerWasOpen = !$("task-drawer").hidden;
          state = applyDelta(state, envelope); await verifyState(state); render();
          if (drawerWasOpen) markDrawerStale();
        }
      }
    } catch (error) { markStale(error.message); await new Promise((resolve) => setTimeout(resolve, 700)); try { await freshSnapshot(); } catch (snapshotError) { markStale(snapshotError.message); } }
  }
}

function rebuildReplay(index) {
  const previousCursor = state?.cursor; const drawerWasOpen = !$("task-drawer").hidden;
  replayIndex = Math.max(0, Math.min(replayDeltas.length, index)); state = applyThrough(initialSnapshot, replayDeltas, replayIndex); render();
  if (drawerWasOpen && previousCursor !== state.cursor) closeDrawer();
  $("timeline").value = String(replayIndex); setText("timeline-label", `${replayIndex + 1} of ${replayDeltas.length + 1}`);
  updateReplayControls();
}
function recordedDecisionCheckpoint() { return config.replay === true && state?.needsYou?.gate_id?.startsWith("final_result_"); }
function updateReplayControls() {
  const decision = recordedDecisionCheckpoint();
  setText("replay-start", decision ? "Continue with recorded simulated approval" : replayIndex >= replayDeltas.length ? "Play from start" : "Play the mission");
  $("replay-step").disabled = decision || replayIndex >= replayDeltas.length;
}
function playReplay() {
  clearTimeout(replayTimer); if (replayIndex >= replayDeltas.length) rebuildReplay(0);
  if (recordedDecisionCheckpoint()) { rebuildReplay(replayIndex + 1); return; }
  const step = () => { if (replayIndex >= replayDeltas.length) return; rebuildReplay(replayIndex + 1); if (!recordedDecisionCheckpoint()) replayTimer = setTimeout(step, 650); }; step();
}

async function submitCommand() {
  if (!pendingCommand) return;
  if (pendingCommand.needsInput && !$("command-input").value.length) { setText("command-status", "Task input cannot be empty."); $("command-status").dataset.state = "error"; $("command-input").focus(); return; }
  const submit = $("command-submit"); submit.disabled = true;
  try {
    await ensureCommandSession();
    const body = {
      action: pendingCommand.action,
      command_id: pendingCommand.commandId,
      expected_head: { mission_id: state.missionId, seq: pendingCommand.head.seq, event_sha256: pendingCommand.head.event_sha256 },
      target_id: pendingCommand.targetId,
      confirmation: $("command-confirmation").value,
      rationale: $("command-rationale").value.trim() || null,
      ...pendingCommand.fields,
    };
    if (pendingCommand.needsInput) body.input_text = $("command-input").value;
    const response = await commandRequest(missionPath("/commands"), body);
    const value = await response.json().catch(() => ({ code: "COMMAND_REJECTED" }));
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) csrfToken = null;
      if (value.code === "MISSION_HEAD_STALE") {
        $("command-dialog").close(); pendingCommand = null; await freshSnapshot();
        setText("command-status", "Mission changed before submission. The current head is refreshed; review and confirm the action again.");
      } else setText("command-status", value.detail ?? "Command rejected without changing mission state.");
      $("command-status").dataset.state = "error";
      return;
    }
    $("command-dialog").close(); pendingCommand = null;
    try {
      await freshSnapshot(); setText("command-status", `Command accepted at committed head ${value.head.seq}.`); delete $("command-status").dataset.state;
    } catch (error) {
      markStale(error.message); setText("command-status", `Command accepted at committed head ${value.head.seq}, but the refreshed projection is unavailable.`); $("command-status").dataset.state = "error";
    }
  } catch {
    setText("command-status", "Command connection failed without a confirmed state change. Refresh before retrying."); $("command-status").dataset.state = "error";
  } finally { submit.disabled = false; }
}

async function start() {
  setText("mode", config.mode ?? "LOCAL MISSION CONTROL"); setText("proof-boundary", config.truthLabel ?? "Committed mission projection");
  if (config.replay === true) {
    const response = await request(missionPath("/replay")); if (!response.ok) throw new Error(`mission replay unavailable (${response.status})`);
    const replay = await response.json();
    if (replay.meta?.truth_label !== config.truthLabel) throw new Error("mission replay truth label does not match the server boundary");
    let verified = createState(replay.snapshot); await verifyState(verified);
    for (const envelope of replay.deltas) { verified = applyDelta(verified, envelope); await verifyState(verified); }
    if (verified.snapshotSha256 !== replay.meta?.final_snapshot_sha256) throw new Error("mission replay final digest is invalid");
    initialSnapshot = replay.snapshot; replayDeltas = replay.deltas; rebuildReplay(0);
    $("replay-controls").hidden = false; $("timeline").max = String(replayDeltas.length); $("connection").dataset.state = "replay"; setText("connection", "Verified replay");
  } else { await freshSnapshot(); stream(); }
}

$("drawer-close").addEventListener("click", closeDrawer);
$("replay-start").addEventListener("click", playReplay);
$("replay-step").addEventListener("click", () => rebuildReplay(replayIndex + 1));
$("timeline").addEventListener("input", (event) => { clearTimeout(replayTimer); rebuildReplay(Number(event.target.value)); });
$("command-dismiss").addEventListener("click", () => { $("command-dialog").close(); pendingCommand = null; });
$("command-submit").addEventListener("click", submitCommand);
$("command-dialog").addEventListener("close", () => {
  $("command-input").value = ""; $("command-rationale").value = ""; $("command-confirmation").value = ""; pendingCommand = null;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("task-drawer").hidden) { closeDrawer(); return; }
  if (event.target !== $("mission-graph") || !cy || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key)) return;
  if (event.key === "Enter") { const node = graphView(state).nodes.find((item) => item.id === selectedNodeId); if (node?.taskId) openTask(node.taskId); return; }
  event.preventDefault(); const nodes = cy.nodes().sort((left, right) => left.id().localeCompare(right.id())); if (!nodes.length) return;
  const direction = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1; const current = nodes.findIndex((node) => node.id() === selectedNodeId);
  selectGraphNode(nodes[current < 0 ? (direction > 0 ? 0 : nodes.length - 1) : (current + direction + nodes.length) % nodes.length].id());
});

start().catch((error) => { markStale(error.message); setText("goal-heading", "Mission Control unavailable"); });
