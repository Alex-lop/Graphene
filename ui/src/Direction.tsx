// The direction above the plan: the path from its top to the node the plan hangs from, each row in
// the row grammar (the title, then the id, then one word), with what waits on you below it, what
// runs and what is next. The same rows `graphene plan` and `graphene watch` show (direction.py).

import type { ReactElement } from "react";

import type { Direction, DirectionNode } from "./types";

const COLOUR: Record<string, string> = {
  proposed: "var(--ask)",
  yours: "var(--ask)",
  running: "var(--a1)",
  quiet: "var(--neutral)",
};

const said = (node: DirectionNode): string =>
  [
    node.you ? `you ${node.you}` : "",
    node.running ? `${node.running} running` : "",
    node.next ? `next: ${node.next}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

/** The root first, down to the node the plan hangs from. */
export function path(direction: Direction, at: string): DirectionNode[] {
  const byId = new Map(direction.nodes.map((n) => [n.id, n]));
  const out: DirectionNode[] = [];
  for (let n = byId.get(at); n; n = n.parent ? byId.get(n.parent) : undefined) out.unshift(n);
  return out;
}

export function DirectionPath({ direction }: { direction?: Direction | null }): ReactElement | null {
  if (!direction || (!direction.refused && !direction.plan)) return null;
  const at = direction.plan?.node;
  return (
    <section className="plan-strip direction" data-testid="direction">
      {direction.refused ? (
        <p className="error">the direction: {direction.refused.split("\n")[0]} (`graphene direction` names the lines)</p>
      ) : !at ? (
        <p className="muted">
          the direction: the plan hangs from none of its nodes yet (<code>graphene direction plan NODE</code>)
        </p>
      ) : (
        <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {path(direction, at).map((node, depth) => (
            <li key={node.id} data-direction={node.id} style={{ paddingLeft: `${depth * 16}px` }}>
              <span className="what">{node.title}</span> <b>{node.id}</b>{" "}
              <span className="state" style={{ color: COLOUR[node.word] ?? "var(--neutral)" }}>
                {node.word}
              </span>{" "}
              <span className="muted">{said(node)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
