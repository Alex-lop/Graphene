import cytoscape from "./vendor/cytoscape.esm.min.mjs";
import {
  REVIEW_SECTIONS, applyDelta, applyThrough, attentionFact, createState,
  checkpointSummary, decisionReceipt, deltaSubjectId, evidenceInvalidResponse, geminiCallLabel, headSummary, outcomeLabel, projectionComposition, projectionCounts, relationshipReceipt, reviewBriefFacts,
  searchProvenance, stageGroups, statePositions, storyNodeIds, truthLabel,
  verifiedSupportPath, visibleGraph,
} from "./reducer.mjs";

const $ = (id) => document.getElementById(id);
const config = Object.freeze(window.__GRAPHENE_VIEWER__ ?? {});
const VERIFIED_REPLAY_LABEL = "VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION";
const groups = Object.freeze([
  ["agent", "Agent", "#6f8fa6"], ["tool", "Tool", "#a9b4bc"], ["evidence", "File / evidence", "#7b9bb2"],
  ["human", "Decision / memory", "#d5ae73"], ["policy", "Policy", "#d77b75"], ["test", "Test", "#73aa91"], ["handoff", "Handoff / outcome", "#9a88bd"],
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
  return ({ simulated_fixture: "SIM", human_attested: "HUMAN", policy_authoritative: "POLICY", runtime_observed: "OBS", server_derived: "DERIVED", evidence_bound: "BOUND", model_proposed: "MODEL" })[truthKind] ?? "UNKNOWN";
}

function restoreFocus(focusId) {
  if (!focusId) return;
  const target = [...document.querySelectorAll("[data-focus-id]")].find((element) => element.dataset.focusId === focusId);
  if (target) target.focus();
  else if (focusId.startsWith("search:")) $("provenance-search").focus();
}
function runState() {
  const outcome = outcomeLabel(state.reviewBrief.outcome_kind);
  if (outcome) return outcome;
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
      return ({
      group: "nodes",
      data: {
        ...node,
        displayLabel: `[${truthMark(node.truthKind)}] ${node.label}\n${node.displayStatus}`,
        size: 58,
        color: colorByGroup[node.group],
        borderColor: negative ? "#b42318" : "#475569",
      },
      position: positions.get(node.id),
      classes: [node.id === currentId ? "current" : "", negative ? "negative" : "", `truth-${node.truthKind}`].filter(Boolean).join(" "),
    }); }),
    ...view.edges.map((edge) => ({
      group: "edges",
      data: { ...edge, width: edge.supportPath ? 3 : 2 },
      classes: [edge.target === currentId ? "current" : "", edge.relationshipClass ? `relationship-${edge.relationshipClass}` : "relationship-untyped", edge.supportPath ? "support" : ""].filter(Boolean).join(" "),
    })),
  ];
}

function factButton(fact, prefix) {
  const hasSupport = fact.nodeIds.length > 0 || fact.edgeIds.length > 0;
  const button = document.createElement(hasSupport ? "button" : "div");
  const label = document.createElement("span");
  const value = document.createElement("span");
  const truth = document.createElement("span");
  const status = document.createElement("span");
  if (hasSupport) button.type = "button";
  button.className = "brief-fact";
  if (hasSupport) button.dataset.focusId = `${prefix}:${fact.id}`;
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
  if (hasSupport) button.addEventListener("click", () => focusFact(fact));
  return button;
}

