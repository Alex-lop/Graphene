// The page: the plan by default, the record behind a toggle, one thing selected at a time.

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import { Footer, Header, Rail } from "./Chrome";
import { Inspector } from "./Inspector";
import { MapView } from "./Map";
import { PlanHeader, PlanInspector, PlanStrip, PlanView } from "./Plan";
import { exported, load, send } from "./data";
import { chain, matching } from "./model";
import type { Counter, Selection, View } from "./model";
import type { Payload } from "./types";

const EVERY = 2000; // milliseconds between reads of the plan while the tab is in front

export function App(): ReactElement {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [failed, setFailed] = useState(false);
  const [session, setSession] = useState<string | null>(null);
  const [view, setView] = useState<View | null>(null);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [selection, setSelection] = useState<Selection | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [chip, setChip] = useState<Counter | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setPayload(await load(session ? `?sessions=${session}` : undefined));
    } catch {
      setFailed(true);
    }
  }, [session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setSelection(null);
      setPicked(null);
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

  // A plan changes while the page is open: an agent takes a node, finishes one, proposes more. The
  // record does not change under a reader in the same way, and its map holds a pan and a zoom that
  // a reload would throw away, so only the plan is read again.
  const shown: View = view ?? (payload && payload.plan.nodes.length > 0 ? "plan" : "record");
  const live = shown === "plan" && !exported();
  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, EVERY);
    return () => window.clearInterval(timer);
  }, [live, refresh]);

  const token = payload?.plan.token ?? null;
  const write = useCallback(
    async (op: string, body: unknown): Promise<string | null> => {
      try {
        await send(op, body, token);
      } catch (trouble) {
        return trouble instanceof Error ? trouble.message : String(trouble);
      }
      await refresh();
      return null;
    },
    [token, refresh],
  );

  if (failed && !payload) return <p className="state">The server did not answer.</p>; // a failed poll keeps the last good plan
  if (!payload) return <p className="state">Reading this repo&rsquo;s plan and the records of its runs.</p>;

  const { graph, plan, runs } = payload;
  const lit = chain(graph, selection) ?? (chip ? matching(graph, chip) : null);
  const current = graph.run.sessions.map((s) => s.id);

  if (shown === "plan") {
    return (
      <div className="app plan">
        <PlanHeader plan={plan} view={shown} onView={setView} />
        <main className="centre">
          <PlanStrip plan={plan} onPick={setPicked} write={write} />
          <PlanView plan={plan} picked={picked} onPick={setPicked} />
        </main>
        <PlanInspector plan={plan} picked={picked} write={write} />
      </div>
    );
  }

  return (
    <div className="app">
      <Header
        graph={graph}
        chip={chip}
        onChip={(next) => {
          setChip(next);
          setSelection(null);
        }}
        view={shown}
        onView={setView}
        planned={plan.nodes.length}
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
