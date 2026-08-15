import cytoscape from "./vendor/cytoscape.esm.min.mjs";
import {
  REVIEW_SECTIONS, activityRadius, applyDelta, applyThrough, attentionFact, createState,
  deltaSubjectId, evidenceInvalidResponse, headSummary, projectionCounts, reviewBriefFacts,
  stageGroups, statePositions, statusBadgeData, storyNodeIds, truthLabel,
  verifiedSupportPath, visibleGraph,
} from "./reducer.mjs";

const $ = (id) => document.getElementById(id);
const config = Object.freeze(window.__GRAPHENE_VIEWER__ ?? {});
const VERIFIED_REPLAY_LABEL = "VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION";
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
let lastFocusId = null;
let topologyScope = "decision";
let focusedFact = null;
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

function truthMark(truthKind) {
  return ({ simulated_fixture: "SIM", human_attested: "HUMAN", policy_authoritative: "POLICY", runtime_observed: "OBS", server_derived: "DERIVED", evidence_bound: "BOUND" })[truthKind] ?? "FACT";
}

function restoreFocus(focusId) {
  if (!focusId) return;
  [...document.querySelectorAll("[data-focus-id]")].find((element) => element.dataset.focusId === focusId)?.focus();
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
      const negative = /denied|failed|invalid|rejected|blocked/.test(node.status.toLowerCase());
      const positive = /passed|approved|promoted|completed|committed|allowed|verified/.test(node.status.toLowerCase());
      const statusColor = negative ? "#ef746f" : node.truthKind === "simulated_fixture" ? "#9a88bd" : node.truthKind === "human_attested" ? "#d5ae73" : positive ? "#73aa91" : "#a9b4bc";
      return ({
      group: "nodes",
      data: {
        ...node,
        displayLabel: `[${truthMark(node.truthKind)}] ${node.label}`,
        size: activityRadius(node.activity),
        color: colorByGroup[node.group],
        borderColor: statusColor,
        badge: statusBadgeData(statusColor),
      },
      position: positions.get(node.id),
      classes: [node.id === currentId ? "current" : "", negative ? "negative" : "", `truth-${node.truthKind}`].filter(Boolean).join(" "),
    }); }),
    ...view.edges.map((edge) => ({
      group: "edges",
      data: { ...edge, width: Math.min(8, 1.4 + Math.log2(1 + edge.activity) * 1.2) },
      classes: [edge.target === currentId ? "current" : "", edge.relationshipClass ? `relationship-${edge.relationshipClass}` : "relationship-untyped", edge.supportPath ? "support" : ""].filter(Boolean).join(" "),
    })),
  ];
}

function factButton(fact, prefix) {
  const button = document.createElement("button");
  const label = document.createElement("span");
  const value = document.createElement("span");
  const truth = document.createElement("span");
  const status = document.createElement("span");
  button.type = "button";
  button.className = "brief-fact";
  button.dataset.focusId = `${prefix}:${fact.id}`;
  label.className = "brief-fact__label";
  value.className = "brief-fact__value";
  truth.className = "truth-chip";
  status.className = "fact-status";
  truth.dataset.truth = fact.truthKind;
  label.textContent = fact.label;
  value.textContent = fact.value;
  truth.textContent = truthLabel(fact.truthKind);
  status.textContent = fact.status ? fact.status.replaceAll("_", " ").toUpperCase() : "CAPTURED";
  button.append(label, value, status, truth);
  const hasSupport = fact.nodeIds.length > 0 || fact.edgeIds.length > 0;
  button.disabled = !hasSupport;
  if (hasSupport) button.addEventListener("click", () => focusFact(fact));
  return button;
}

function renderBrief() {
  const attention = attentionFact(state);
  $("attention-fact").replaceChildren(factButton(attention, "attention"));
  const pending = attention.id === "evidence-invalid" ? "invalid" : attention.status === "pending" ? "pending" : attention.value.replace(/\.$/, "") === "No unresolved Graphene decision" ? "clear" : "pending";
  document.querySelector(".attention").dataset.state = pending;
  $("brief-sections").hidden = pending === "invalid";
  if (pending === "invalid") return;
  const sections = reviewBriefFacts(state);
  for (const [key] of REVIEW_SECTIONS) {
    const list = $(`brief-${key}`);
    list.replaceChildren();
    for (const fact of sections[key]) {
      const item = document.createElement("li");
      item.append(factButton(fact, `brief-${key}`));
      list.append(item);
    }
  }
}