function renderBrief() {
  const attention = attentionFact(state);
  $("attention-fact").replaceChildren(factButton(attention, "attention"));
  const pending = attention.id === "evidence-invalid" ? "invalid" : attention.status === "pending" || Number(attention.metadata?.pending_count) > 0 ? "pending" : "clear";
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

function renderDecisionReceipt() {
  const receipt = decisionReceipt(state);
  const labels = { required: "Decision required", recorded: "Terminal outcome recorded", not_open: "No decision gate open yet" };
  setText("receipt-gate", labels[receipt.state]);
  setText("receipt-outcome", receipt.outcomeKind.replaceAll("_", " "));
  setText("receipt-limits", receipt.explicitLimitCount);
  $("path-bindings").replaceChildren();
  const paths = receipt.paths.length ? receipt.paths : [{ path: "Exact changed paths not established", boundToPassingReceipt: false }];
  for (const item of paths) {
    const row = document.createElement("li");
    const path = document.createElement("code");
    const status = document.createElement("span");
    path.textContent = item.path;
    status.textContent = item.boundToPassingReceipt ? "Passing fixed-test receipt bound" : "Bound passing receipt not established";
    status.dataset.state = item.boundToPassingReceipt ? "bound" : "gap";
    row.append(path, status);
    $("path-bindings").append(row);
  }
}

function renderFocusSummary() {
  if (!focusedFact) { $("focus-summary").hidden = true; return; }
  $("focus-summary").hidden = false;
  setText("focus-title", focusedFact.value);
  setText("focus-counts", `${focusedFact.nodeIds.length} record${focusedFact.nodeIds.length === 1 ? "" : "s"} · ${focusedFact.edgeIds.length} explicit relationship${focusedFact.edgeIds.length === 1 ? "" : "s"}`);
}

function renderStages() {
  $("stage-story").replaceChildren();
  for (const stage of stageGroups(state)) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.focusId = `stage:${stage.id}`;
    button.dataset.current = String(stage.id === state.reviewBrief.stage || stage.nodeIds.includes(currentId));
    if (button.dataset.current === "true") button.setAttribute("aria-current", "step");
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
    button.addEventListener("click", () => selectEdge(edge.id));
    item.append(button);
    $("relationships").append(item);
  }
  $("relationships-empty").hidden = view.edges.length > 0;
  setText("relationship-count", `${view.edges.length} typed explicit relationship${view.edges.length === 1 ? "" : "s"}`);
}

function chooseSearchResult(result) {
  if (result.type === "node") selectNode(result.id);
  else if (result.type === "relationship") selectEdge(result.id);
  else if (result.fact) focusFact(result.fact);
}

function renderSearch() {
  const match = searchProvenance(state, $("provenance-search").value);
  $("search-results").replaceChildren();
  $("search-panel").hidden = !match.query;
  $("search-clear").hidden = !match.query;
  if (!match.query) return;
  const shown = match.results.length;
  setText("search-status", match.total
    ? `${match.truncated ? `Showing ${shown} of ` : ""}${match.total} match${match.total === 1 ? "" : "es"} in this checkpoint.`
    : `No captured evidence matches “${match.query}” in this checkpoint.`);
  for (const result of match.results) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const label = document.createElement("strong");
    const detail = document.createElement("span");
    button.type = "button";
    button.dataset.focusId = `search:${result.type}:${result.id}`;
    label.textContent = result.label;
    detail.textContent = `${result.type} · ${result.detail}`;
    button.append(label, detail);
    button.addEventListener("click", () => chooseSearchResult(result));
    item.append(button);
    $("search-results").append(item);
  }
}

function receiptCount(value) {
  return value === null ? "not established" : `${value} captured receipt${value === 1 ? "" : "s"}`;
}

function inspectorButton(label, value, fact) {
  const hasSupport = fact && (fact.nodeIds.length || fact.edgeIds.length);
  const row = document.createElement(hasSupport ? "button" : "div");
  const name = document.createElement("strong");
  const detail = document.createElement("span");
  if (hasSupport) row.type = "button";
  name.textContent = label;
  detail.textContent = value;
  row.append(name, detail);
  if (hasSupport) {
    row.dataset.focusId = `inspector:${fact.id}`;
    row.addEventListener("click", () => focusFact(fact));
  }
  return row;
}

