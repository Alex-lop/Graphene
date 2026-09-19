// The page: one run on screen, one thing selected at a time, and the state the person opened.

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import { Footer, Header, Rail } from "./Chrome";
import { Inspector } from "./Inspector";
import { MapView } from "./Map";
import { exported, load } from "./data";
import { chain, matching } from "./model";
import type { Counter, Selection } from "./model";
import type { Payload } from "./types";

export function App(): ReactElement {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [failed, setFailed] = useState(false);
  const [session, setSession] = useState<string | null>(null);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [selection, setSelection] = useState<Selection | null>(null);
  const [chip, setChip] = useState<Counter | null>(null);

  useEffect(() => {
    let live = true;
    load(session ? `?sessions=${session}` : undefined)
      .then((next) => live && setPayload(next))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [session]);

  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setSelection(null);
      setChip(null);
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, []);

  const toggle = useCallback((id: string) => {
    setOpen((was) => {
      const next = new Set(was);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }, []);

  const choose = useCallback((next: Selection | null) => {
    setSelection(next);
    setChip(null); // one thing lights the map at a time: a selection or a chip
  }, []);

  if (failed) return <p className="state">The server did not answer.</p>;
  if (!payload) return <p className="state" />;

  const { graph, runs } = payload;
  const lit = chain(graph, selection) ?? (chip ? matching(graph, chip) : null);
  const current = graph.run.sessions.map((s) => s.id);

  return (
    <div className="app">
      <Header
        graph={graph}
        chip={chip}
        onChip={(next) => {
          setChip(next);
          setSelection(null);
        }}
      />
      <Rail runs={runs} current={current} onPick={exported() ? null : setSession} />
      <main className="centre">
        {graph.lanes.length === 0 ? (
          <p className="state">No run has been recorded yet.</p>
        ) : (
          <MapView graph={graph} open={open} toggle={toggle} selection={selection} select={choose} lit={lit} />
        )}
        <Footer graph={graph} />
      </main>
      <Inspector graph={graph} selection={selection} />
    </div>
  );
}