function renderStages() {
  $("stage-story").replaceChildren();
  for (const stage of stageGroups(state)) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.focusId = `stage:${stage.id}`;
    button.dataset.current = String(stage.id === state.reviewBrief.stage || stage.nodeIds.includes(currentId));
    button.textContent = stage.status ? `${stage.label} · ${stage.status}` : stage.label;
    button.disabled = stage.nodeIds.length === 0;
    if (stage.nodeIds.length) button.addEventListener("click", () => highlightElements(stage.nodeIds, []));
    item.append(button);
    $("stage-story").append(item);
  }
}

function renderList(view) {
  $("relationships").replaceChildren();
  const nodes = new Map(view.nodes.map((node) => [node.id, node]));
  for (const edge of view.edges) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    const relationship = edge.relationshipLabel ?? edge.relationshipClass?.replaceAll("_", " ") ?? "untyped explicit relationship";
    button.dataset.focusId = `relationship:${edge.id}`;
    button.textContent = `${nodes.get(edge.source).label} — ${relationship} / ${edge.kind} → ${nodes.get(edge.target).label}`;
    button.addEventListener("click", () => selectNode(edge.target));
    item.append(button);
    $("relationships").append(item);
  }
  $("relationships-empty").hidden = view.edges.length > 0;
  setText("relationship-count", `${view.edges.length} typed explicit relationship${view.edges.length === 1 ? "" : "s"}`);
}