function renderInspector() {
  const composition = projectionComposition(state);
  const sections = reviewBriefFacts(state);
  const current = state.nodes.get(currentId);
  $("inspector-body").hidden = Boolean(state.invalidReason);
  setText("inspector-state", state.invalidReason
    ? "Evidence is invalid. Prior checkpoint details are hidden."
    : `${composition.runs.verifiedHeads} verified head${composition.runs.verifiedHeads === 1 ? "" : "s"} · ${composition.runs.visibleRunRecords} projected run record${composition.runs.visibleRunRecords === 1 ? "" : "s"}.`);
  setText("inspector-summary", state.invalidReason ? "Evidence invalid" : `${composition.runs.verifiedHeads} head${composition.runs.verifiedHeads === 1 ? "" : "s"}`);
  if (state.invalidReason) return;
  setText("inspector-anchor", current?.label ?? "not established");
  setText("inspector-stage", state.reviewBrief.stage?.replaceAll("_", " ") ?? current?.stage?.replaceAll("_", " ") ?? "not established");
  setText("inspector-digest", state.graphSha256 ? `sha256:${state.graphSha256}` : "not established");

  const meters = [
    ["established", composition.brief.established], ["pending", composition.brief.pending],
    ["historical", composition.brief.historical], ["limits", composition.brief.gaps],
  ];
  for (const [id, value] of meters) {
    const meter = $(`meter-${id}`);
    meter.max = Math.max(1, composition.brief.total);
    meter.value = value;
    setText(`count-${id}`, `${value} / ${composition.brief.total}`);
  }

  const included = sections.context.find((fact) => fact.id === "context:included");
  const opened = sections.context.find((fact) => fact.id === "context:opened");
  const denied = sections.evidence.find((fact) => fact.id.startsWith("evidence:handoff_denial:") && ["established", "historical"].includes(fact.status));
  $("context-receipts").replaceChildren(
    inspectorButton("Compiled", receiptCount(composition.context.compiledRecords), included),
    inspectorButton("Injected", receiptCount(composition.context.injectedRecords), included),
    inspectorButton("Explicitly opened", receiptCount(composition.context.openedRecords), opened),
    inspectorButton("Excluded handoffs", `${composition.context.projectedDeniedHandoffs} projected · ${composition.context.deniedHandoffsWithExplicitZeroDispatch} with explicit zero dispatch`, denied),
  );
  $("memory-scopes").replaceChildren();
  if (!composition.context.memoryScopes.length) {
    const item = document.createElement("li"); item.textContent = "not established by captured evidence"; $("memory-scopes").append(item);
  } else for (const scope of composition.context.memoryScopes) {
    const item = document.createElement("li");
    item.append(inspectorButton(scope.scope_id ?? "unnamed scope", `revision ${scope.revision ?? "not exposed"} · ${(scope.path_globs ?? []).join(", ") || "paths not exposed"}`, included));
    $("memory-scopes").append(item);
  }

  $("run-heads").replaceChildren();
  const heads = [...state.heads].sort((left, right) => Number(right.run_id === state.rootRunId) - Number(left.run_id === state.rootRunId) || String(left.run_id).localeCompare(String(right.run_id)));
  for (const head of heads) {
    const item = document.createElement("li");
    const run = state.nodes.get(`run:${head.run_id}`);
    if (run) {
      const button = document.createElement("button");
      const label = document.createElement("strong");
      const detail = document.createElement("span");
      button.type = "button";
      button.dataset.focusId = `inspector-run:${head.run_id}`;
      label.textContent = `${run.label}${head.run_id === state.rootRunId ? " · root" : ""}`;
      detail.textContent = `${run.displayStatus} · seq ${head.seq ?? "—"} · ${head.run_id}`;
      button.append(label, detail);
      button.addEventListener("click", () => selectNode(run.id));
      item.append(button);
    } else item.textContent = `${head.run_id} · seq ${head.seq ?? "—"}`;
    $("run-heads").append(item);
  }
  if (!heads.length) { const item = document.createElement("li"); item.textContent = "No verified run head is available."; $("run-heads").append(item); }
  setText("run-omissions", `${composition.runs.omittedFamilyRuns} run${composition.runs.omittedFamilyRuns === 1 ? "" : "s"} omitted by the family cap.`);
}

