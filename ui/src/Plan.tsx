// The plan: what will be done, by whom, inside which paths, and what it waits for. Every position
// comes from src/graphene_map/plan_view.py, for the graph and for the tree alike; the page adds the
// gutter it draws lane names in, and a pan and a zoom where a drawing is larger than its pane. Every control here changes what an agent may do, through one function in plan.py,
// and where that mechanism stops the sentence saying so is printed next to the control.

import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { useEffect, useRef, useState, type FormEvent, type ReactElement, type ReactNode } from "react";

import { PAD_X, PAD_Y, STATE, STATE_COLOUR, clip, clock, graphWidth, stamp, treeWidth, why, type Layout, type Mode, type View } from "./model";
import type { Board, Fork, Plan, PlanEdge, PlanNode, Shown } from "./types";

const CHAR = 6.4;
const SMALL = 5.9;

/** A plan edit: the server's own sentence when it refused, null when it went through. */
export type Write = (op: string, body: unknown) => Promise<string | null>;

const lines = (text: string): string[] =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

const words = (text: string): string[] => text.split(/[\s,]+/).filter(Boolean);

/** A sub-goal's progress, in the leaves beneath it: the same count the terminal prints. */
const rolled = (node: PlanNode): string => `${node.leaves_done}/${node.leaves_total} done`;

/** A fork's colour, as the terminal's: running is the executor's, passed is done work, any other end
 * is nobody's move. */
const forkColour = (state: string): string => (state === "passed" ? "var(--pass)" : state === "running" ? "var(--a1)" : "var(--neutral)");

/** What a fork's sandbox took, when it ran in one; nothing while it runs, as the terminal's record: the
 * row it wrote as it began carries the operations it started with. */
const sandboxed = (fork: Fork): string =>
  fork.ops === undefined || fork.state === "running" ? "" : ` · sandbox ${fork.checkpoint === "forked" ? "forked from the checkpoint" : "made"}, ${fork.ops} operations, ${(fork.seconds ?? 0).toFixed(1)} s`;

const Shape = ({ state, colour }: { state: Shown; colour: string }): ReactElement => {
  switch (state) {
    case "sub-goal":
      return <path d="M-4,-5.5V5.5M-4,-2H4.5M-4,3H4.5" fill="none" stroke={colour} strokeWidth={1.6} strokeLinecap="round" />;
    case "done":
      return <path d="M-5,0L-1.5,4L5,-4.5" fill="none" stroke={colour} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />;
    case "running":
      return <path d="M-4,-5L5,0L-4,5Z" fill={colour} />;
    case "review":
      return <path d="M0,-5.5L5.5,0L0,5.5L-5.5,0Z" fill={colour} />;
    case "proposed":
      return <rect x={-4.5} y={-4.5} width={9} height={9} fill="none" stroke={colour} strokeWidth={1.6} strokeDasharray="2.5 1.8" />;
    case "waiting":
      return <circle r={4.4} fill="none" stroke={colour} strokeWidth={1.8} />;
    default:
      return <circle r={4.8} fill={colour} />;
  }
};

// The record screen is drawn from Claude Code's sessions only. A run by any other executor has none,
// and what it did is in each node's own record, on the plan: a screen of zeros would say otherwise.
const UNRECORDED = "no Claude Code session was recorded in this repo; what each executor did is in its node's record, on the plan";

export function Toggle({ view, onView, planned, recorded }: { view: View; onView: (v: View) => void; planned: number; recorded: number }): ReactElement {
  return (
    <div className="toggle" role="group" aria-label="what the page shows">
      <button type="button" className={view === "plan" ? "on" : ""} aria-pressed={view === "plan"} disabled={planned === 0} onClick={() => onView("plan")}>
        the plan
      </button>
      <button
        type="button"
        className={view === "record" ? "on" : ""}
        aria-pressed={view === "record"}
        disabled={recorded === 0}
        title={recorded === 0 ? UNRECORDED : undefined}
        onClick={() => onView("record")}
      >
        the record
      </button>
    </div>
  );
}

/** The plan's leaves, the unit bare `graphene` counts in: a sub-goal is done when its leaves are. */
const leavesOf = (plan: Plan): PlanNode[] => plan.nodes.filter((n) => !n.sub_goal && !n.aside);

