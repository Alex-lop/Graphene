// The map: lanes above, repo rows below, one x transform over both. Every position comes from the
// JSON; the page adds an open container's numbers and the viewport's pan and zoom, and nothing else.

import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { useEffect, useRef, useState, type ReactElement } from "react";

import { LANE_H, ROW_H, clock, cull, dash, hue, hues, laneRegion, rowRegion, span } from "./model";
import type { Chain, Open, Selection } from "./model";
import type { Graph, Lane, Mark } from "./types";

const GUTTER = 196; // the fixed label column: it never pans
const AXIS_H = 26;
const BREAK_H = 16;
const GAP = 28; // between the two regions, with the repo divider in it
const RIGHT = 16;

const TOP = AXIS_H + BREAK_H;
const CHAR = 6.4; // enough to keep a 12px label inside the gutter
const MONO = 7.0;

interface Props {
  graph: Graph;
  open: Open;
  toggle: (id: string) => void;
  selection: Selection | null;
  select: (s: Selection | null) => void;
  lit: Chain | null;
}

// A member of a closed group or directory keeps its element and stops being drawn; SVG has no
// `hidden` in React's typings, so it goes on as the plain attribute it is.
const away = (gone: boolean): { hidden?: "" } => (gone ? { hidden: "" } : {});

const clip = (text: string, width: number, per: number): string => {
  const room = Math.floor(width / per);
  return text.length <= room ? text : `${text.slice(0, Math.max(1, room - 1))}…`;
};

const laneName = (lane: Lane): string =>
  lane.task ?? lane.label ?? (lane.kind === "main" ? "main agent" : lane.kind === "unknown" ? "no recorded agent" : "agent");

const curve = (sx: number, sy: number, tx: number, ty: number): string =>
  `M${sx},${sy}C${sx + (tx - sx) / 2},${sy} ${tx - (tx - sx) / 2},${ty} ${tx},${ty}`;

function Glyph({ mark, colour }: { mark: Mark; colour: string }): ReactElement {
  if (mark.region === "rows") {
    if (mark.grade === "edit") return <circle r={4.5} fill={colour} />;
    if (mark.grade === "shell") return <rect x={-4} y={-4} width={8} height={8} fill={colour} />;
    if (mark.grade === "commit") return <path d="M0,-5.5L5.5,0L0,5.5L-5.5,0Z" fill={colour} />;
    if (mark.grade === "window") return <circle r={4.4} fill="none" stroke={colour} strokeWidth={1.8} />;
    return <rect x={-5} y={-5} width={10} height={10} fill="url(#hatch)" stroke={colour} strokeWidth={1.2} />;
  }
  switch (mark.kind) {
    case "commit":
      return <path d="M0,-5.5L5.5,0L0,5.5L-5.5,0Z" fill={colour} />;
    case "prompt":
      return <path d="M-4,-5.5L5,0L-4,5.5Z" fill={colour} />;
    case "spawn":
      return <circle r={4.2} fill="var(--panel)" stroke={colour} strokeWidth={2} />;
    case "check":
      return <rect x={-2} y={-6} width={4} height={12} rx={1} fill={mark.ok === false ? "var(--fail)" : "var(--pass)"} />;
    case "failure":
      return <path d="M0,-6L6,5L-6,5Z" fill="var(--fail)" />;
    case "refused":
      return (
        <g stroke="var(--ask)" strokeWidth={1.8} fill="none">
          <circle r={5} />
          <line x1={-3} y1={0} x2={3} y2={0} />
        </g>
      );
    case "outside":
      return <rect x={-4.5} y={-4.5} width={9} height={9} fill="none" stroke={colour} strokeWidth={1.5} strokeDasharray="2.5 1.8" />;
    default:
      return <circle r={2.6} fill={colour} />;
  }
}

