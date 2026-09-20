// The plan: what will be done, by whom, inside which paths, and what it waits for. Every position
// comes from src/graphene_debrief/plan_view.py; the page adds the gutter it draws lane names in and
// nothing else. Every control here changes what an agent may do, through one function in plan.py,
// and where that mechanism stops the sentence saying so is printed next to the control.

import { useState, type FormEvent, type ReactElement } from "react";

import { STATE, STATE_COLOUR, clip, clock, stamp, why, type View } from "./model";
import type { Plan, PlanNode, Shown } from "./types";

const PAD_X = 132; // the lane-name gutter, which is the page's own margin, not a position
const PAD_Y = 16;
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

const Shape = ({ state, colour }: { state: Shown; colour: string }): ReactElement => {
  switch (state) {
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

export function Toggle({ view, onView, planned }: { view: View; onView: (v: View) => void; planned: number }): ReactElement {
  return (
    <div className="toggle" role="group" aria-label="what the page shows">
      <button type="button" className={view === "plan" ? "on" : ""} aria-pressed={view === "plan"} disabled={planned === 0} onClick={() => onView("plan")}>
        the plan
      </button>
      <button type="button" className={view === "record" ? "on" : ""} aria-pressed={view === "record"} onClick={() => onView("record")}>
        the record
      </button>
    </div>
  );
}

export function PlanHeader({ plan, view, onView }: { plan: Plan; view: View; onView: (v: View) => void }): ReactElement {
  const counts = Object.entries(plan.counts).filter(([, n]) => n > 0);
  return (
    <header className="header" data-testid="header">
      <div className="run">
        <h1>{plan.repo || "this repo"}</h1>
        <Toggle view={view} onView={onView} planned={plan.nodes.length} />
        <span>
          {plan.nodes.length} node{plan.nodes.length === 1 ? "" : "s"}
          {counts.length > 0 ? ` · ${counts.map(([state, n]) => `${n} ${STATE[state as Shown]}`).join(" · ")}` : ""}
        </span>
      </div>
      <div className="badges">
        {plan.paused && <span className="badge warn">paused: nothing starts and no write is refused</span>}
        {!plan.writable && <span className="badge">read-only: this page cannot change the plan</span>}
      </div>
    </header>
  );
}

/** What is on the person right now, above everything else: the screen is prospective, and this is
 * the part of it that will not move until they touch it. */
export function PlanStrip({ plan, onPick, write }: { plan: Plan; onPick: (id: string) => void; write: Write }): ReactElement {
  const [said, setSaid] = useState<string | null>(null);
  const waiting = plan.waiting_on_person;
  return (
    <section className="strip plan-strip" data-testid="waiting-on-you">
      <h3>{waiting.length > 0 ? `waiting on you (${waiting.length})` : "nothing is waiting on you"}</h3>
      <ul>
        {waiting.map((item) => (
          <li key={item.id}>
            <button type="button" className="chip" data-waiting={item.id} onClick={() => onPick(item.id)}>
              <b>{item.id}</b> {item.why}
            </button>
          </li>
        ))}
        {waiting.length === 0 && <li className="muted">every node is with an agent, or done.</li>}
      </ul>
      <p className="muted forecast">
        left alone, agents can reach: {plan.forecast.runs.join(", ") || "nothing"}
        {plan.forecast.waits.map((wait) => (
          <span key={wait.id} className="waits">
            {wait.id} will wait: {wait.why.join("; ")}
          </span>
        ))}
      </p>
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

export function PlanView({ plan, picked, onPick }: { plan: Plan; picked: string | null; onPick: (id: string | null) => void }): ReactElement {
  const width = PAD_X + plan.width + 24;
  return (
    <div className="plan-canvas">
      <svg width={width} height={plan.height + PAD_Y * 2} aria-label="the plan" onClick={() => onPick(null)}>
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX={7} refY={4} markerWidth={7} markerHeight={7} orient="auto">
            <path d="M0,1L7,4L0,7Z" fill="var(--neutral)" />
          </marker>
        </defs>
        {plan.lanes.map((lane) => (
          <g key={lane.id} className={`lane-band ${lane.person ? "person" : ""}`} data-lane={lane.id}>
            <rect x={4} y={PAD_Y + lane.y} width={width - 8} height={lane.height} rx={10} />
            <text x={16} y={PAD_Y + lane.y + 17}>
              {lane.person ? `${lane.label} — a person's` : "agents"}
            </text>
          </g>
        ))}
        {plan.edges.map((edge) => (
          <polyline
            key={edge.id}
            data-edge={edge.id}
            className="edge"
            markerEnd="url(#arrow)"
            points={edge.points.map((p) => `${PAD_X + (p[0] ?? 0)},${PAD_Y + (p[1] ?? 0)}`).join(" ")}
          />
        ))}
        {plan.nodes.map((node) => (
          <Box key={node.id} node={node} on={node.id === picked} onPick={onPick} />
        ))}
      </svg>
    </div>
  );
}

function Box({ node, on, onPick }: { node: PlanNode; on: boolean; onPick: (id: string) => void }): ReactElement {
  const shown = node.display_state;
  const colour = STATE_COLOUR[shown];
  // who has it and since when while it runs; who had it and when it ended once it is finished
  const held = node.executor
    ? node.state === "running"
      ? `${node.executor} · since ${clock(node.started_at)}`
      : `${node.executor} · finished ${clock(node.finished_at)}`
    : null;
  const says = held ?? node.waits[0] ?? node.scope.join(", ");
  return (
    <g
      className={`node ${on ? "on" : ""}`}
      data-node={node.id}
      data-state={shown}
      aria-selected={on}
      transform={`translate(${PAD_X + node.x},${PAD_Y + node.y})`}
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
        {node.id} · {node.owner === "agent" ? "any agent" : node.owner} · revision {node.rev}
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
}: {
  plan: Plan;
  picked: string | null;
  write: Write;
}): ReactElement {
  const [note, setNote] = useState("");
  const node = plan.nodes.find((n) => n.id === picked) ?? null;
  if (node === null) {
    return (
      <aside className="inspector" data-testid="inspector">
        <h2>The plan</h2>
        <p className="sub">select a node to read its contract{plan.writable ? ", or add one" : ""}</p>
        <dl className="facts">
          {Object.entries(plan.counts).map(([state, n]) => (
            <Fact key={state} label={STATE[state as Shown]}>
              {String(n)}
            </Fact>
          ))}
        </dl>
        {plan.writable ? (
          <section className="block">
            <h3>Add a node</h3>
            <AddNode plan={plan} write={write} />
          </section>
        ) : (
          <p className="rule">This page is read-only. The plan is changed from the person&rsquo;s terminal, or from a page they opened.</p>
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
      <dl className="facts">
        <Fact label="goal">{node.goal || node.title}</Fact>
        <Fact label="may touch">{node.scope.join(", ") || "nothing"}</Fact>
        <Fact label="done when">
          {[node.check ? `${node.check} passes` : "", node.signoff ? "a person signs it off" : ""].filter(Boolean).join(", and ") || "—"}
        </Fact>
        {node.needs.length > 0 && <Fact label="waits on">{node.needs.join(", ")}</Fact>}
        {node.executor && (
          <Fact label={node.state === "running" ? "held by" : "ran by"}>
            {`${node.executor}, ${node.state === "running" ? "since" : "from"} ${stamp(node.started_at)}`}
          </Fact>
        )}
        {node.finished_at && <Fact label="finished">{stamp(node.finished_at)}</Fact>}
      </dl>
      {node.state === "running" && <p className="rule">{plan.holes.stop}</p>}
      {node.waits.length > 0 && (
        <ul className="list waits">
          {node.waits.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
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