/** The plan's size as bare `graphene` says it: `3 leaves, 1 done, 0 running`. */
export const size = (plan: Plan): string => {
  const leaves = leavesOf(plan);
  const n = (state: string) => leaves.filter((l) => l.state === state).length;
  return `${leaves.length} lea${leaves.length === 1 ? "f" : "ves"}, ${n("done")} done, ${n("running")} running`;
};

/** Why this page cannot change the plan, and where it is changed instead: said once, on the overview. An
 * export carries no token; a page served to an agent's shell has one and cannot write with it. */
const READ_ONLY = {
  copy: "This page is a copy, written by graphene ui --export. The plan changes in its repository: graphene watch, graphene board, or graphene ui started there by the person.",
  agent: "This page was opened from an agent's shell. The person changes the plan from their own terminal: graphene watch, graphene board, or graphene ui started there.",
};

export function PlanHeader({ plan, view, onView, recorded }: { plan: Plan; view: View; onView: (v: View) => void; recorded: number }): ReactElement {
  return (
    <header className="header" data-testid="header">
      <div className="run">
        <h1>{plan.repo || "this repo"}</h1>
        <Toggle view={view} onView={onView} planned={plan.nodes.length} recorded={recorded} />
        <span data-testid="size">{size(plan)}</span>
      </div>
      {/* the root of the tree, in the person's words: why any of the rest is being done */}
      <p className="goal" data-testid="goal" title={plan.goal}>
        {plan.goal || <span className="muted">no goal yet — `graphene plan goal &lsquo;why any of this is being done&rsquo;`</span>}
      </p>
      <div className="badges">
        {plan.paused && <span className="badge warn">paused: nothing starts and no write is refused</span>}
        {!plan.writable && <span className="badge">read-only</span>}
      </div>
    </header>
  );
}

/** What is on the person right now, above everything else: the screen is prospective, and this is
 * the part of it that will not move until they touch it. */
export function PlanStrip({ plan, onPick, write }: { plan: Plan; onPick: (id: string) => void; write: Write }): ReactElement {
  const [said, setSaid] = useState<string | null>(null);
  const waiting = plan.waiting_on_person;
  const asked = plan.board.open.length;
  const board = asked > 0 ? ` + ${asked} on the board` : "";
  return (
    <section className="strip plan-strip" data-testid="waiting-on-you">
      <h3>{waiting.length > 0 || asked > 0 ? `waiting on you (${waiting.length}${board})` : "nothing is waiting on you"}</h3>
      <ul>
        {waiting.map((item) => (
          <li key={item.id}>
            <button type="button" className="chip" data-waiting={item.id} onClick={() => onPick(item.id)}>
              <b>{item.id}</b> {item.why}
            </button>
          </li>
        ))}
        {waiting.length === 0 && <li className="muted">{asked > 0 ? "no node: only the board." : "every node is with an agent, or done."}</li>}
      </ul>
      <p className="muted forecast">
        left alone, agents can reach: {plan.forecast.runs.join(", ") || "nothing"}
        {plan.forecast.waits.map((wait) => (
          <span key={wait.id} className="waits">
            {wait.id} will wait: {wait.why.map((reason) => (reason.startsWith(`${wait.id} `) ? `it${reason.slice(wait.id.length)}` : reason)).join("; ")}
          </span>
        ))}
      </p>
      <PlanBoard board={plan.board} />
      {plan.all_done && !plan.paused && (
        <p className="muted">
          every node is done, and the plan is still in force: agents write nothing here until you add a node, archive it or
          pause it.
        </p>
      )}
      {plan.loose.length > 0 && (
        <p className="error" data-testid="loose">
          changed while no node owned it: {plan.loose.slice(0, 8).join(", ")}
          {plan.loose.length > 8 ? ` and ${plan.loose.length - 8} more` : ""}. Agents cannot start a node over it; put it
          back, or accept it as it is.
        </p>
      )}
      {plan.writable && (
        <p className="acts">
          <button type="button" onClick={async () => setSaid(await write(plan.paused ? "resume" : "pause", {}))}>
            {plan.paused ? "resume the plan" : "pause the plan"}
          </button>
          <button type="button" onClick={async () => setSaid(await write("archive", {}))}>
            archive finished nodes
          </button>
          {plan.loose.length > 0 && (
            <button type="button" onClick={async () => setSaid(await write("ack", {}))}>
              accept those changes as they are
            </button>
          )}
          {said && <span className="error">{said}</span>}
        </p>
      )}
    </section>
  );
}

