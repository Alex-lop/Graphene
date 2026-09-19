// The inspector: what the record says about the one thing that is selected, and where each fact
// came from. Nothing here is worked out — every line names the record it was read from.

import type { ReactElement, ReactNode } from "react";

import { GRADE, between, duration, stamp } from "./model";
import type { Selection } from "./model";
import type { Graph, Grade, Lane, Mark } from "./types";

const Ref = ({ of }: { of: string }): ReactElement => (
  <code className="ref" title={of}>
    {of}
  </code>
);

const Fact = ({ label, children }: { label: string; children: ReactNode }): ReactElement => (
  <div className="fact">
    <dt>{label}</dt>
    <dd>{children}</dd>
  </div>
);

const Block = ({ title, children }: { title: string; children: ReactNode }): ReactElement => (
  <section className="block">
    <h3>{title}</h3>
    {children}
  </section>
);

// A lane's record, in the graph's own reference scheme: an agent's row; for a Workflow group, the
// Workflow call that spawned its members. The main agent is the session, which has no single record.
const laneRef = (graph: Graph, lane: Lane): string | null => {
  if (lane.agent) return `agent:${(lane.session ?? "").slice(0, 8)}:${lane.agent}`;
  if (lane.kind !== "group") return null;
  const members = new Set(graph.lanes.filter((l) => l.group === lane.id).map((l) => l.id));
  return graph.links.find((l) => l.kind === "spawned" && members.has(l.target))?.ref ?? null;
};

const unique = <T,>(items: T[]): T[] => Array.from(new Set(items));

const name = (lane: Lane | undefined): string =>
  lane?.task ?? lane?.label ?? (lane?.kind === "main" ? "main agent" : lane?.kind === "unknown" ? "no recorded agent" : "agent");

const words = (grade: Grade, mark?: Mark): string => {
  const extra = [mark?.copy ? "worktree copy" : null, mark?.shared ? "may belong to a concurrent command" : null].filter(Boolean);
  return GRADE[grade] + (extra.length ? ` — ${extra.join(", ")}` : "");
};

