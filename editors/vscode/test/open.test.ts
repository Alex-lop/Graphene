import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { beside, opens, seen, type Seen } from "../src/open.ts";
import { parseState, type State } from "../src/state.ts";

const fixture = (name: string) => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));
const empty = fixture("empty"), drafting = fixture("drafting"), proposals = fixture("proposals"), running = fixture("running");
/** The same plan with every task done, or with its run going or stopped. */
const done = (s: State): State => ({ ...s, tasks: s.tasks.map((t) => ({ ...t, state: "done" as const })), run: { going: false, pid: null } });
const run = (s: State, going: boolean): State => ({ ...s, run: { going, pid: going ? 4242 : null } });
const ON = { on: true, tab: false };

/** A window's life: each snapshot in turn, the tab open or closed as `tab` says before it; which of them opened it. */
function walk(states: State[], o: { on?: boolean; tab?: (i: number) => boolean } = {}): number[] {
  const opened: number[] = [];
  let was: Seen | null = null;
  states.forEach((s, i) => {
    const now = seen(s);
    if (opens(was, now, { on: o.on ?? true, tab: o.tab?.(i) ?? false })) opened.push(i);
    was = now;
  });
  return opened;
}

test("what a snapshot shows: work is a task that is not done or a planner writing; a run is going or not", () => {
  assert.deepEqual(seen(empty), { work: false, going: false });
  assert.deepEqual(seen(drafting), { work: true, going: false }, "a planner is writing: no task yet, and there is work to show");
  assert.deepEqual(seen(proposals), { work: true, going: false }, "a suggested task is not done");
  assert.deepEqual(seen(running), { work: true, going: true });
  assert.deepEqual(seen(done(running)), { work: false, going: false });
});

test("the window opens on a plan with work to show: the first snapshot opens the tab", () => {
  for (const s of [proposals, drafting, running, run(done(running), true)]) assert.equal(opens(null, seen(s), ON), true);
});

test("an empty folder and a plan whose every task is done open nothing", () => {
  assert.equal(opens(null, seen(empty), ON), false);
  assert.equal(opens(null, seen(done(running)), ON), false);
  assert.deepEqual(walk([empty, empty, done(proposals), done(proposals)]), []);
});

test("a plan appears where there was none: drafting begins, or the first tasks arrive", () => {
  assert.deepEqual(walk([empty, drafting]), [1], "an ask from Home: the planner starts writing");
  assert.deepEqual(walk([empty, proposals]), [1], "a planner whose plan arrives whole, or a task drawn by hand");
  assert.deepEqual(walk([done(running), drafting]), [1], "a finished plan, and a new ask");
});

test("a run starts: the tab opens when it turns to going, not while it goes or when it ends", () => {
  assert.deepEqual(walk([run(proposals, false), run(proposals, true)], { tab: (i) => i === 0 }), [1]);
  assert.deepEqual(walk([running, running, run(running, false)], { tab: () => false }), [0], "going at the first read is a start; staying so and ending are not");
});

test("at most once for a start: drafting, then its tasks, is one plan appearing", () => {
  assert.deepEqual(walk([empty, drafting, drafting, proposals, proposals]), [1]);
});

test("a person who closes the tab is not chased: no later snapshot reopens it until the next start", () => {
  const working = { ...proposals, tasks: proposals.tasks.map((t, i) => ({ ...t, state: i ? t.state : "running" as const })) };
  // the tab opened on the first read and was closed at once: the plan moves on, and nothing opens
  assert.deepEqual(walk([proposals, proposals, working, { ...working, cursor: working.cursor + 1 }]), [0]);
  // closed while the planner wrote: its tasks arriving is the same plan, the run that starts is the next start
  assert.deepEqual(walk([empty, drafting, proposals, run(proposals, true), run(working, true)]), [1, 3]);
  // closed during a run: the run ending opens nothing; the next plan that appears does
  assert.deepEqual(walk([running, run(running, false), done(running), drafting]), [0, 3]);
});

test("a tab that is already there is left as it is, and a start it sat through is not made up for later", () => {
  assert.equal(opens(null, seen(proposals), { on: true, tab: true }), false);
  assert.deepEqual(walk([empty, drafting, proposals, proposals], { tab: (i) => i < 2 }), [], "it was there when the plan appeared; closed after, it stays closed");
});

test("it opens beside what a person has in front, and in the group when nothing of theirs is there", () => {
  // the active tab's input, as VS Code's tabs give it: an object for a file, a diff, a terminal, an extension's page
  for (const front of [{ uri: "file:///repo/notes.md" }, { original: "a", modified: "b" }, {}, { viewType: "another.page" }]) assert.equal(beside(front), true);
  assert.equal(beside(undefined), false, "an empty group, or a page of VS Code's own (Welcome, Settings)");
  assert.equal(beside(null), false);
});

test("the setting off opens nothing, and turning it on waits for the next start", () => {
  assert.deepEqual(walk([proposals, run(proposals, true)], { on: false }), []);
  let was: Seen | null = null;
  const at = (s: State, on: boolean) => { const now = seen(s), o = opens(was, now, { on, tab: false }); was = now; return o; };
  assert.equal(at(proposals, false), false);
  assert.equal(at(proposals, true), false, "the window's opening is past");
  assert.equal(at(run(proposals, true), true), true);
});