/** The board, as the terminal's rows read it (decision 84): the standing conditions' one line, each open
 * item with its kind as a verb, its default, its options and what it is about, and what is settled,
 * parked or dropped folded into one count that opens. The page answers nothing on it: the terminal does. */
export function PlanBoard({ board }: { board: Board }): ReactElement | null {
  if (!board.standing && board.open.length === 0 && board.folded.length === 0) return null;
  return (
    <div className="board" data-testid="board">
      {board.standing && (
        <p className="muted standing" data-testid="standing">
          {board.standing}
        </p>
      )}
      {board.open.length > 0 && (
        <ul className="board-items">
          {board.open.map((item) => (
            <li key={item.id} data-item={item.id}>
              <span className="kind">◇ {item.word}</span>
              <span className="what">{item.text}</span> <b>{item.id}</b>
              <span className="muted detail">
                {[
                  item.default ? `default: ${item.default}` : "",
                  ...item.options.map((option, i) => `${i + 1}: ${option}`),
                  item.about ? `about ${item.about}` : "",
                  `put up by ${item.by}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      )}
      {board.folded.length > 0 && (
        <details className="board-fold" data-testid="board-fold">
          <summary>
            {board.folded.some((it) => it.word !== "parked" && it.word !== "dropped") ? "✓" : "◌"} {board.counts}
          </summary>
          <ul>
            {board.folded.map((item) => (
              <li key={item.id} data-item={item.id}>
                <span className="kind">{item.word}</span> <b>{item.id}</b> <span className="what">{item.said}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {board.open.length > 0 && <p className="muted">answered in the terminal: graphene board, or y and 1-9 on the item in graphene watch</p>}
    </div>
  );
}

/** The plan as a tree: a node under the one it helps achieve, indented by the depth Python computed.
 * A sub-goal carries no scope and no check of its own, so it says how many of the leaves beneath it
 * are done. Leaves made from a prompt and already finished fold into one line, as the terminal folds
 * them: they are a record of what was typed, not work anyone is waiting on. Under a leaf that forked
 * are its forks, the tree of sandboxes: each fork's model, how it ended and why, the winner marked;
 * a fork is not a node, so picking one picks its leaf. */
export function PlanTree({ plan, picked, onPick }: { plan: Plan; picked: string | null; onPick: (id: string) => void }): ReactElement {
  const shown = plan.nodes.filter((n) => !(n.aside && n.state === "done"));
  const folded = plan.nodes.length - shown.length;
  return (
    <section className="tree" data-testid="tree">
      <ul>
        {shown.map((node) => (
          <li key={node.id} data-tree={node.id} data-depth={node.depth} style={{ paddingLeft: 12 + node.depth * 20 }}>
            <button type="button" className={node.id === picked ? "row on" : "row"} onClick={() => onPick(node.id)}>
              <span className="state" style={{ color: STATE_COLOUR[node.display_state] }}>
                {STATE[node.display_state]}
              </span>
              <b>{node.id}</b>
              <span className="what">{node.title}</span>
              <span className="muted">
                {node.sub_goal ? rolled(node) : node.scope.join(", ")}
                {node.aside ? " · typed into a session" : ""}
              </span>
            </button>
            {node.forks.length > 0 && (
              <ul className="forks" data-forks={node.id}>
                {node.forks.map((fork) => (
                  <li key={fork.fork} data-fork={fork.fork} data-state={fork.state}>
                    <button type="button" className={fork.state === "passed" ? "row fork won" : "row fork"} onClick={() => onPick(node.id)}>
                      <span className="state" style={{ color: forkColour(fork.state) }}>
                        {fork.state === "passed" ? "✓ won" : fork.state}
                      </span>
                      <b>
                        fork {fork.fork} of {fork.of}
                      </b>
                      <span className="what">{fork.model.split("/").pop()}</span>
                      <span className="muted">
                        {fork.why}
                        {sandboxed(fork)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      {folded > 0 && (
        <p className="muted done-asides">
          ✓ {folded} done from a prompt, each with its record (`graphene plan --all` lists them)
        </p>
      )}
    </section>
  );
}

const BUTTONS = ["auto", "outline", "tree", "graph"] as const;

/** At once counts proposals whose needs are done (decision 87): said beside the number, so it never
 * reads against "left alone, agents can reach: nothing" while nothing is accepted. */
const onceAccepted = (plan: Plan): string => {
  const proposed = new Set(plan.nodes.filter((n) => n.state === "proposed").map((n) => n.id));
  const later = plan.at_once.filter((id) => proposed.has(id)).length;
  if (later === 0) return "";
  return later === plan.at_once.length ? ", once accepted" : ` (${later} once accepted)`;
};

/** Which way the plan is drawn, the record's toggle again, with auto to give the choice back to the
 * plan's shape. Under it, the plan's own two facts in words, whichever layout is shown: the critical
 * path and what can start at once, as the terminal says them. */
export function LayoutBar({ plan, layout, mode, why, onLayout }: { plan: Plan; layout: Layout; mode: "auto" | Layout; why: string; onLayout: (m: Mode) => void }): ReactElement {
  return (
    <div className="layout-bar" data-testid="layout" data-layout={layout}>
      <div className="toggle" role="group" aria-label="how the plan is drawn">
        {BUTTONS.map((m) => (
          <button key={m} type="button" className={m === mode ? "on" : ""} aria-pressed={m === mode} onClick={() => onLayout(m)}>
            {m}
          </button>
        ))}
      </div>
      <span className="muted">{why}</span>
      <span data-testid="critical">
        {plan.critical.length > 0 ? `critical path: ${plan.critical.join(" → ")}` : "no critical path: nothing waits on anything"}
      </span>
      <span data-testid="at-once" title={plan.at_once.join(", ")}>
        {plan.at_once.length} at once{onceAccepted(plan)}
        {plan.at_once.length === 0 && ": no leaf can start now"}
        {plan.at_once.length > 0 && `: ${plan.at_once.slice(0, 5).join(", ")}`}
        {plan.at_once.length > 5 && ` and ${plan.at_once.length - 5} more`}
      </span>
    </div>
  );
}

/** Where a drawing starts: its width fitted to the pane, never larger than drawn and never below 0.6,
 * where it stays readable and is dragged (a layout the viewer picked though it is far too wide). A
 * drawing only taller than its pane starts at 1 and pans down. */
export const startScale = (width: number, pane: number): number => Math.max(Math.min(1, pane / width), 0.6);

/** Which events move the drawing: d3-zoom's own rule (no right button, no ctrl but a pinch's wheel),
 * and on a touch screen only two fingers, so one finger still scrolls the page past the drawing. */
export const panFilter = (event: Event): boolean => {
  const e = event as Event & { ctrlKey?: boolean; button?: number; touches?: { length: number } };
  if (e.type === "touchstart") return (e.touches?.length ?? 0) > 1;
  return (!e.ctrlKey || e.type === "wheel") && !e.button;
};

/** A drawing larger than its pane pans and zooms with d3-zoom, as the record's map does; one that
 * fits is drawn as it is. The pane is measured, so a static render draws it whole. */
function Pan({ width, height, label, onClear, children }: { width: number; height: number; label: string; onClear: () => void; children: ReactNode }): ReactElement {
  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [pane, setPane] = useState<[number, number]>([0, 0]);
  const [t, setT] = useState<ZoomTransform>(zoomIdentity);
  useEffect(() => {
    const node = box.current;
    if (!node) return;
    const measure = () => setPane([node.clientWidth, node.clientHeight]);
    const watch = new ResizeObserver(measure);
    watch.observe(node);
    measure();
    return () => watch.disconnect();
  }, []);
  const [pw, ph] = pane;
  const larger = pw > 0 && ph > 0 && (width > pw || height > ph);
  useEffect(() => {
    const node = svg.current;
    if (!node || !larger) return setT(zoomIdentity);
    const fit = Math.min(1, pw / width, ph / height);
    const behaviour = zoom<SVGSVGElement, unknown>()
      .filter(panFilter)
      .extent([
        [0, 0],
        [pw, ph],
      ])
      .scaleExtent([fit, 2])
      .translateExtent([
        [0, 0],
        [width, height],
      ])
      .on("zoom", (event: { transform: ZoomTransform }) => setT(event.transform));
    const picked = select(node);
    picked.call(behaviour).call(behaviour.transform, zoomIdentity.scale(startScale(width, pw)));
    return () => {
      picked.on(".zoom", null);
    };
  }, [larger, pw, ph, width, height]);
  return (
    <>
      {larger && <p className="pan-hint muted">two fingers move and zoom the drawing; one scrolls the page</p>}
      <div className="plan-canvas" ref={box} data-pans={larger}>
        <svg ref={svg} width={larger ? pw : width} height={larger ? ph : height} aria-label={label} onClick={onClear}>
          <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX={7} refY={4} markerWidth={7} markerHeight={7} orient="auto">
              <path d="M0,1L7,4L0,7Z" fill="var(--neutral)" />
            </marker>
          </defs>
          <g transform={t.toString()}>{children}</g>
        </svg>
      </div>
    </>
  );
}

const points = (edge: PlanEdge, dx: number, dy: number): string => edge.points.map((p) => `${dx + (p[0] ?? 0)},${dy + (p[1] ?? 0)}`).join(" ");

/** The graph: what waits on what, left to right in columns by depth, one lane per owner. The critical
 * path is drawn heavier, its edges and its boxes, and a leaf that can start now is tinted. */
export function PlanView({ plan, picked, onPick }: { plan: Plan; picked: string | null; onPick: (id: string | null) => void }): ReactElement {
  const width = graphWidth(plan);
  const on = new Set(plan.critical);
  const now = new Set(plan.at_once);
  return (
    <Pan width={width} height={plan.height + PAD_Y * 2} label="the plan, as a graph of what waits on what" onClear={() => onPick(null)}>
      {plan.lanes.map((lane) => (
        <g key={lane.id} className={`lane-band ${lane.person ? "person" : ""}`} data-lane={lane.id}>
          <rect x={4} y={PAD_Y + lane.y} width={width - 8} height={lane.height} rx={10} />
          <text x={16} y={PAD_Y + lane.y + 17}>
            {lane.person ? `${lane.label} — a person's` : "agents"}
          </text>
        </g>
      ))}
      {plan.edges.map((edge) => (
        <polyline key={edge.id} data-edge={edge.id} data-critical={edge.critical} className={edge.critical ? "edge critical" : "edge"} markerEnd="url(#arrow)" points={points(edge, PAD_X, PAD_Y)} />
      ))}
      {plan.nodes.map((node) => (
        <Box key={node.id} node={node} x={PAD_X + node.x} y={PAD_Y + node.y} on={node.id === picked} critical={on.has(node.id)} now={now.has(node.id)} onPick={onPick} />
      ))}
    </Pan>
  );
}

/** The tree the way a person draws it: the goal at the top, each node under the one it helps achieve,
 * the leaves at the ends of the branches. The same boxes, the same states and colours as the graph. */
export function PlanTopDown({ plan, picked, onPick }: { plan: Plan; picked: string | null; onPick: (id: string | null) => void }): ReactElement {
  const on = new Set(plan.critical);
  const now = new Set(plan.at_once);
  const [gx, gy] = [PAD_Y + (plan.tree_goal[0] ?? 0), PAD_Y + (plan.tree_goal[1] ?? 0)];
  const goal = plan.goal || "no goal yet";
  return (
    <Pan width={treeWidth(plan)} height={plan.tree_height + PAD_Y * 2} label="the plan, as a tree" onClear={() => onPick(null)}>
      {plan.tree_links.map((link) => (
        <polyline key={link.id} data-link={link.id} className="edge link" points={points(link, PAD_Y, PAD_Y)} />
      ))}
      <g className="node goal-box" data-goal="" transform={`translate(${gx},${gy})`}>
        <rect className="box" width={200} height={76} rx={8} />
        <text x={12} y={24} className="state">
          the goal
        </text>
        {wrap(goal, 176, CHAR).map((line, i) => (
          <text key={i} x={12} y={44 + i * 16} className="title">
            {line}
            <title>{goal}</title>
          </text>
        ))}
      </g>
      {plan.nodes.map((node) => (
        <Box key={node.id} node={{ ...node, width: node.tree_w }} x={PAD_Y + node.tree_x} y={PAD_Y + node.tree_y} on={node.id === picked} critical={on.has(node.id)} now={now.has(node.id)} onPick={onPick} />
      ))}
    </Pan>
  );
}

/** Words laid into two lines of a box, the second cut: the goal's box holds a sentence. */
export const wrap = (text: string, width: number, per: number): string[] => {
  const room = Math.floor(width / per);
  const words = text.split(" ");
  let first = "";
  while (words.length > 0 && `${first} ${words[0]}`.trim().length <= room) first = `${first} ${words.shift()}`.trim();
  if (!first) return [clip(text, width, per)];
  return words.length > 0 ? [first, clip(words.join(" "), width, per)] : [first];
};

function Box({
  node,
  x,
  y,
  on,
  critical,
  now,
  onPick,
}: {
  node: PlanNode;
  x: number;
  y: number;
  on: boolean;
  critical: boolean;
  now: boolean;
  onPick: (id: string) => void;
}): ReactElement {
  const shown = node.display_state;
  const colour = STATE_COLOUR[shown];
  // who has it and since when while it runs; who had it and when it ended once it is finished: the
  // executor by its name, `run:` left to the detail, so the clock fits a 200px card
  const by = (node.executor ?? "").replace(/^run:/, "");
  const held = node.executor
    ? node.state === "running"
      ? `${by} · since ${clock(node.started_at)}`
      : `${by} · finished ${clock(node.finished_at)}`
    : null;
  const who = node.owner === "agent" ? node.id : `${node.id} · ${node.owner}'s`;
  const says = node.sub_goal ? rolled(node) : (held ?? node.waits[0] ?? node.scope.join(", "));
  return (
    <g
      className={["node", on && "on", critical && "critical", now && "now"].filter(Boolean).join(" ")}
      data-node={node.id}
      data-state={shown}
      data-critical={critical}
      data-now={now}
      aria-selected={on}
      transform={`translate(${x},${y})`}
      onClick={(e) => (e.stopPropagation(), onPick(node.id))}
    >
      <rect className="box" width={node.width} height={node.height} rx={8} stroke={colour} strokeDasharray={shown === "proposed" ? "4 3" : undefined} />
      <g transform="translate(19,20)">
        <Shape state={shown} colour={colour} />
      </g>
      <text x={30} y={24} className="state" fill={colour}>
        {STATE[shown]}
      </text>
      {node.signoff && (
        <text x={node.width - 10} y={24} className="tag" textAnchor="end">
          sign-off
        </text>
      )}
      <text x={12} y={44} className="title">
        {clip(node.title, node.width - 24, CHAR)}
        <title>{node.title}</title>
      </text>
      <text x={12} y={58} className="who">
        {clip(who, node.width - 24, SMALL)}
        <title>{who}</title>
      </text>
      <text x={12} y={70} className="says">
        {clip(says, node.width - 24, SMALL)}
        <title>{says}</title>
      </text>
    </g>
  );
}

// -- the inspector, where the contract is read and changed ----------------------------------------

function Fact({ label, children }: { label: string; children: ReactElement | string | null }): ReactElement {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** One button that calls one function in plan.py. Disabled, it says why before anything is sent;
 * refused, it prints the server's own sentence where it stands. */
function Act({ label, no, op, body, write }: { label: string; no: string | null; op: string; body: () => unknown; write: Write }): ReactElement {
  const [said, setSaid] = useState<string | null>(null);
  return (
    <span className="act">
      <button type="button" data-act={op} disabled={no !== null} title={no ?? undefined} onClick={async () => setSaid(await write(op, body()))}>
        {label}
      </button>
      {no && <span className="rule">{no}</span>}
      {said && <p className="error">{said}</p>}
    </span>
  );
}

function Contract({ node, plan, write }: { node: PlanNode; plan: Plan; write: Write }): ReactElement {
  const [title, setTitle] = useState(node.title);
  const [goal, setGoal] = useState(node.goal);
  const [scope, setScope] = useState(node.scope.join("\n"));
  const [check, setCheck] = useState(node.check ?? "");
  const [needs, setNeeds] = useState(node.needs.join(", "));
  const [owner, setOwner] = useState(node.owner);
  const [signoff, setSignoff] = useState(node.signoff);
  const [said, setSaid] = useState<string | null>(null);
  const no = why(node, plan).edit;
  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setSaid(
      await write("set", {
        id: node.id,
        title,
        goal,
        scope: lines(scope),
        check: check.trim() || null,
        needs: words(needs),
        owner: owner.trim() || "agent",
        signoff,
      }),
    );
  };
  return (
    <form className="edit" onSubmit={save}>
      <label>
        title
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        goal
        <textarea rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} />
      </label>
      <label>
        scope — one glob a line
        <textarea rows={3} value={scope} onChange={(e) => setScope(e.target.value)} />
      </label>
      <p className="rule">{plan.holes.scope}</p>
      <label>
        check
        <input value={check} onChange={(e) => setCheck(e.target.value)} />
      </label>
      <p className="rule">{plan.holes.check}</p>
      <label>
        waits on — node ids
        <input value={needs} onChange={(e) => setNeeds(e.target.value)} />
      </label>
      <label>
        owner — agent, or a person&rsquo;s name
        <input value={owner} onChange={(e) => setOwner(e.target.value)} />
      </label>
      <label className="tick">
        <input type="checkbox" checked={signoff} onChange={(e) => setSignoff(e.target.checked)} />a person signs it off
      </label>
      <p className="rule">{plan.holes.person}</p>
      {said && <p className="error">{said}</p>}
      <p className="acts">
        <button type="submit" disabled={no !== null} title={no ?? undefined}>
          save the contract
        </button>
        {no && <span className="rule">{no}</span>}
      </p>
    </form>
  );
}

function AddNode({ plan, write }: { plan: Plan; write: Write }): ReactElement {
  const [title, setTitle] = useState("");
  const [scope, setScope] = useState("");
  const [check, setCheck] = useState("");
  const [goal, setGoal] = useState("");
  const [needs, setNeeds] = useState("");
  const [owner, setOwner] = useState("agent");
  const [parent, setParent] = useState("");
  const [signoff, setSignoff] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const add = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const failed = await write("add", {
      title,
      goal,
      scope: lines(scope),
      check: check.trim() || null,
      needs: words(needs),
      owner: owner.trim() || "agent",
      parent: parent.trim(),
      signoff,
    });
    setSaid(failed);
    if (failed === null) {
      setTitle("");
      setScope("");
      setCheck("");
      setGoal("");
      setNeeds("");
    }
  };
  return (
    <form className="edit" onSubmit={add} data-testid="add-node">
      <label>
        title
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="what this node is" />
      </label>
      <label>
        scope — one glob a line
        <textarea rows={2} value={scope} onChange={(e) => setScope(e.target.value)} placeholder="src/api/**" />
      </label>
      <p className="rule">{plan.holes.scope}</p>
      <label>
        check
        <input value={check} onChange={(e) => setCheck(e.target.value)} placeholder="pytest tests/api" />
      </label>
      <p className="rule">{plan.holes.check}</p>
      <label>
        goal
        <textarea rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} />
      </label>
      <label>
        under — the node it helps achieve, or blank for the goal
        <input value={parent} onChange={(e) => setParent(e.target.value)} placeholder="n1" />
      </label>
      <label>
        waits on — node ids
        <input value={needs} onChange={(e) => setNeeds(e.target.value)} />
      </label>
      <label>
        owner — agent, or a person&rsquo;s name
        <input value={owner} onChange={(e) => setOwner(e.target.value)} />
      </label>
      <label className="tick">
        <input type="checkbox" checked={signoff} onChange={(e) => setSignoff(e.target.checked)} />a person signs it off
      </label>
      {said && <p className="error">{said}</p>}
      <p className="acts">
        <button type="submit">add it to the plan</button>
      </p>
    </form>
  );
}

function Log({ node }: { node: PlanNode }): ReactElement {
  return (
    <ul className="list log">
      {node.log.map((entry, i) => (
        <li key={`${entry.at}:${i}`}>
          <span className="who">
            {entry.kind} <span className="muted">{entry.actor}</span>
          </span>
          <span className="grade">{stamp(entry.at)}</span>
          {entry.said && <span className="grade said">{entry.said}</span>}
        </li>
      ))}
      {node.log.length === 0 && <li className="muted">nothing recorded yet.</li>}
    </ul>
  );
}

export function PlanInspector({
  plan,
  picked,
  write,
  recorded = 1,
}: {
  plan: Plan;
  picked: string | null;
  write: Write;
  recorded?: number;
}): ReactElement {
  const [note, setNote] = useState("");
  const node = plan.nodes.find((n) => n.id === picked) ?? null;
  if (node === null) {
    const leaves = leavesOf(plan);
    const shown = (Object.keys(STATE) as Shown[]).filter((state) => leaves.some((l) => l.display_state === state));
    return (
      <aside className="inspector" data-testid="inspector">
        <h2>The plan</h2>
        <p className="sub">select a node to read its contract{plan.writable ? ", or add one" : ""}</p>
        <dl className="facts" data-testid="leaves">
          {shown.map((state) => (
            <Fact key={state} label={STATE[state]}>
              {`${leaves.filter((l) => l.display_state === state).length} of ${leaves.length} leaves`}
            </Fact>
          ))}
        </dl>
        {recorded === 0 && <p className="rule" data-testid="unrecorded">{UNRECORDED}</p>}
        {plan.writable ? (
          <section className="block">
            <h3>Add a node</h3>
            <AddNode plan={plan} write={write} />
          </section>
        ) : (
          <p className="rule" data-testid="read-only">{plan.token === null ? READ_ONLY.copy : READ_ONLY.agent}</p>
        )}
      </aside>
    );
  }
  const no = why(node, plan);
  return (
    <aside className="inspector" data-testid="inspector">
      <h2>{node.title}</h2>
      <p className="sub">
        {node.id} · {STATE[node.display_state]} · {node.owner === "agent" ? "any agent" : `${node.owner}'s`} · revision {node.rev}
      </p>
      {/* why this is being done at all: the path from the plan's goal down to it, root first, the
       * same lines `graphene node start` prints to whoever takes it */}
      {node.why.length > 0 && (
        <ol className="list why" data-testid="why">
          {node.why.map((line, i) => (
            <li key={line} style={{ paddingLeft: i * 12 }}>
              {line}
            </li>
          ))}
        </ol>
      )}
      <dl className="facts">
        <Fact label="goal">{node.goal || node.title}</Fact>
        {node.sub_goal ? (
          <Fact label="done when">
            {`its children are: ${rolled(node)}${node.check ? `, and then \`${node.check}\` passes` : ""}`}
          </Fact>
        ) : (
          <>
            <Fact label="may touch">{node.scope.join(", ") || "nothing"}</Fact>
            <Fact label="done when">
              {[node.check ? `${node.check} passes` : "", node.signoff ? "a person signs it off" : ""].filter(Boolean).join(", and ") || "—"}
            </Fact>
          </>
        )}
        {node.needs.length > 0 && <Fact label="waits on">{node.needs.join(", ")}</Fact>}
        {node.executor && (
          <Fact label={node.state === "running" ? "held by" : "ran by"}>
            {`${node.executor}, ${node.state === "running" ? "since" : "from"} ${stamp(node.started_at)}`}
          </Fact>
        )}
        {node.finished_at && <Fact label="finished">{stamp(node.finished_at)}</Fact>}
        {node.decided.length > 0 && (
          <Fact label="decided">
            <ul className="list decided" data-testid="decided">
              {node.decided.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </Fact>
        )}
      </dl>
      {node.state === "running" && <p className="rule">{plan.holes.stop}</p>}
      {node.waits.length > 0 && (
        <ul className="list waits">
          {node.waits.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {plan.writable && (
      <section className="block">
        <h3>What a person decides</h3>
        <p className="acts">
          <Act label="accept" op="accept" no={no.accept} body={() => ({ ids: [node.id] })} write={write} />
          <Act label="sign off" op="signoff" no={no.signoff} body={() => ({ id: node.id })} write={write} />
          <Act label="drop" op="drop" no={no.drop} body={() => ({ id: node.id })} write={write} />
        </p>
        <p className="rule">{plan.holes.person}</p>
        <p className="acts">
          <input className="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="what is wrong with it" aria-label="a note for whoever takes it next" />
          <Act label="send it back" op="reopen" no={no.reopen} body={() => ({ id: node.id, note })} write={write} />
        </p>
      </section>
      )}
      {plan.writable && (
        <section className="block">
          <h3>Its contract</h3>
          <Contract key={`${node.id}:${node.rev}`} node={node} plan={plan} write={write} />
        </section>
      )}
      <section className="block">
        <h3>Everything recorded about it</h3>
        <Log node={node} />
      </section>
    </aside>
  );
}