function render(organize = false) {
  const focusId = document.activeElement?.dataset?.focusId;
  if (selectedId && !state.nodes.has(selectedId)) selectedId = null;
  if (focusedFact) focusedFact = [attentionFact(state), ...Object.values(reviewBriefFacts(state)).flat()].find((fact) => fact.id === focusedFact.id) ?? null;
  positions = statePositions(state, positions, organize);
  const storyIds = topologyScope === "decision" ? storyNodeIds(state, currentId, selectedId, focusedFact) : null;
  const view = visibleGraph(state, enabledGroups, storyIds);
  const elements = graphElements(view);
  if (!cy) {
    cy = cytoscape({
      container: $("canvas"), elements, layout: { name: "preset", fit: true, padding: 64 }, minZoom: 0.25, maxZoom: 2.4,
      wheelSensitivity: 0.25,
      style: [
        { selector: "node", style: { "background-color": "data(color)", width: "data(size)", height: "data(size)", label: "data(displayLabel)", color: "#172026", "font-size": 9, "font-weight": 700, "text-wrap": "wrap", "text-max-width": 105, "text-valign": "center", "text-halign": "center", "border-width": 4, "border-color": "data(borderColor)", "border-opacity": 0.9, "overlay-opacity": 0 } },
        { selector: "edge", style: { width: "data(width)", "line-color": "#64748b", "target-arrow-color": "#64748b", "target-arrow-shape": "triangle", "curve-style": "bezier", opacity: 0.72, "arrow-scale": 0.72 } },
        { selector: "edge.support", style: { "line-color": "#1d4ed8", "target-arrow-color": "#1d4ed8", "line-style": "solid" } },
        { selector: "edge.relationship-authorization", style: { "line-style": "dashed", width: 5, "line-color": "#8a5a00", "target-arrow-color": "#8a5a00" } },
        { selector: "edge.relationship-context_transfer", style: { "line-style": "dashed" } },
        { selector: "edge.relationship-membership", style: { "line-style": "dotted", opacity: 0.34 } },
        { selector: ".negative", style: { "border-color": "#b42318", "border-style": "double", "border-width": 7 } },
        { selector: "node.truth-simulated_fixture", style: { "border-style": "dashed" } },
        { selector: "node.truth-human_attested", style: { "border-style": "double", "border-width": 7 } },
        { selector: "node.truth-policy_authoritative", style: { "border-style": "dotted", "border-width": 6 } },
        { selector: ".current", style: { "border-color": "#0f172a", "line-color": "#0f172a", "target-arrow-color": "#0f172a", "z-index": 10 } },
        { selector: ":selected", style: { "border-color": "#1d4ed8", "border-width": 7 } },
        { selector: ".faded", style: { opacity: 0.12, "text-opacity": 0.08 } },
        { selector: ".path", style: { opacity: 1, "line-color": "#1d4ed8", "target-arrow-color": "#1d4ed8", "z-index": 20 } },
      ],
    });
    cy.on("tap", "node", (event) => selectNode(event.target.id()));
    cy.on("tap", "edge", (event) => selectEdge(event.target.id()));
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
  renderSearch();
  renderInspector();
  renderDecisionReceipt();
  renderFocusSummary();
  renderStages();
  renderList(view);
  $("canvas-state").hidden = view.nodes.length > 0;
  if (!view.nodes.length) setText("canvas-state", state.nodes.size ? "No lineage matches the active filters." : "No committed lineage records are available.");
  const counts = projectionCounts(state, view, enabledGroups, storyIds);
  setText("count-total", counts.total);
  setText("count-visible", counts.visible);
  setText("count-filtered", counts.filtered);
  setText("count-collapsed", counts.collapsed);
  setText("bounds", `${counts.visible} / ${counts.total} records visible · ${counts.visibleEdges} / ${counts.totalEdges} relationships · ${counts.filtered} filtered · ${counts.collapsed} collapsed · ${counts.omitted} omitted by cap. Sequence does not prove causality.`);
  setText("verified-head", formatHead());
  setText("run-state", state.invalidReason ? "Evidence invalid" : runState());
  const checkpoint = checkpointSummary(replayIndex, deltaLog.length);
  $("timeline").max = String(deltaLog.length);
  $("timeline").value = String(replayIndex);
  $("timeline").setAttribute("aria-valuetext", `Checkpoint ${checkpoint.current} of ${checkpoint.total}`);
  setText("timeline-label", `${checkpoint.current} of ${checkpoint.total}`);
  $("latest-checkpoint").disabled = checkpoint.latest;
  if (state.invalidReason) showInvalid(state.invalidReason);
  else if (focusedFact) highlightElements(focusedFact.nodeIds, focusedFact.edgeIds);
  else if (selectedId) highlightVerifiedSupport(selectedId);
  restoreFocus(focusId);
}

function scheduleRender() {
  if (renderFrame !== null) return;
  renderFrame = requestAnimationFrame(() => { renderFrame = null; render(); });
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
  selectedId = null;
  render();
}
function clearPath() {
  const changed = selectedId !== null || focusedFact !== null;
  cy?.elements().removeClass("faded path"); selectedId = null; focusedFact = null;
  if (changed && topologyScope === "decision") render(); else renderFocusSummary();
}

function openDrawer(kind, title, fields, limitations, status) {
  lastFocused = document.activeElement;
  lastFocusId = document.activeElement?.dataset?.focusId ?? null;
  setText("drawer-kind", kind);
  setText("drawer-title", title);
  $("drawer-fields").replaceChildren();
  for (const [label, value] of fields) {
    const term = document.createElement("dt"); const description = document.createElement("dd");
    term.textContent = String(label).replaceAll("_", " "); description.textContent = String(value ?? "Not exposed");
    $("drawer-fields").append(term, description);
  }
  setText("drawer-limitations", limitations);
  setText("drawer-state", status);
  $("drawer").hidden = false;
  $("drawer-close").focus();
}

function selectEdge(id) {
  const receipt = relationshipReceipt(state, id);
  if (!receipt) return;
  openDrawer("EXPLICIT RELATIONSHIP", `${receipt.source} → ${receipt.target}`, [
    ["Source", receipt.source], ["Relationship class", receipt.relationshipClass], ["Recorded kind", receipt.kind], ["Target", receipt.target],
    ["Decision support path", receipt.supportPath ? "Included" : "Not included"], ["Run", receipt.runId], ["Sequence", receipt.sequence],
    ["Event", receipt.eventId], ["Source reference", receipt.sourceRef], ["Digest", receipt.digest],
  ], "This receipt records an explicit relationship; it does not establish causality, correctness, relevance, or hidden reasoning. Private artifact bytes remain outside this public view.", "Showing a sanitized relationship receipt.");
}

async function selectNode(id, highlightSupport = true) {
  selectedId = id;
  if (highlightSupport) focusedFact = null;
  renderFocusSummary();
  const node = state.nodes.get(id);
  if (!node) return;
  cy.getElementById(id).select();
  if (highlightSupport) highlightVerifiedSupport(id);
  const fields = [
    ["Meaning", node.label], ["Status", node.displayStatus], ["Stage", node.stage ?? "not established by captured evidence"], ["Run", node.runId ?? "Shared across run family"],
    ["Sequence", node.sequence ?? "Not exposed"], ["Evidence class", truthLabel(node.truthKind)],
    ["Source reference", node.sourceRef ?? "Not exposed"], ["Digest", node.digest ?? "Not exposed"], ...metadataLines(node.metadata),
  ];
  const limitations = Array.isArray(node.metadata.limitations) && node.metadata.limitations.length
    ? node.metadata.limitations.join(" ")
    : "Node-specific limitations were not established by captured evidence.";
  openDrawer(node.kind.replaceAll("_", " ").toUpperCase(), node.label, fields, `${limitations} This bounded public view does not expose private artifact bytes, prompts, raw diffs, or test output.`, "Showing sanitized projection data. Loading bounded server detail…");
  if (live && state.rootRunId) {
    try {
      const response = await request(rootPath(`/nodes/${encodeURIComponent(id)}`));
      if (!response.ok) throw new Error(`detail unavailable (${response.status})`);
      const detail = await response.json();
      if (selectedId !== id) return;
      const detailDigest = detail.source_ref?.sha256;
      setText("drawer-state", detailDigest && node.digest && detailDigest !== node.digest ? "Server detail digest differs; reverify authoritative lineage before relying on it." : "Bounded detail matches the selected public reference.");
    } catch (error) { if (selectedId === id) setText("drawer-state", `Public summary shown; ${error.message}.`); }
  } else setText("drawer-state", "Checked-in sanitized replay detail.");
}

function closeDrawer() {
  $("drawer").hidden = true;
  clearPath();
  const replacement = lastFocusId ? [...document.querySelectorAll("[data-focus-id]")].find((element) => element.dataset.focusId === lastFocusId) : null;
  (replacement ?? lastFocused)?.focus();
}
function dismissTransientView() {
  const drawerHadFocus = $("drawer").contains(document.activeElement);
  $("drawer").hidden = true;
  selectedId = null;
  focusedFact = null;
  if (drawerHadFocus) queueMicrotask(() => $("canvas").focus());
}
function showInvalid(reason) {
  if (state) state.invalidReason ??= reason;
  dismissTransientView();
  $("invalid").hidden = false;
  setText("invalid-reason", reason);
  setText("connection", "Stopped");
  $("connection").dataset.state = "error";
  paused = true;
  $("provenance-search").value = "";
  renderSearch();
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
  if (index !== replayIndex) dismissTransientView();
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
  dismissTransientView();
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
      setText("connection", config.replay === true ? "Verified replay" : "Watching committed records");
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
  if (config.replay === true) {
    const response = await fetch(config.replayUrl ?? "/static/replay.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`replay unavailable (${response.status})`);
    payload = await response.json();
    initialSnapshot = payload.snapshot;
    deltaLog = payload.deltas ?? [];
    live = false;
    paused = true;
    replayIndex = deltaLog.length;
    state = applyThrough(initialSnapshot, deltaLog, replayIndex);
  } else if (config.rootRunId) {
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
    paused = true;
    replayIndex = deltaLog.length;
    state = applyThrough(initialSnapshot, deltaLog, replayIndex);
  }
  state ??= createState(initialSnapshot);
  currentId = state.currentId;
  setText("mode", config.replay === true ? VERIFIED_REPLAY_LABEL : (payload.meta?.mode ?? "LOCAL VIEWER"));
  setText("truth-label", config.replay === true ? VERIFIED_REPLAY_LABEL : (payload.meta?.truth_label ?? "Committed and verified v2 SQLite lineage"));
  setText("driver-truth", `Google ADK Runner: ${payload.meta?.adk_runner ?? config.adkRunner ?? (config.driver === "adk-fake" ? "real Google ADK 2.5.0" : "not used")} · ${geminiCallLabel(payload.meta?.gemini_calls, config.geminiCalls)} · Evidence source: ${payload.meta?.evidence_source ?? config.evidenceSource ?? "committed and verified v2 SQLite lineage"}`);
  setText("live-badge", config.replay === true ? "VERIFIED REPLAY" : live ? "EVENT FEED" : "EVENT HISTORY");
  setText("connection", config.replay === true ? "Verified replay" : live ? "Watching committed records" : "Offline fixture");
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
$("clear-focus").addEventListener("click", clearPath);
$("drawer-close").addEventListener("click", closeDrawer);
$("search-form").addEventListener("submit", (event) => { event.preventDefault(); $("search-results").querySelector("button")?.focus(); });
$("provenance-search").addEventListener("input", renderSearch);
$("provenance-search").addEventListener("keydown", (event) => { if (event.key === "ArrowDown") { event.preventDefault(); $("search-results").querySelector("button")?.focus(); } });
$("search-clear").addEventListener("click", () => { $("provenance-search").value = ""; renderSearch(); $("provenance-search").focus(); });
$("play").addEventListener("click", () => { paused = !paused; if (live && !paused) { rebuild(deltaLog.length); pending = []; } updatePlay(); });
$("step").addEventListener("click", () => { paused = true; step(); });
$("latest-checkpoint").addEventListener("click", () => { paused = true; rebuild(deltaLog.length); updatePlay(); });
$("speed").addEventListener("change", updatePlay);
$("timeline").addEventListener("input", (event) => { paused = true; rebuild(Number(event.target.value)); updatePlay(); });
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("drawer").hidden) { closeDrawer(); return; }
  if (event.key === "Escape" && $("provenance-search").value) { $("provenance-search").value = ""; renderSearch(); $("provenance-search").focus(); return; }
  if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey && !["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) { event.preventDefault(); $("provenance-search").focus(); return; }
  if (event.target !== $("canvas")) return;
  if (!cy || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key)) return;
  if (event.key === "Enter" && selectedId) { selectNode(selectedId); return; }
  if (event.key === "Enter") return;
  const nodes = cy.nodes().sort((left, right) => left.id().localeCompare(right.id()));
  if (!nodes.length) return;
  event.preventDefault();
  const direction = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
  const currentIndex = nodes.findIndex((node) => node.id() === selectedId);
  const index = currentIndex < 0 ? (direction > 0 ? 0 : nodes.length - 1) : (currentIndex + direction + nodes.length) % nodes.length;
  selectedId = nodes[index].id();
  cy.nodes().unselect(); cy.getElementById(selectedId).select();
  const node = state.nodes.get(selectedId);
  setText("selection-status", `${index + 1} of ${nodes.length}: ${node.kind}, ${node.label}, status ${node.displayStatus}, evidence class ${truthLabel(node.truthKind)}`);
});

start().catch((error) => {
  setText("canvas-state", `Viewer unavailable: ${error.message}`);
  setText("connection", "Error"); $("connection").dataset.state = "error";
});
