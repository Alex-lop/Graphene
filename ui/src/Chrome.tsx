// The frame around the map: the run in one line, the coverage counts, the counters as filters, the
// rail of runs, the agent's own list, what nothing accounts for, and the caption that never leaves.

import type { ReactElement } from "react";

import { Glyph } from "./Map";
import { COUNTER, GRADE, between, duration, stamp, clock, zone } from "./model";
import type { Counter } from "./model";
import type { Grade, Graph, Mark, Run } from "./types";

const COUNTERS: Counter[] = ["failed_checks", "rerun_green", "refused", "failures", "outside", "collisions"];
const ONE: Partial<Record<Counter, string>> = { failed_checks: "failed check", failures: "other failed call", collisions: "collision" };
const GRADES: Grade[] = ["edit", "shell", "commit", "window", "unknown"];

const many = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

export function Header({
  graph,
  chip,
  onChip,
}: {
  graph: Graph;
  chip: Counter | null;
  onChip: (c: Counter | null) => void;
}): ReactElement {
  const { run, coverage } = graph;
  const ids = run.sessions.map((s) => s.id.slice(0, 8)).join(", ");
  return (
    <header className="header" data-testid="header">
      <div className="run">
        <h1>{run.repo || "this repo"}</h1>
        <code className="ref">{ids || "no session"}</code>
        <span>
          {between(run.started ?? run.t0, run.ended ?? run.t1)} <span className="muted">{zone(run.t0)}</span>
        </span>
        <span>{duration(run.started ?? run.t0, run.ended ?? run.t1)}</span>
        <span>
          {many(run.agents, "agent")} · {many(run.commits, "commit")} · {many(run.prompts, "prompt")}
        </span>
      </div>
      <div className="coverage" data-testid="coverage">
        <div className="cov">
          <b>{coverage.committed_files}</b>
          <span>committed files</span>
        </div>
        <div className="cov">
          <b>{coverage.write}</b>
          <span>traced to a recorded write</span>
        </div>
        <div className="cov">
          <b>{coverage.commit}</b>
          <span>only to an agent&rsquo;s commit</span>
        </div>
        <div className={`cov ${coverage.nothing ? "warn" : ""}`}>
          <b>{coverage.nothing}</b>
          <span>to nothing</span>
        </div>
        <p className="window">
          {coverage.window} of those {coverage.window === 1 ? "was" : "were"} committed during the session by no
          identifiable agent
        </p>
      </div>
      <div className="counters" data-testid="counters">
        {COUNTERS.map((name) => (
          <button
            key={name}
            type="button"
            data-counter={name}
            title={name === "outside" ? graph.rules.outside : name === "collisions" ? graph.rules.collision : undefined}
            className={`chip ${chip === name ? "on" : ""}`}
            disabled={graph.counters[name] === 0}
            aria-pressed={chip === name}
            onClick={() => onChip(chip === name ? null : name)}
          >
            <b>{graph.counters[name]}</b> {(graph.counters[name] === 1 && ONE[name]) || COUNTER[name]}
          </button>
        ))}
      </div>
    </header>
  );
}

export function Rail({
  runs,
  current,
  onPick,
}: {
  runs: Run[];
  current: string[];
  onPick: ((id: string) => void) | null;
}): ReactElement {
  return (
    <nav className="rail" data-testid="rail" aria-label="runs">
      <h2>Runs</h2>
      {runs.length === 0 && <p className="empty">No run has been recorded yet.</p>}
      {runs.map((run) => (
        <button
          key={run.id}
          type="button"
          data-run={run.id}
          className={`run-row ${current.includes(run.id) ? "on" : ""}`}
          aria-selected={current.includes(run.id)}
          disabled={onPick === null}
          onClick={() => onPick?.(run.id)}
        >
          <code className="ref">{run.id.slice(0, 8)}</code>
          <span className="when">{stamp(run.started_at)}</span>
          <span className="muted">
            {duration(run.started_at, run.ended_at)} · {many(run.agents, "agent")} · {many(run.files, "file")} edited ·{" "}
            {many(run.calls, "call")}
          </span>
        </button>
      ))}
    </nav>
  );
}

export function Footer({ graph }: { graph: Graph }): ReactElement {
  const nothing = graph.coverage.paths.nothing;
  return (
    <footer className="footer">
      {graph.tasks.length > 0 && (
        <section className="strip" data-testid="task-list">
          <h3>The agent&rsquo;s own list</h3>
          <ul>
            {graph.tasks.map((task) => (
              <li key={task.id}>
                <span>{task.subject}</span>
                <span className="muted">
                  created {clock(task.created)}
                  {task.started ? ` · started ${clock(task.started)}` : ""}
                  {task.done ? ` · done ${clock(task.done)}` : ""}
                </span>
                <code className="ref" title={task.ref}>
                  {task.ref}
                </code>
              </li>
            ))}
          </ul>
        </section>
      )}
      {nothing.length > 0 && (
        <section className="strip warn" data-testid="unknown-block">
          <h3>
            {nothing.length} committed {nothing.length === 1 ? "file traces" : "files trace"} to nothing
          </h3>
          <ul className="paths">
            {nothing.map((path) => (
              <li key={path}>
                <code className="path">{path}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
      {/* the shape is what carries the grade, so the shapes are named where they are drawn */}
      <ul className="legend" data-testid="legend">
        {GRADES.map((grade) => (
          <li key={grade} title={GRADE[grade]}>
            <svg width={14} height={14} aria-hidden="true">
              <g transform="translate(7,7)">
                <Glyph mark={{ region: "rows", grade } as Mark} colour="var(--neutral)" />
              </g>
            </svg>
            {grade}
          </li>
        ))}
        <li title={graph.rules.collision}>
          <span className="swatch" /> two agents held the file at once
        </li>
      </ul>
      <p className="caption" data-testid="caption">
        {graph.caption}
      </p>
    </footer>
  );
}