export function Inspector({ graph, selection }: { graph: Graph; selection: Selection | null }): ReactElement {
  const lanes = new Map(graph.lanes.map((l) => [l.id, l]));
  const rows = new Map(graph.rows.map((r) => [r.id, r]));
  const marks = new Map(graph.marks.map((m) => [m.id, m]));
  const path = (id: string): string => rows.get(id)?.path ?? id;
  // the mark a link cites: same row, same record; else the agent's mark of that grade on the row
  const change = (link: { ref: string; grade: Grade }, row: string, agent: string): Mark | undefined =>
    graph.marks.find((m) => m.region === "rows" && m.at === row && m.ref === link.ref) ??
    graph.marks.find((m) => m.region === "rows" && m.at === row && m.agent === agent && m.grade === link.grade);

  let body: ReactNode = null;
  let heading = "Nothing selected";
  let sub = "";

  if (selection?.kind === "agent" && lanes.has(selection.id)) {
    const lane = lanes.get(selection.id)!;
    const touched = graph.links.filter((l) => l.kind === "touched" && l.source === lane.id);
    const commits = graph.marks.filter((m) => m.kind === "commit" && m.agent === lane.id);
    const checks = graph.marks.filter((m) => m.kind === "check" && m.at === lane.id);
    const unknown = lane.kind === "unknown";
    heading = name(lane);
    sub = unknown ? "commits in the window with no agent on record" : (lane.type ?? lane.kind);
    body = (
      <>
        {lane.prompt && (
          <Block title="What it was asked">
            <p className="prompt">{lane.prompt}</p>
            {laneRef(graph, lane) && <Ref of={laneRef(graph, lane)!} />}
          </Block>
        )}
        <dl className="facts">
          <Fact label="type">{lane.type ?? lane.kind}</Fact>
          {lane.worktree && <Fact label="worktree">{lane.worktree}</Fact>}
          {!lane.worktree && lane.cwd && <Fact label="working directory">{lane.cwd}</Fact>}
          <Fact label="span">{between(lane.t0, lane.t1)}</Fact>
          <Fact label="duration">{duration(lane.t0, lane.t1)}</Fact>
          {lane.kind === "main" && lane.session && <Fact label="session">{lane.session.slice(0, 8)}</Fact>}
          {laneRef(graph, lane) && (
            <Fact label="record">
              <Ref of={laneRef(graph, lane)!} />
            </Fact>
          )}
        </dl>
        {touched.length > 0 && (
          <Block title={`Files (${unique(touched.map((l) => l.target)).length})`}>
            <ul className="list">
              {unique(touched.map((l) => l.target)).map((target) => (
                <li key={target}>
                  <code className="path">{path(target)}</code>
                  {touched
                    .filter((l) => l.target === target)
                    .map((link) => (
                      <span key={link.id} className="evidence">
                        <span className="grade">{words(link.grade, change(link, target, lane.id))}</span>
                        <Ref of={link.ref} />
                      </span>
                    ))}
                </li>
              ))}
            </ul>
          </Block>
        )}
        {commits.length > 0 && (
          <Block title={`Commits (${commits.length})`}>
            <ul className="list">
              {commits.map((commit) => (
                <li key={commit.id}>
                  <code className="path">{commit.label}</code>
                  {unknown && (
                    <span className="grade">
                      {graph.links
                        .filter((l) => l.kind === "committed-in" && l.target === commit.id)
                        .map((l) => path(l.source))
                        .join(", ")}
                    </span>
                  )}
                  <Ref of={commit.ref} />
                </li>
              ))}
            </ul>
          </Block>
        )}
        {checks.length > 0 && (
          <Block title={`Checks (${checks.length})`}>
            <ul className="list">
              {checks.map((check) => (
                <li key={check.id}>
                  <code className="path">{check.label}</code>
                  <span className={check.ok === false ? "bad" : "good"}>{check.ok === false ? "failed" : "passed"}</span>
                  <Ref of={check.ref} />
                </li>
              ))}
            </ul>
          </Block>
        )}
        {lane.closing && (
          <Block title="What it said when it stopped">
            <p className="prompt">{lane.closing}</p>
          </Block>
        )}
      </>
    );
  } else if (selection && (selection.kind === "file" || selection.kind === "dir") && rows.has(selection.id)) {
    const row = rows.get(selection.id)!;
    const members = selection.kind === "dir" ? graph.rows.filter((r) => r.dir === row.id) : [row];
    const ids = new Set(members.map((r) => r.id));
    const touched = graph.links.filter((l) => l.kind === "touched" && ids.has(l.target));
    const carried = graph.links.filter((l) => l.kind === "committed-in" && ids.has(l.source));
    heading = row.path;
    sub = row.kind === "dir" ? `${row.files} files · ${row.changes} recorded changes` : `${row.changes} recorded changes`;
    body = (
      <>
        <dl className="facts">
          <Fact label="first seen">{stamp(row.t0)}</Fact>
          <Fact label="two agents at once">{row.collision ? "yes" : "no"}</Fact>
        </dl>
        {row.collision && <p className="rule">{graph.rules.collision}</p>}
        {touched.length > 0 && (
          <Block title={`Touched by (${unique(touched.map((l) => l.source)).length})`}>
            <ul className="list">
              {touched.map((link) => (
                <li key={link.id}>
                  <span className="who">{name(lanes.get(link.source))}</span>
                  {row.kind === "dir" && <code className="path">{path(link.target)}</code>}
                  <span className="grade">{words(link.grade, change(link, link.target, link.source))}</span>
                  <Ref of={link.ref} />
                </li>
              ))}
            </ul>
          </Block>
        )}
        {carried.length > 0 && (
          <Block title={`Commits (${unique(carried.map((l) => l.target)).length})`}>
            <ul className="list">
              {unique(carried.map((l) => l.target)).map((target) => (
                <li key={target}>
                  <code className="path">{marks.get(target)?.label ?? target}</code>
                  {carried
                    .filter((l) => l.target === target)
                    .map((link) => (
                      <span key={link.id} className="grade">
                        {row.kind === "dir" ? `${path(link.source)}: ` : ""}
                        {words(link.grade)}
                      </span>
                    ))}
                  <Ref of={marks.get(target)?.ref ?? target} />
                </li>
              ))}
            </ul>
          </Block>
        )}
      </>
    );
  } else if (selection?.kind === "commit" && marks.has(selection.id)) {
    const commit = marks.get(selection.id)!;
    const files = graph.links.filter((l) => l.kind === "committed-in" && l.target === commit.id);
    heading = commit.label ?? commit.ref;
    sub = "commit";
    body = (
      <>
        <dl className="facts">
          <Fact label="committed">{stamp(commit.committed ?? commit.t)}</Fact>
          {commit.committed && commit.committed !== commit.t && <Fact label="the call began">{stamp(commit.t)}</Fact>}
          <Fact label="ran on">{name(lanes.get(commit.at))}</Fact>
          <Fact label="credited to">{name(lanes.get(commit.agent ?? commit.at))}</Fact>
          <Fact label="record">
            <Ref of={commit.ref} />
          </Fact>
        </dl>
        <Block title={`Files (${files.length})`}>
          <ul className="list">
            {files.map((link) => (
              <li key={link.id}>
                <code className="path">{path(link.source)}</code>
                <span className="grade">{words(link.grade)}</span>
                <Ref of={link.ref} />
              </li>
            ))}
          </ul>
        </Block>
      </>
    );
  } else {
    sub = "select a lane, a row or a mark";
    body = (
      <dl className="facts">
        <Fact label="records read">{graph.omitted.records ?? 0}</Fact>
        <Fact label="marks drawn">{graph.marks.length}</Fact>
        <Fact label="records merged into another mark's count">{graph.omitted.merged_into_counts ?? 0}</Fact>
        <Fact label="files Claude Code's shell lists left out">{graph.omitted.vendor_more_files ?? 0}</Fact>
        <Fact label="shell calls whose list Claude Code could not make">
          {graph.omitted.vendor_lists_unavailable ?? 0}
        </Fact>
      </dl>
    );
  }

  return (
    <aside className="inspector" data-testid="inspector">
      <h2>{heading}</h2>
      <p className="sub">{sub}</p>
      {body}
    </aside>
  );
}
