import cytoscape from "./vendor/cytoscape.esm.min.mjs";
import { activityRadius, applyDelta, applyThrough, createState, deltaSubjectId, directedEvidenceIds, evidenceInvalidResponse, headSummary, statePositions, statusBadgeData, visibleGraph } from "./reducer.mjs";

const $ = (id) => document.getElementById(id);
const config = Object.freeze(window.__GRAPHENE_VIEWER__ ?? {});
const groups = Object.freeze([
  ["agent", "Agent", "#6f8fa6"], ["tool", "Tool", "#a9b4bc"], ["evidence", "File / evidence", "#7b9bb2"],
  ["human", "Human / memory", "#d5ae73"], ["policy", "Policy", "#d77b75"], ["test", "Test", "#73aa91"], ["handoff", "Handoff / promotion", "#9a88bd"],
]);
const enabledGroups = new Set(groups.map(([id]) => id));
const colorByGroup = Object.fromEntries(groups.map(([id, , color]) => [id, color]));
const prefersReducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const initialPositions = new Map();
let positions = initialPositions;
let initialSnapshot;
let state;
let cy;
let currentId = null;
let selectedId = null;
let paused = false;
let playTimer = null;
let deltaLog = [];
let pending = [];
let replayIndex = 0;
let live = true;
let lastFocused = null;
let renderFrame = null;
let pulseTimer = null;
let pulsingId = null;

function setText(id, value) { $(id).textContent = String(value ?? "—"); }
function request(url, options = {}) {
  const headers = new Headers(options.headers);
  if (config.token) headers.set("Authorization", `Bearer ${config.token}`);
  return fetch(url, { ...options, headers, cache: "no-store" });
}
function endpoint(path) { return `${config.apiBase ?? "/api/viewer"}${path}`; }
function rootPath(suffix) { return endpoint(`/runs/${encodeURIComponent(state?.rootRunId ?? config.rootRunId)}${suffix}`); }
function formatHead() {
  return headSummary(state.heads, state.rootRunId);
}
function metadataLines(metadata) {
  return Object.entries(metadata).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 8);
}
function runState() {
  const runs = [...state.nodes.values()].filter((node) => node.id.startsWith("run:"));
  return runs.find((node) => node.runId !== state.rootRunId)?.status
    ?? runs.find((node) => node.runId === state.rootRunId)?.status
    ?? "Observed";
}

function buildFilters() {
  for (const [id, label] of groups) {
    const button = document.createElement("button");
    const dot = document.createElement("span");
    dot.className = `filter-dot filter-dot--${id}`;
    button.type = "button";
    button.dataset.group = id;
    button.setAttribute("aria-pressed", "true");
    button.append(dot, document.createTextNode(label));
    button.addEventListener("click", () => {
      enabledGroups.has(id) ? enabledGroups.delete(id) : enabledGroups.add(id);
      button.setAttribute("aria-pressed", String(enabledGroups.has(id)));
      render();
    });
    $("filters").append(button);
  }
}

function graphElements(view) {
  return [
    ...view.nodes.map((node) => {
      const statusColor = /denied|failed|invalid|rejected/.test(node.status.toLowerCase()) ? "#ef746f" : node.truthKind.includes("human") ? "#d5ae73" : "#73aa91";
      return ({
      group: "nodes",
      data: {
        ...node,
        size: activityRadius(node.activity),
        color: colorByGroup[node.group],
        borderColor: statusColor,
        badge: statusBadgeData(statusColor),
      },
      position: positions.get(node.id),
      classes: [node.id === currentId ? "current" : "", /denied|failed|invalid|rejected/.test(node.status.toLowerCase()) ? "negative" : ""].filter(Boolean).join(" "),
    }); }),
    ...view.edges.map((edge) => ({ group: "edges", data: { ...edge, width: Math.min(8, 1.4 + Math.log2(1 + edge.activity) * 1.2) }, classes: edge.target === currentId ? "current" : "" })),
  ];
}

