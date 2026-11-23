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
const ON = { on: true, tab: false, shut: false };

/** A window's life: each snapshot in turn, the tab there as `tab` says before it, and closed by a person before
 *  it as `shut` says; which of them opened it. */
function walk(states: State[], o: { on?: boolean; tab?: (i: number) => boolean; shut?: (i: number) => boolean } = {}): number[] {
  const opened: number[] = [];
  let was: Seen | null = null;
  states.forEach((s, i) => {
    const now = seen(s);
    if (opens(was, now, { on: o.on ?? true, tab: o.tab?.(i) ?? false, shut: o.shut?.(i) ?? false })) opened.push(i);
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

test("the side bar coming into view opens the tab on any plan, unless it is there, was closed, or the setting is off", () => {
  for (const s of [empty, done(running), proposals]) assert.equal(opens(seen(s), seen(s), { ...ON, sidebar: true }), true);
  assert.equal(opens(null, seen(empty), { ...ON, sidebar: true, tab: true }), false);
  assert.equal(opens(null, seen(empty), { ...ON, sidebar: true, shut: true }), false);
  assert.equal(opens(null, seen(empty), { ...ON, sidebar: true, on: false }), false);
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

const working = { ...proposals, tasks: proposals.tasks.map((t, i) => ({ ...t, state: i ? t.state : "running" as const })) };

test("a tab that is not there and that nobody closed opens on each start, and on nothing between two", () => {
  // the plan moves on, and nothing opens
  assert.deepEqual(walk([proposals, proposals, working, { ...working, cursor: working.cursor + 1 }]), [0]);
  // the planner's tasks arriving is the same plan; the run that starts is the next start
  assert.deepEqual(walk([empty, drafting, proposals, run(proposals, true), run(working, true)]), [1, 3]);
  // the run ending opens nothing; the next plan that appears does
  assert.deepEqual(walk([running, run(running, false), done(running), drafting]), [0, 3]);
});

test("a person who closes the tab is not chased: no start opens it again in this window", () => {
  // a round of `graphene auto` after another: a plan appears and a run starts, twice a round
  const rounds = [proposals, run(working, true), done(running), drafting, proposals, run(working, true), done(running), drafting];
  assert.deepEqual(walk(rounds), [0, 1, 3, 5, 7], "the cost of chasing: nobody closed it, and every start opens it");
  assert.deepEqual(walk(rounds, { shut: (i) => i > 0 }), [0], "closed after the first: the run that starts and the plans that appear open nothing");
  // closed, asked for (the tab is there for a while), closed again: it stays closed again
  assert.deepEqual(walk(rounds, { tab: (i) => i === 1 || i === 2, shut: (i) => i > 0 }), [0]);
  assert.equal(opens(null, seen(running), { on: true, tab: false, shut: true }), false, "not even the first read, were the close before it");
});

test("a tab that is already there is left as it is, and a start it sat through is not made up for later", () => {
  assert.equal(opens(null, seen(proposals), { ...ON, tab: true }), false);
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
  const at = (s: State, on: boolean) => { const now = seen(s), o = opens(was, now, { ...ON, on }); was = now; return o; };
  assert.equal(at(proposals, false), false);
  assert.equal(at(proposals, true), false, "the window's opening is past");
  assert.equal(at(run(proposals, true), true), true);
});