export function MapView({ graph, open, toggle, selection, select: choose, lit }: Props): ReactElement {
  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(900);
  const [t, setT] = useState<ZoomTransform>(zoomIdentity);

  useEffect(() => {
    const node = box.current;
    if (!node) return;
    const watch = new ResizeObserver(() => setWidth(node.clientWidth));
    watch.observe(node);
    setWidth(node.clientWidth);
    return () => watch.disconnect();
  }, []);

  const plot = Math.max(120, width - GUTTER - RIGHT);
  const fit = (plot - 24) / (graph.axis.width || 1);
  useEffect(() => {
    const node = svg.current;
    if (!node) return;
    const pad = 12 / fit;
    const behaviour = zoom<SVGSVGElement, unknown>()
      .extent([
        [0, 0],
        [plot, 1],
      ])
      .scaleExtent([fit, fit * 80])
      .translateExtent([
        [-pad, 0],
        [graph.axis.width + pad, 1],
      ])
      .on("zoom", (event: { transform: ZoomTransform }) => setT(event.transform));
    const picked = select(node);
    picked.call(behaviour).call(behaviour.transform, zoomIdentity.scale(fit).translate(pad, 0));
    return () => {
      picked.on(".zoom", null);
    };
  }, [fit, plot, graph]);

  const lanes = laneRegion(graph, open);
  const rows = rowRegion(graph, open);
  const ROWS_Y = TOP + lanes.height + GAP;
  const height = ROWS_Y + rows.height + 12;
  const colour = hues(graph);
  const px = (x: number): number => GUTTER + t.applyX(x);
  const laneMid = (id: string): number => TOP + (lanes.y.get(id) ?? 0) + LANE_H / 2;
  const rowMid = (id: string): number => ROWS_Y + (rows.y.get(id) ?? 0) + ROW_H / 2;
  const tint = (lane: string | null): string => hue(lane ? colour.get(lane) : -1);
  const off = (kind: "lanes" | "rows", id: string): string =>
    lit && !(kind === "lanes" ? lit.lanes : lit.rows).has(id) ? "off" : "";

  const from = t.invertX(-40);
  const to = t.invertX(plot + 40);
  const shown = cull(graph.marks, from, to);
  const marks = new Map(graph.marks.map((m) => [m.id, m]));
  const laneOf = new Map(graph.lanes.map((l) => [l.id, l]));

  const pick = (event: { stopPropagation: () => void }, s: Selection): void => {
    event.stopPropagation();
    choose(selection && selection.kind === s.kind && selection.id === s.id ? null : s);
  };
  const chosen = (kind: Selection["kind"], id: string): true | undefined =>
    selection && selection.kind === kind && selection.id === id ? true : undefined;

  return (
    <div className="map" ref={box}>
      <svg ref={svg} width={width} height={height} aria-label="the map" onClick={() => choose(null)}>
        <defs>
          <pattern id="hatch" width={4} height={4} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1={0} y1={0} x2={0} y2={4} stroke="var(--line)" strokeWidth={2} />
          </pattern>
          <clipPath id="plot">
            <rect x={GUTTER} y={0} width={plot + RIGHT} height={height} />
          </clipPath>
          <clipPath id="names">
            <rect x={0} y={0} width={GUTTER - 8} height={height} />
          </clipPath>
        </defs>

        <g className="axis" clipPath="url(#plot)">
          {graph.axis.ticks.map((tick) => (
            <g key={tick.x} transform={`translate(${px(tick.x)},0)`}>
              <line y1={AXIS_H - 6} y2={height} className="tick" />
              <text y={16} className="tick-label">
                {clock(tick.t)}
              </text>
            </g>
          ))}
          {graph.axis.breaks.map((brk) => (
            <g key={brk.x0}>
              <rect x={px(brk.x0)} y={AXIS_H} width={Math.max(2, px(brk.x1) - px(brk.x0))} height={height - AXIS_H} className="break" />
              <text x={(px(brk.x0) + px(brk.x1)) / 2} y={AXIS_H + 12} className="break-label">
                {span(brk.seconds)} idle
              </text>
            </g>
          ))}
        </g>

        <g className="region-rule">
          <line x1={0} y1={ROWS_Y - GAP / 2} x2={width} y2={ROWS_Y - GAP / 2} />
          <text x={12} y={ROWS_Y - GAP / 2 - 6} className="region-label">
            repo
          </text>
          <text x={12} y={TOP - 6} className="region-label">
            agents
          </text>
        </g>

        {graph.lanes.map((lane) => {
          const y = TOP + (lanes.y.get(lane.id) ?? 0);
          const name = laneName(lane);
          const indent = lane.group ? 14 : 0;
          const group = lane.kind === "group";
          return (
            <g
              key={lane.id}
              data-lane={lane.id}
              data-kind={lane.kind}
              className={`lane ${off("lanes", lane.id)}`}
              aria-selected={chosen("agent", lane.id)}
              {...away(!lanes.shown.has(lane.id))}
              onClick={(e) => pick(e, { kind: "agent", id: lane.id })}
            >
              <rect className="hit" x={0} y={y} width={width} height={LANE_H} />
              <line className="guide" x1={GUTTER} y1={y + LANE_H / 2} x2={width} y2={y + LANE_H / 2} />
              <line
                className="lane-line"
                clipPath="url(#plot)"
                x1={px(lane.x0)}
                y1={y + LANE_H / 2}
                x2={px(lane.x1)}
                y2={y + LANE_H / 2}
                stroke={tint(lane.id)}
                strokeDasharray={dash(colour.get(lane.id))}
              />
              <g clipPath="url(#names)">
                {group ? (
                  <g className="caret" onClick={(e) => (e.stopPropagation(), toggle(lane.id))}>
                    <rect x={4} y={y + 6} width={16} height={16} fill="transparent" />
                    <path d={open.has(lane.id) ? "M7,10L17,10L12,17Z" : "M9,8L17,13L9,18Z"} />
                  </g>
                ) : (
                  <rect x={indent + 6} y={y + LANE_H / 2 - 5} width={3} height={10} rx={1.5} fill={tint(lane.id)} />
                )}
                <text x={indent + 24} y={y + LANE_H / 2 + 4} className={`name ${lane.kind}`}>
                  {clip(name, GUTTER - indent - 34 - (group ? 24 : 0), CHAR)}
                  <title>{name}</title>
                </text>
                {group && (
                  <text x={GUTTER - 12} y={y + LANE_H / 2 + 4} className="count" textAnchor="end">
                    {lane.members}
                  </text>
                )}
              </g>
            </g>
          );
        })}

        {graph.rows.map((row) => {
          const y = ROWS_Y + (rows.y.get(row.id) ?? 0);
          const dir = row.kind === "dir";
          const name = dir ? `${row.path}/` : (row.path.split("/").pop() ?? row.path);
          return (
            <g
              key={row.id}
              data-row={row.id}
              data-kind={row.kind}
              data-collision={row.collision ? "true" : undefined}
              className={`row ${off("rows", row.id)}`}
              aria-selected={chosen(dir ? "dir" : "file", row.id)}
              {...away(!rows.shown.has(row.id))}
              onClick={(e) => pick(e, { kind: dir ? "dir" : "file", id: row.id })}
            >
              <rect className={`band ${dir ? "dir" : ""} ${row.collision ? "collide" : ""}`} x={0} y={y} width={width} height={ROW_H} />
              <g clipPath="url(#names)">
                {dir ? (
                  <g className="caret" onClick={(e) => (e.stopPropagation(), toggle(row.id))}>
                    <rect x={4} y={y + 3} width={16} height={16} fill="transparent" />
                    <path d={open.has(row.id) ? "M7,7L17,7L12,14Z" : "M9,5L17,10L9,15Z"} />
                  </g>
                ) : null}
                <text x={dir ? 24 : 38} y={y + ROW_H / 2 + 4} className={`path ${dir ? "dir" : ""}`}>
                  {clip(name, GUTTER - (dir ? 62 : 76), MONO)}
                  <title>{row.path}</title>
                </text>
                <text x={GUTTER - 12} y={y + ROW_H / 2 + 4} className="count" textAnchor="end">
                  {dir ? `${row.files}f` : row.changes || ""}
                </text>
              </g>
            </g>
          );
        })}

        <g className={`links ${lit ? "lit" : ""}`} clipPath="url(#plot)">
          {graph.links.map((link) => {
            const shownLink = lit?.links.has(link.id) ?? false;
            const always = link.kind === "spawned" || link.kind === "returned";
            if (!always && !shownLink) return null;
            const source = marks.get(link.source);
            const target = marks.get(link.target);
            let d = "";
            let halo: [number, number] | null = null;
            if (link.kind === "spawned") {
              const lane = laneOf.get(link.target);
              const sx = source ? source.x : (laneOf.get(link.source)?.x0 ?? 0);
              const sy = laneMid(source ? source.at : link.source);
              d = curve(px(sx), sy, px(lane?.x0 ?? sx), laneMid(link.target));
            } else if (link.kind === "returned") {
              const lane = laneOf.get(link.source);
              d = curve(px(lane?.x1 ?? 0), laneMid(link.source), px(lane?.x1 ?? 0), laneMid(link.target));
            } else if (link.kind === "touched") {
              // the write itself is where the lane meets the row: its first recorded change
              const write = graph.marks.find((m) => m.region === "rows" && m.at === link.target && m.agent === link.source);
              if (!write) return null;
              d = curve(px(write.x), laneMid(link.source), px(write.x), rowMid(link.target));
            } else if (link.kind === "committed-in" && target) {
              d = curve(px(target.x), rowMid(link.source), px(target.x), laneMid(target.at));
            } else if (target) {
              halo = [px(target.x), laneMid(target.at)]; // ran and blocked stay on one lane
            }
            return (
              <g key={link.id} data-link={link.id} data-kind={link.kind} className={`link ${shownLink ? "on" : ""}`}>
                {halo ? <circle cx={halo[0]} cy={halo[1]} r={9} /> : <path d={d} />}
              </g>
            );
          })}
        </g>

        <g className="marks" clipPath="url(#plot)">
          {shown.map((mark) => {
            const y = mark.region === "lanes" ? laneMid(mark.at) : rowMid(mark.at);
            const colours = tint(mark.agent ?? mark.at);
            const dimmed = lit && !lit.marks.has(mark.id) ? "off" : "";
            const what: Selection =
              mark.kind === "commit"
                ? { kind: "commit", id: mark.id }
                : mark.region === "lanes"
                  ? { kind: "agent", id: mark.at }
                  : { kind: "file", id: mark.at };
            return (
              <g
                key={mark.id}
                data-mark={mark.id}
                data-kind={mark.kind}
                data-grade={mark.grade}
                className={`mark ${dimmed}`}
                aria-selected={chosen(what.kind, what.id)}
                transform={`translate(${px(mark.x)},${y})`}
                onClick={(e) => pick(e, what)}
              >
                {mark.count > 1 && <circle r={8} className="merged" stroke={colours} />}
                <Glyph mark={mark} colour={colours} />
                <title>
                  {`${clock(mark.t)} · ${mark.kind}${mark.label ? ` · ${mark.label}` : ""}${mark.count > 1 ? ` · ${mark.count} records` : ""}`}
                </title>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