function renderList(view) {
  $("relationships").replaceChildren();
  const nodes = new Map(view.nodes.map((node) => [node.id, node]));
  for (const edge of view.edges) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${nodes.get(edge.source).label} — ${edge.kind} → ${nodes.get(edge.target).label}`;
    button.addEventListener("click", () => selectNode(edge.target));
    item.append(button);
    $("relationships").append(item);
  }
  $("relationships-empty").hidden = view.edges.length > 0;
  setText("relationship-count", `${view.edges.length} verified relationship${view.edges.length === 1 ? "" : "s"}`);
}

function render(organize = false) {
  positions = statePositions(state, positions, organize);
  const view = visibleGraph(state, enabledGroups);
  const elements = graphElements(view);
  if (!cy) {
    cy = cytoscape({
      container: $("canvas"), elements, layout: { name: "preset", fit: true, padding: 64 }, minZoom: 0.25, maxZoom: 2.4,
      wheelSensitivity: 0.25,
      style: [
        { selector: "node", style: { "background-color": "data(color)", "background-image": "data(badge)", "background-fit": "none", "background-width": "18px", "background-height": "18px", "background-position-x": "78%", "background-position-y": "20%", width: "data(size)", height: "data(size)", label: "data(label)", color: "#f7fafb", "font-size": 11, "font-weight": 650, "text-wrap": "wrap", "text-max-width": 90, "text-valign": "center", "text-halign": "center", "border-width": 4, "border-color": "data(borderColor)", "border-opacity": 0.9, "overlay-opacity": 0 } },
        { selector: "edge", style: { width: "data(width)", "line-color": "#71808a", "target-arrow-color": "#71808a", "target-arrow-shape": "triangle", "curve-style": "bezier", opacity: 0.68, "arrow-scale": 0.72 } },
        { selector: ".negative", style: { "border-color": "#ef746f", "border-style": "double", "border-width": 7 } },
        { selector: ".current", style: { "border-color": "#e7edf0", "line-color": "#e7edf0", "target-arrow-color": "#e7edf0", "z-index": 10 } },
        { selector: ":selected", style: { "border-color": "#ffffff", "border-width": 7 } },
        { selector: ".faded", style: { opacity: 0.12, "text-opacity": 0.08 } },
        { selector: ".path", style: { opacity: 1, "line-color": "#dbe7ec", "target-arrow-color": "#dbe7ec", "z-index": 20 } },
      ],
    });
    cy.on("tap", "node", (event) => selectNode(event.target.id()));
    cy.on("tap", (event) => { if (event.target === cy) clearPath(); });
  } else {
    cy.batch(() => {
      const desired = new Set(elements.map((element) => element.data.id));
      cy.elements().forEach((element) => { if (!desired.has(element.id())) element.remove(); });
      for (const element of elements.filter((item) => item.group === "nodes")) {
        const existing = cy.getElementById(element.data.id);
        if (existing.length) { existing.data(element.data); existing.position(element.position); existing.classes(element.classes); }
        else cy.add(element);
      }
      for (const element of elements.filter((item) => item.group === "edges")) {
        const existing = cy.getElementById(element.data.id);
        if (existing.length) { existing.data(element.data); existing.classes(element.classes); }
        else cy.add(element);
      }
    });
  }
  if (organize) cy.fit(undefined, 62);
  renderList(view);
  $("canvas-state").hidden = view.nodes.length > 0;
  if (!view.nodes.length) setText("canvas-state", "No lineage matches the active filters.");
  const omitted = Object.values(state.omittedCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  setText("bounds", `${view.nodes.length} bubbles · ${view.edges.length} explicit lines · ${omitted} omitted · ${state.unknowns.length} unknown`);
  setText("verified-head", formatHead());
  setText("run-state", state.invalidReason ? "Evidence invalid" : runState());
  $("timeline").max = String(deltaLog.length);
  $("timeline").value = String(replayIndex);
  setText("timeline-label", `${replayIndex} / ${deltaLog.length}`);
  if (state.invalidReason) showInvalid(state.invalidReason);
  pulseCurrent();
}

function scheduleRender() {
  if (renderFrame !== null) return;
  renderFrame = requestAnimationFrame(() => { renderFrame = null; render(); });
}

function pulseCurrent() {
  if (prefersReducedMotion || pulsingId === currentId) return;
  clearInterval(pulseTimer);
  pulsingId = currentId;
  let bright = false;
  pulseTimer = currentId ? setInterval(() => {
    bright = !bright;
    cy?.getElementById(currentId).style("border-width", bright ? 9 : 5);
    cy?.edges().filter((edge) => edge.target().id() === currentId).style("opacity", bright ? 1 : .65);
  }, 650) : null;
}

function connectedPath(id) {
  if (!cy || !cy.getElementById(id).length) return;
  const view = visibleGraph(state, enabledGroups);
  const connected = directedEvidenceIds(view.nodes, view.edges, id);
  cy.elements().addClass("faded");
  for (const nodeId of connected) cy.getElementById(nodeId).removeClass("faded").addClass("path");
  cy.edges().filter((edge) => connected.has(edge.source().id()) && connected.has(edge.target().id())).removeClass("faded").addClass("path");
}
function clearPath() { cy?.elements().removeClass("faded path"); selectedId = null; }

async function selectNode(id) {
  selectedId = id;
  const node = state.nodes.get(id);
  if (!node) return;
  lastFocused = document.activeElement;
  cy.getElementById(id).select();
  connectedPath(id);
  setText("drawer-kind", node.kind.replaceAll("_", " ").toUpperCase());
  setText("drawer-title", node.label);
  $("drawer-fields").replaceChildren();
  const fields = [
    ["Meaning", node.label], ["Status", node.status], ["Run", node.runId ?? "Shared across run family"],
    ["Sequence", node.sequence ?? "Not exposed"], ["Truth kind", node.truthKind], ["Activity", node.activity],
    ["Source reference", node.sourceRef ?? "Not exposed"], ["Digest", node.digest ?? "Not exposed"], ...metadataLines(node.metadata),
  ];
  for (const [label, value] of fields) {
    const term = document.createElement("dt"); const description = document.createElement("dd");
    term.textContent = String(label).replaceAll("_", " "); description.textContent = String(value);
    $("drawer-fields").append(term, description);
  }
  $("drawer").hidden = false;
  setText("drawer-state", "Showing sanitized projection data. Loading bounded server detail…");
  $("drawer-close").focus();
  if (live && state.rootRunId) {
    try {
      const response = await request(rootPath(`/nodes/${encodeURIComponent(id)}`));
      if (!response.ok) throw new Error(`detail unavailable (${response.status})`);
      const detail = await response.json();
      if (selectedId !== id) return;
      setText("drawer-state", detail.digest && node.digest && detail.digest !== node.digest ? "Detail digest differs; projection remains authoritative." : "Bounded detail matches the selected public node.");
    } catch (error) { if (selectedId === id) setText("drawer-state", `Public summary shown; ${error.message}.`); }
  } else setText("drawer-state", "Checked-in sanitized replay detail.");
}

function closeDrawer() {
  $("drawer").hidden = true;
  selectedId = null;
  clearPath();
  lastFocused?.focus();
}
function showInvalid(reason) {
  if (state) state.invalidReason ??= reason;
  $("invalid").hidden = false;
  setText("invalid-reason", reason);
  setText("connection", "Stopped");
  $("connection").dataset.state = "error";
  paused = true;
  updatePlay();
}
function updatePlay() {
  setText("play", paused ? "Play" : "Pause");
  $("play").setAttribute("aria-label", paused ? "Play replay" : "Pause replay");
  clearTimeout(playTimer);
  if (!live && !paused && replayIndex < deltaLog.length) playTimer = setTimeout(step, Number($("speed").value));
}
function rebuild(index) {
  state = applyThrough(initialSnapshot, deltaLog, index);
  currentId = null;
  for (const delta of deltaLog.slice(0, index)) {
    currentId = deltaSubjectId(delta) ?? currentId;
  }
  replayIndex = index;
  render();
}
function step() {
  if (replayIndex < deltaLog.length) rebuild(replayIndex + 1);
  if (replayIndex >= deltaLog.length) paused = true;
  updatePlay();
}
function consume(delta) {
  deltaLog.push(delta);
  if (paused) { pending.push(delta); render(); return; }
  state = applyDelta(state, delta);
  currentId = deltaSubjectId(delta) ?? currentId;
  replayIndex = deltaLog.length;
  scheduleRender();
}

async function stream() {
  while (!state.invalidReason) {
    try {
      setText("connection", "Connecting"); $("connection").dataset.state = "connecting";
      const response = await request(rootPath(`/stream?cursor=${encodeURIComponent(state.cursor ?? "")}`), { headers: { Accept: "application/x-ndjson" } });
      const invalidDetail = await evidenceInvalidResponse(response);
      if (invalidDetail) { showInvalid(invalidDetail); return; }
      if (!response.ok || !response.body) throw new Error(`stream rejected (${response.status})`);
      setText("connection", "Live"); $("connection").dataset.state = "live";
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;
        const lines = buffer.split("\n"); buffer = lines.pop();
        for (const line of lines) if (line.trim()) {
          try {
            consume(JSON.parse(line));
          } catch (error) {
            showInvalid(`Malformed viewer payload: ${error.message}`);
            await reader.cancel();
            return;
          }
        }
      }
    } catch (error) {
      if (state.invalidReason) return;
      setText("connection", "Reconnecting"); $("connection").dataset.state = "connecting";
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  }
}

async function start() {
  buildFilters();
  let payload;
  if (config.rootRunId) {
    const response = await request(endpoint(`/runs/${encodeURIComponent(config.rootRunId)}/snapshot`));
    const invalidDetail = await evidenceInvalidResponse(response);
    if (invalidDetail) {
      initialSnapshot = { root_run_id: config.rootRunId, nodes: [], edges: [], heads: [], omitted_counts: {}, unknowns: [] };
      state = createState(initialSnapshot);
      render();
      showInvalid(invalidDetail);
      return;
    }
    if (!response.ok) throw new Error(`snapshot rejected (${response.status})`);
    try {
      initialSnapshot = await response.json();
      state = createState(initialSnapshot);
    } catch (error) {
      initialSnapshot = { root_run_id: config.rootRunId, nodes: [], edges: [], heads: [], omitted_counts: {}, unknowns: [] };
      state = createState(initialSnapshot);
      render();
      showInvalid(`Malformed viewer payload: ${error.message}`);
      return;
    }
    payload = { meta: { mode: config.mode ?? config.driver ?? "SCRIPTED LOCAL", truth_label: config.truthLabel ?? "COMMITTED + VERIFIED V2 SQLITE" }, snapshot: initialSnapshot };
    live = true;
  } else {
    const response = await fetch(config.replayUrl ?? "/static/replay.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`replay unavailable (${response.status})`);
    payload = await response.json();
    initialSnapshot = payload.snapshot;
    deltaLog = payload.deltas ?? [];
    live = false;
    paused = false;
  }
  state ??= createState(initialSnapshot);
  setText("mode", payload.meta?.mode ?? "LOCAL VIEWER");
  setText("truth-label", payload.meta?.truth_label ?? "Committed and verified v2 SQLite lineage");
  setText("driver-truth", `Google ADK Runner: ${payload.meta?.adk_runner ?? config.adkRunner ?? (config.driver === "adk-fake" ? "real Google ADK 2.5.0" : "not used")} · Gemini calls: ${payload.meta?.gemini_calls ?? config.geminiCalls ?? 0} · Evidence source: ${payload.meta?.evidence_source ?? config.evidenceSource ?? "committed and verified v2 SQLite lineage"}`);
  setText("live-badge", live ? "LIVE" : "REPLAY");
  setText("connection", live ? "Live" : "Offline fixture");
  $("connection").dataset.state = live ? "live" : "replay";
  render(true);
  if (live) stream(); else updatePlay();
}

$("fit").addEventListener("click", () => cy?.fit(undefined, 62));
$("organize").addEventListener("click", () => render(true));
$("focus-current").addEventListener("click", () => currentId && cy?.animate({ center: { eles: cy.getElementById(currentId) }, zoom: 1.12 }, { duration: prefersReducedMotion ? 0 : 320 }));
$("evidence-path").addEventListener("click", () => selectedId ? connectedPath(selectedId) : currentId && connectedPath(currentId));
$("reset-filters").addEventListener("click", () => { enabledGroups.clear(); groups.forEach(([id]) => enabledGroups.add(id)); document.querySelectorAll("[data-group]").forEach((button) => button.setAttribute("aria-pressed", "true")); clearPath(); render(); });
$("drawer-close").addEventListener("click", closeDrawer);
$("play").addEventListener("click", () => { paused = !paused; if (live && !paused) { rebuild(deltaLog.length); pending = []; } updatePlay(); });
$("step").addEventListener("click", () => { paused = true; step(); });
$("speed").addEventListener("change", updatePlay);
$("timeline").addEventListener("input", (event) => { paused = true; rebuild(Number(event.target.value)); updatePlay(); });
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("drawer").hidden) closeDrawer();
  if (!cy || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key)) return;
  if (event.key === "Enter" && selectedId) { selectNode(selectedId); return; }
  if (event.key === "Enter") return;
  const nodes = cy.nodes().sort((left, right) => left.id().localeCompare(right.id()));
  if (!nodes.length) return;
  event.preventDefault();
  const index = Math.max(0, nodes.findIndex((node) => node.id() === selectedId));
  selectedId = nodes[(index + (event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1) + nodes.length) % nodes.length].id();
  cy.nodes().unselect(); cy.getElementById(selectedId).select();
});

start().catch((error) => {
  setText("canvas-state", `Viewer unavailable: ${error.message}`);
  setText("connection", "Error"); $("connection").dataset.state = "error";
});