function render(organize = false) {
  const focusId = document.activeElement?.dataset?.focusId;
  positions = statePositions(state, positions, organize);
  const storyIds = topologyScope === "decision" ? storyNodeIds(state, currentId, selectedId) : null;
  const view = visibleGraph(state, enabledGroups, storyIds);
  const elements = graphElements(view);
  if (!cy) {
    cy = cytoscape({
      container: $("canvas"), elements, layout: { name: "preset", fit: true, padding: 64 }, minZoom: 0.25, maxZoom: 2.4,
      wheelSensitivity: 0.25,
      style: [
        { selector: "node", style: { "background-color": "data(color)", "background-image": "data(badge)", "background-fit": "none", "background-width": "18px", "background-height": "18px", "background-position-x": "78%", "background-position-y": "20%", width: "data(size)", height: "data(size)", label: "data(displayLabel)", color: "#f7fafb", "font-size": 10, "font-weight": 650, "text-wrap": "wrap", "text-max-width": 100, "text-valign": "center", "text-halign": "center", "border-width": 4, "border-color": "data(borderColor)", "border-opacity": 0.9, "overlay-opacity": 0 } },
        { selector: "edge", style: { width: "data(width)", "line-color": "#71808a", "target-arrow-color": "#71808a", "target-arrow-shape": "triangle", "curve-style": "bezier", opacity: 0.68, "arrow-scale": 0.72 } },
        { selector: "edge.support", style: { "line-color": "#dbe7ec", "target-arrow-color": "#dbe7ec", "line-style": "solid" } },
        { selector: "edge.relationship-authorization", style: { "line-style": "dashed", width: 5, "line-color": "#d5ae73", "target-arrow-color": "#d5ae73" } },
        { selector: "edge.relationship-context_transfer", style: { "line-style": "dashed" } },
        { selector: "edge.relationship-membership", style: { "line-style": "dotted", opacity: 0.34 } },
        { selector: ".negative", style: { "border-color": "#ef746f", "border-style": "double", "border-width": 7 } },
        { selector: "node.truth-simulated_fixture", style: { "border-style": "dashed" } },
        { selector: "node.truth-human_attested", style: { "border-style": "double", "border-width": 7 } },
        { selector: "node.truth-policy_authoritative", style: { "border-style": "dotted", "border-width": 6 } },
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
  renderBrief();
  renderStages();
  renderList(view);
  $("canvas-state").hidden = view.nodes.length > 0;
  if (!view.nodes.length) setText("canvas-state", "No lineage matches the active filters.");
  const counts = projectionCounts(state, view, enabledGroups, storyIds);
  setText("count-total", counts.total);
  setText("count-visible", counts.visible);
  setText("count-filtered", counts.filtered);
  setText("count-collapsed", counts.collapsed);
  setText("bounds", `${counts.visible} / ${counts.total} nodes visible · ${counts.visibleEdges} / ${counts.totalEdges} edges · ${counts.filtered} filtered · ${counts.collapsed} collapsed · ${counts.omitted} omitted by cap`);
  setText("verified-head", formatHead());
  setText("run-state", state.invalidReason ? "Evidence invalid" : runState());
  $("timeline").max = String(deltaLog.length);
  $("timeline").value = String(replayIndex);
  setText("timeline-label", `${replayIndex} / ${deltaLog.length}`);
  if (state.invalidReason) showInvalid(state.invalidReason);
  else if (focusedFact) highlightElements(focusedFact.nodeIds, focusedFact.edgeIds);
  else if (selectedId) highlightVerifiedSupport(selectedId);
  pulseCurrent();
  restoreFocus(focusId);
}

function scheduleRender() {
  if (renderFrame !== null) return;
  renderFrame = requestAnimationFrame(() => { renderFrame = null; render(); });
}

function pulseCurrent() {
  if (prefersReducedMotion || pulsingId === currentId) return;
  clearInterval(pulseTimer);
  cy?.nodes().removeStyle("border-width");
  cy?.edges().removeStyle("opacity");
  pulsingId = currentId;
  let bright = false;
  pulseTimer = currentId ? setInterval(() => {
    bright = !bright;
    cy?.getElementById(currentId).style("border-width", bright ? 9 : 5);
    cy?.edges().filter((edge) => edge.target().id() === currentId).style("opacity", bright ? 1 : .65);
  }, 650) : null;
}

function highlightElements(nodeIds, edgeIds) {
  if (!cy) return;
  const nodes = new Set(nodeIds);
  const edges = new Set(edgeIds);
  cy.elements().removeClass("path").addClass("faded");
  for (const nodeId of nodes) cy.getElementById(nodeId).removeClass("faded").addClass("path");
  for (const edgeId of edges) cy.getElementById(edgeId).removeClass("faded").addClass("path");
}

function highlightVerifiedSupport(id) {
  const support = verifiedSupportPath(state, id);
  highlightElements(support.nodeIds, support.edgeIds);
}

function focusFact(fact) {
  focusedFact = fact;
  const nodeId = fact.nodeIds.find((id) => state.nodes.has(id));
  if (nodeId) selectNode(nodeId, false);
  highlightElements(fact.nodeIds, fact.edgeIds);
}
function clearPath() { cy?.elements().removeClass("faded path"); selectedId = null; focusedFact = null; }

async function selectNode(id, highlightSupport = true) {
  selectedId = id;
  if (highlightSupport) focusedFact = null;
  const node = state.nodes.get(id);
  if (!node) return;
  lastFocused = document.activeElement;
  lastFocusId = document.activeElement?.dataset?.focusId ?? null;
  cy.getElementById(id).select();
  if (highlightSupport) highlightVerifiedSupport(id);
  setText("drawer-kind", node.kind.replaceAll("_", " ").toUpperCase());
  setText("drawer-title", node.label);
  $("drawer-fields").replaceChildren();
  const fields = [
    ["Meaning", node.label], ["Status", node.status], ["Stage", node.stage ?? "not established by captured evidence"], ["Run", node.runId ?? "Shared across run family"],
    ["Sequence", node.sequence ?? "Not exposed"], ["Truth kind", truthLabel(node.truthKind)], ["Activity", node.activity],
    ["Source reference", node.sourceRef ?? "Not exposed"], ["Digest", node.digest ?? "Not exposed"], ...metadataLines(node.metadata),
  ];
  for (const [label, value] of fields) {
    const term = document.createElement("dt"); const description = document.createElement("dd");
    term.textContent = String(label).replaceAll("_", " "); description.textContent = String(value);
    $("drawer-fields").append(term, description);
  }
  const limitations = Array.isArray(node.metadata.limitations) && node.metadata.limitations.length
    ? node.metadata.limitations.join(" ")
    : "Node-specific limitations were not established by captured evidence.";
  setText("drawer-limitations", `${limitations} This bounded public view does not expose private artifact bytes, prompts, raw diffs, or test output.`);
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
  const replacement = lastFocusId ? [...document.querySelectorAll("[data-focus-id]")].find((element) => element.dataset.focusId === lastFocusId) : null;
  (replacement ?? lastFocused)?.focus();
}
function showInvalid(reason) {
  if (state) state.invalidReason ??= reason;
  clearInterval(pulseTimer);
  pulsingId = null;
  cy?.nodes().removeStyle("border-width");
  cy?.edges().removeStyle("opacity");
  $("invalid").hidden = false;
  setText("invalid-reason", reason);
  setText("connection", "Stopped");
  $("connection").dataset.state = "error";
  paused = true;
  renderBrief();
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
  currentId = state.currentId;
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
  currentId = deltaSubjectId(delta) ?? state.currentId ?? currentId;
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
      setText("connection", config.replay === true ? "Verified replay" : "Live");
      $("connection").dataset.state = config.replay === true ? "replay" : "live";
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
  currentId = state.currentId;
  setText("mode", config.replay === true ? VERIFIED_REPLAY_LABEL : (payload.meta?.mode ?? "LOCAL VIEWER"));
  setText("truth-label", config.replay === true ? VERIFIED_REPLAY_LABEL : (payload.meta?.truth_label ?? "Committed and verified v2 SQLite lineage"));
  setText("driver-truth", `Google ADK Runner: ${payload.meta?.adk_runner ?? config.adkRunner ?? (config.driver === "adk-fake" ? "real Google ADK 2.5.0" : "not used")} · Gemini calls: ${payload.meta?.gemini_calls ?? config.geminiCalls ?? 0} · Evidence source: ${payload.meta?.evidence_source ?? config.evidenceSource ?? "committed and verified v2 SQLite lineage"}`);
  setText("live-badge", config.replay === true ? "VERIFIED REPLAY" : live ? "LIVE" : "REPLAY");
  setText("connection", config.replay === true ? "Verified replay" : live ? "Live" : "Offline fixture");
  $("connection").dataset.state = config.replay === true || !live ? "replay" : "live";
  render(true);
  if (live) stream(); else updatePlay();
}

$("fit").addEventListener("click", () => cy?.fit(undefined, 62));
$("organize").addEventListener("click", () => render(true));
$("focus-current").addEventListener("click", () => currentId && cy?.animate({ center: { eles: cy.getElementById(currentId) }, zoom: 1.12 }, { duration: prefersReducedMotion ? 0 : 320 }));
$("evidence-path").addEventListener("click", () => selectedId ? highlightVerifiedSupport(selectedId) : currentId && highlightVerifiedSupport(currentId));
$("decision-view").addEventListener("click", () => { topologyScope = "decision"; $("decision-view").setAttribute("aria-pressed", "true"); $("full-view").setAttribute("aria-pressed", "false"); render(); cy?.fit(undefined, 62); });
$("full-view").addEventListener("click", () => { topologyScope = "full"; $("decision-view").setAttribute("aria-pressed", "false"); $("full-view").setAttribute("aria-pressed", "true"); render(); cy?.fit(undefined, 62); });
$("reset-filters").addEventListener("click", () => { enabledGroups.clear(); groups.forEach(([id]) => enabledGroups.add(id)); document.querySelectorAll("[data-group]").forEach((button) => button.setAttribute("aria-pressed", "true")); clearPath(); render(); });
$("drawer-close").addEventListener("click", closeDrawer);
$("play").addEventListener("click", () => { paused = !paused; if (live && !paused) { rebuild(deltaLog.length); pending = []; } updatePlay(); });
$("step").addEventListener("click", () => { paused = true; step(); });
$("speed").addEventListener("change", updatePlay);
$("timeline").addEventListener("input", (event) => { paused = true; rebuild(Number(event.target.value)); updatePlay(); });
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("drawer").hidden) closeDrawer();
  if (event.key === "Tab" && !$("drawer").hidden) { event.preventDefault(); $("drawer-close").focus(); return; }
  if (event.target !== $("canvas")) return;
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
