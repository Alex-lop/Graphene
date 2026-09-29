// What the tree forces on the page, rendered: the outline is indented by the depth Python computed,
// a sub-goal says how many of the leaves beneath it are done instead of a scope and a check, and a
// node's detail opens with why it is being done at all. React renders to a string here, so this
// needs no browser and no test framework beyond the one already installed.

import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { layoutFor, shownLayout, type Mode } from "./model";
import { LayoutBar, PlanHeader, PlanInspector, PlanStrip, PlanTopDown, PlanTree, PlanView, panFilter, size, startScale, wrap } from "./Plan";
import type { Plan, PlanEdge, PlanNode } from "./types";

const node = (id: string, extra: Partial<PlanNode> = {}): PlanNode => ({
  id,
  title: `do ${id}`,
  goal: "",
  scope: ["src/**"],
  check: "true",
  signoff: false,
  needs: [],
  owner: "agent",
  parent: null,
  aside: false,
  sub_goal: false,
  depth: 0,
  why: ["people can sign in"],
  leaves_done: 0,
  leaves_total: 0,
  state: "open",
  display_state: "ready",
  rev: 1,
  executor: null,
  started_at: null,
  finished_at: null,
  waits: [],
  log: [],
  forks: [],
  decided: [],
  lane: "agent",
  column: 0,
  row: 0,
  x: 0,
  y: 0,
  tree_w: 200,
  tree_x: 0,
  tree_y: 124,
  width: 200,
  height: 76,
  ...extra,
});

const plan: Plan = {
  version: 1,
  repo: "toy",
  goal: "people can sign in",
  person: "alex",
  paused: false,
  width: 200,
  height: 76,
  nodes: [
    node("signin", { sub_goal: true, display_state: "sub-goal", scope: [], check: null, leaves_total: 2 }),
    node("api", { parent: "signin", depth: 1, why: ["people can sign in", "do signin (signin)"] }),
    node("typed", { aside: true, state: "done", display_state: "done" }),
  ],
  lanes: [],
  edges: [],
  counts: { proposed: 0, open: 2, running: 0, review: 0, done: 1 },
  waiting_on_person: [],
  loose: [],
  all_done: false,
  forecast: { runs: [], waits: [] },
  holes: { scope: "", check: "", stop: "", person: "" },
  writable: false,
  token: null,
  critical: [],
  at_once: [],
  tree_width: 200,
  tree_height: 200,
  tree_goal: [0, 0],
  tree_links: [],
  view: "auto",
  board: { open: [], folded: [], counts: "", standing: null },
};

// feeds, as plan_view.py lays it out: two chains into one leaf, the longer one critical
const edge = (source: string, target: string, critical: boolean): PlanEdge => ({ id: `${source}>${target}`, source, target, points: [[200, 38], [240, 38]], critical });
const feeds: Plan = {
  ...plan,
  nodes: [node("xml-reader"), node("xml-wire", { needs: ["xml-reader"], display_state: "waiting" }), node("zero-rule"), node("xml-e2e", { needs: ["xml-wire", "zero-rule"], display_state: "waiting" })],
  edges: [edge("xml-reader", "xml-wire", true), edge("xml-wire", "xml-e2e", true), edge("zero-rule", "xml-e2e", false)],
  critical: ["xml-reader", "xml-wire", "xml-e2e"],
  at_once: ["xml-reader", "zero-rule"],
};

test("the tree is indented by depth, and a sub-goal counts its leaves instead of naming a scope", () => {
  const html = renderToStaticMarkup(<PlanTree plan={plan} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/data-tree="signin" data-depth="0" style="padding-left:12px"/);
  expect(html).toMatch(/data-tree="api" data-depth="1" style="padding-left:32px"/); // one level in
  expect(html).toContain("0/2 done");
  expect(html).toContain("sub-goal");
  expect(html.indexOf('data-tree="signin"')).toBeLessThan(html.indexOf('data-tree="api"'));
  expect(html).not.toContain('data-tree="typed"'); // a done aside folds into one line below the tree
  expect(html).toContain("✓ 1 done from a prompt");
});

test("under a leaf that forked, the tree of sandboxes: each fork, its model and how it ended, the winner marked", () => {
  const forked: Plan = {
    ...plan,
    nodes: [
      node("greet", {
        state: "done",
        display_state: "done",
        forks: [
          { fork: 1, of: 2, model: "nvidia/Nemotron-3-Nano-fake", state: "check failed", why: "its check failed (exit 1)", checkpoint: "made", ops: 6, seconds: 4.25 },
          { fork: 2, of: 2, model: "nvidia/Nemotron-3-Nano-fake", state: "passed", why: "its check passed first", checkpoint: "forked", ops: 4, seconds: 2 },
        ],
      }),
      node("schema"),
    ],
  };
  const html = renderToStaticMarkup(<PlanTree plan={forked} picked={null} onPick={() => undefined} />);
  const under = html.slice(html.indexOf('data-tree="greet"'), html.indexOf('data-tree="schema"'));
  expect(under).toContain('data-forks="greet"'); // inside the leaf's own item: a level in, not a node
  expect(under).toMatch(/data-fork="1" data-state="check failed">.*<b>fork 1 of 2<\/b><span class="what">Nemotron-3-Nano-fake/);
  expect(under).toContain("its check failed (exit 1) · sandbox made, 6 operations, 4.3 s");
  expect(under).toMatch(/data-fork="2" data-state="passed"><button type="button" class="row fork won">.*✓ won/);
  expect(under).toContain("sandbox forked from the checkpoint, 4 operations, 2.0 s");
  expect(html.slice(html.indexOf('data-tree="schema"'))).not.toContain("data-fork"); // a leaf that did not fork
});

test("a fork still running shows no count: its row holds the operations it started with, and the terminal waits too", () => {
  const running: Plan = {
    ...plan,
    nodes: [
      node("greet", {
        state: "running",
        display_state: "running",
        forks: [{ fork: 1, of: 1, model: "nvidia/Nemotron-3-Nano-fake", state: "running", why: "", checkpoint: "forked", ops: 0, seconds: 0 }],
      }),
    ],
  };
  const html = renderToStaticMarkup(<PlanTree plan={running} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/data-fork="1" data-state="running">.*<b>fork 1 of 1<\/b>/);
  expect(html).not.toContain("operations");
  expect(html).not.toContain("0.0 s");
});

test("a node's detail opens with the path from the goal down to it, root first", () => {
  const html = renderToStaticMarkup(
    <PlanInspector plan={plan} picked="api" write={async () => null} />,
  );
  const why = html.slice(html.indexOf('data-testid="why"'));
  expect(why.indexOf("people can sign in")).toBeLessThan(why.indexOf("do signin (signin)"));
  expect(why).toMatch(/style="padding-left:12px">do signin \(signin\)/); // a level in from the root
  expect(html).toContain("src/**"); // and a leaf still says what it may touch
});

test("with no Claude Code session recorded, the record screen cannot be opened and the button says why", () => {
  // a run by any other executor (graphene run --with …) records no session: its record is on the plan
  const header = (recorded: number) =>
    renderToStaticMarkup(<PlanHeader plan={plan} view="plan" onView={() => undefined} recorded={recorded} />);
  const record = (html: string) => html.slice(html.lastIndexOf("<button", html.indexOf("the record")));
  expect(record(header(0))).toMatch(/^<button[^>]* disabled="" title="no Claude Code session was recorded in this repo/);
  expect(record(header(1))).not.toContain("disabled");
});

test("the page draws the plan the way its shape calls for: the graph when anything waits and it fits at 0.8, else the tree when it fits, else the outline", () => {
  // feeds' graph is 132 + 440 + 24 = 596 px wide; its tree 200 + 32
  const wide = { ...feeds, width: 440, tree_width: 200 };
  expect(layoutFor(wide, 2000)).toEqual(["graph", "some nodes wait on others, and the graph fits"]);
  expect(layoutFor(wide, 596 * 0.8)[0]).toBe("graph"); // drawn at 0.8, still readable
  expect(layoutFor(wide, 596 * 0.8 - 1)).toEqual(["tree", "the graph is too wide for the window, and the tree fits"]);
  expect(layoutFor({ ...wide, tree_width: 4000 }, 300)).toEqual(["outline", "the graph and the tree are too wide for the window"]);
  expect(layoutFor(plan, 1000)).toEqual(["tree", "nothing waits on anything, and the tree fits"]);
  expect(layoutFor({ ...plan, tree_width: 4000 }, 1000)).toEqual(["outline", "nothing waits on anything, and the tree is too wide for the window"]);
});

test("a drawing starts at the scale that fits its width, never below 0.6, and one only taller than its pane is not shrunk", () => {
  expect(startScale(500, 900)).toBe(1); // narrower than the pane: however tall, drawn at 1 and panned down
  expect(startScale(1000, 900)).toBe(0.9);
  expect(startScale(3000, 900)).toBe(0.6); // a layout the viewer picked though it is far too wide: readable, dragged
});

test("the tree's boxes are as wide as Python sized them", () => {
  const sized: Plan = { ...plan, nodes: [node("a", { tree_w: 140 })] };
  const html = renderToStaticMarkup(<PlanTopDown plan={sized} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/data-node="a"[^>]*><rect class="box" width="140"/);
});

test("the switch has auto and the three layouts, says what is drawn and why, and says the critical path and what can start at once in words, as the terminal names it", () => {
  const bar = (mode: Mode) => renderToStaticMarkup(<LayoutBar plan={feeds} {...shownLayout(feeds, mode, 2000)} onLayout={() => undefined} />);
  const html = bar(null);
  expect(html).toMatch(/data-layout="graph"/);
  expect(html.match(/<button/g)).toHaveLength(4);
  expect(html).toMatch(/class="on" aria-pressed="true"[^>]*>auto<\/button>.*aria-pressed="false"[^>]*>outline<\/button>.*aria-pressed="false"[^>]*>tree<\/button>.*aria-pressed="false"[^>]*>graph<\/button>/);
  expect(html).toContain("auto chose the graph: some nodes wait on others, and the graph fits");
  expect(html).toContain("critical path: xml-reader → xml-wire → xml-e2e");
  expect(html).toContain("2 at once: xml-reader, zero-rule");
  expect(bar("tree")).toMatch(/data-layout="tree".*class="on" aria-pressed="true"[^>]*>tree<\/button>.*your choice, on this page only/);
  expect(renderToStaticMarkup(<LayoutBar plan={plan} {...shownLayout(plan, null, 2000)} onLayout={() => undefined} />)).toContain("no critical path: nothing waits on anything");
});

test("the page opens in the repository's view setting, the one the terminal reads, and a click changes this page only", () => {
  expect(shownLayout({ ...feeds, view: "auto" }, null, 2000).layout).toBe("graph");
  expect(shownLayout({ ...feeds, view: "outline" }, null, 2000)).toMatchObject({ layout: "outline", mode: "outline", why: "this repo's view setting: outline" });
  expect(shownLayout({ ...feeds, view: "dag" }, null, 2000)).toMatchObject({ layout: "graph", mode: "graph", why: "this repo's view setting: the graph (dag in graphene watch)" }); // the terminal's name for it, said beside the page's (judge 11)
  expect(shownLayout({ ...feeds, view: "tree" }, "auto", 2000)).toMatchObject({ layout: "graph", mode: "auto" }); // a click on auto brings the choice back
  expect(shownLayout({ ...feeds, view: "something else" }, null, 2000).mode).toBe("auto");
});

test("in the graph the critical path is drawn heavier, its edges and its boxes, and a leaf that can start now is marked", () => {
  const html = renderToStaticMarkup(<PlanView plan={feeds} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/data-edge="xml-reader&gt;xml-wire" data-critical="true" class="edge critical"/);
  expect(html).toMatch(/data-edge="xml-wire&gt;xml-e2e" data-critical="true" class="edge critical"/);
  expect(html).toMatch(/data-edge="zero-rule&gt;xml-e2e" data-critical="false" class="edge"/);
  expect(html).toMatch(/class="node critical now" data-node="xml-reader"/);
  expect(html).toMatch(/class="node critical" data-node="xml-e2e"/);
  expect(html).toMatch(/class="node now" data-node="zero-rule" data-state="ready" data-critical="false" data-now="true"/);
  expect(html).toMatch(/data-pans="false"/); // a static render measures no pane, so it draws the plan whole
});

test("the tree is drawn top-down from Python's positions: the goal on top, a link to each node, the same boxes", () => {
  const tree: Plan = {
    ...plan,
    tree_goal: [112, 0],
    tree_links: [{ id: ">signin", source: "", target: "signin", points: [[212, 76], [212, 124]], critical: false }],
  };
  const html = renderToStaticMarkup(<PlanTopDown plan={tree} picked="api" onPick={() => undefined} />);
  expect(html).toMatch(/data-goal="" transform="translate\(128,16\)"/);
  expect(html).toContain("people can sign in");
  expect(html).toMatch(/data-link="&gt;signin" class="edge link" points="228,92 228,140"/);
  expect(html).toMatch(/class="node" data-node="signin" data-state="sub-goal"[^>]*transform="translate\(16,140\)"/);
  expect(html).toMatch(/class="node on" data-node="api"/);
  expect(html).not.toContain("lane-band"); // the tree has no lanes: whose a node is, is in the box
});

test("a box's id line is cut to the box like its title, so a long id never runs into the next box", () => {
  const long: Plan = { ...plan, nodes: [node("a-thirty-one-character-long-id1")] };
  const html = renderToStaticMarkup(<PlanTopDown plan={long} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/class="who">a-thirty-one-character-lon[^<]*…<title>a-thirty-one-character-long-id1<\/title>/);
});

test("the at-once line names at most five leaves and then how many more", () => {
  const many: Plan = { ...feeds, at_once: ["a", "b", "c", "d", "e", "f", "g", "h"] };
  const html = renderToStaticMarkup(<LayoutBar plan={many} {...shownLayout(many, null, 2000)} onLayout={() => undefined} />);
  expect(html).toContain("8 at once: a, b, c, d, e and 3 more");
  expect(html).toMatch(/title="a, b, c, d, e, f, g, h"/); // all of them, on hover
});

test("on a phone one finger scrolls the page and two pan and zoom the drawing; a mouse drags it", () => {
  const touch = (n: number) => ({ type: "touchstart", touches: { length: n } }) as unknown as Event;
  expect(panFilter(touch(1))).toBe(false);
  expect(panFilter(touch(2))).toBe(true);
  expect(panFilter({ type: "mousedown", button: 0 } as unknown as Event)).toBe(true);
  expect(panFilter({ type: "mousedown", button: 2 } as unknown as Event)).toBe(false); // the context menu
});

// -- walks.md: what three walkers found on the exported page, 2026-09-28 --------------------------------

/** The markup from the tag holding `from` up to the next `to`. */
const cut = (html: string, from: string, to?: string): string => {
  const at = html.indexOf(from);
  return html.slice(html.lastIndexOf("<", at), to ? html.indexOf(to, at) : undefined);
};
const text = (html: string): string => html.replace(/<[^>]+>/g, "").replace(/&#x27;/g, "'").replace(/&gt;/g, ">").replace(/&lt;/g, "<").replace(/&amp;/g, "&");

// the board as the store holds it, in the terminal's words (board_rows.py)
const boarded: Plan = {
  ...feeds,
  waiting_on_person: [{ id: "xml-reader", title: "do xml-reader", why: "see why it came back" }],
  board: {
    open: [
      { id: "cents", word: "asks", text: "are XML prices already in cents?", default: "yes, whole numbers", options: ["no, dollars; convert in normalize/money.py"], about: "xml-reader", by: "the planner (graphene ask)", said: "are XML prices already in cents?" },
      { id: "summary", word: "assumes", text: "the summary line is not a product", default: null, options: [], about: null, by: "the planner (graphene ask)", said: "assumed: the summary line is not a product" },
    ],
    folded: [
      { id: "stream", word: "parked", text: "a streaming parser", default: null, options: [], about: null, by: "the planner (graphene ask)", said: "left out: a streaming parser" },
      { id: "legacy", word: "taken", text: "legacy skips the zero rule", default: "leave legacy alone", options: [], about: null, by: "the planner (graphene ask)", said: "risk: legacy skips the zero rule → leave legacy alone" },
      { id: "shape", word: "dropped", text: "keep the JSONL shape", default: null, options: [], about: null, by: "the planner (graphene ask)", said: "keep the JSONL shape" },
    ],
    counts: "1 settled · 1 parked · 1 dropped",
    standing: "conditions: protected vendor/** · read-only legacy/**",
  },
};

test("the page shows the board and the standing conditions as the terminal reads them, and answers nothing on it", () => {
  // alex 11, first 5, judge 10: the exported page had no board and no standing condition
  const html = renderToStaticMarkup(<PlanStrip plan={boarded} onPick={() => undefined} write={async () => null} />);
  const board = cut(html, 'data-testid="board"');
  expect(text(cut(board, 'data-testid="standing"', "</p>"))).toBe("conditions: protected vendor/** · read-only legacy/**");
  const cents = text(cut(board, 'data-item="cents"', "</li>"));
  expect(cents).toContain("◇ asks");
  expect(cents).toContain("are XML prices already in cents? cents");
  expect(cents).toContain("default: yes, whole numbers · 1: no, dollars; convert in normalize/money.py · about xml-reader · put up by the planner (graphene ask)");
  expect(text(cut(board, 'data-item="summary"', "</li>"))).toContain("◇ assumes");
  // settled, parked and dropped fold into the terminal's one count, which opens on what was decided
  expect(text(cut(board, "<summary>", "</summary>"))).toBe("✓ 1 settled · 1 parked · 1 dropped");
  expect(text(cut(board, 'data-item="legacy"', "</li>"))).toBe("taken legacy risk: legacy skips the zero rule → leave legacy alone");
  expect(board).not.toMatch(/<button|<input|<form/); // read-only: the terminal answers it
  expect(text(board)).toContain("answered in the terminal: graphene board");
  // the items are counted apart from the plan's own, as the terminal's status line counts them
  expect(text(cut(html, "<h3>", "</h3>"))).toBe("waiting on you (1 + 2 on the board)");
});

test("a page with no board and no conditions shows neither", () => {
  expect(renderToStaticMarkup(<PlanStrip plan={feeds} onPick={() => undefined} write={async () => null} />)).not.toContain('data-testid="board"');
});

test("a read-only page says so once, and offers no decision it cannot make", () => {
  // alex 13, first 5, judge 11: four rows said "this page cannot change the plan; it is read-only", the
  // footer said the plan is changed "from a page they opened", and the badge said it again
  const header = renderToStaticMarkup(<PlanHeader plan={boarded} view="plan" onView={() => undefined} recorded={1} />);
  expect(text(cut(header, 'class="badges"'))).toBe("read-only");
  const node = renderToStaticMarkup(<PlanInspector plan={boarded} picked="xml-reader" write={async () => null} />);
  expect(node).not.toContain("read-only");
  expect(node).not.toContain("What a person decides");
  expect(node).not.toMatch(/data-act=/);
  const copy = text(renderToStaticMarkup(<PlanInspector plan={boarded} picked={null} write={async () => null} />));
  expect(copy).toContain("This page is a copy, written by graphene ui --export. The plan changes in its repository");
  expect(copy).not.toContain("from a page they opened");
  const agents = text(renderToStaticMarkup(<PlanInspector plan={{ ...boarded, token: "t" }} picked={null} write={async () => null} />));
  expect(agents).toContain("This page was opened from an agent's shell.");
  // a page the person can write with still offers every decision
  expect(renderToStaticMarkup(<PlanInspector plan={{ ...boarded, writable: true, token: "t" }} picked="xml-reader" write={async () => null} />)).toMatch(/data-act="accept"/);
});

test("the page counts the plan in leaves, as bare graphene does, not in nodes", () => {
  // alex 20: the page said "3 nodes · 3 done" where the shell said "2 leaves, 2 done"
  const done = (id: string, extra: Partial<PlanNode> = {}) => node(id, { state: "done", display_state: "done", ...extra });
  const finished: Plan = { ...plan, nodes: [done("app", { sub_goal: true, display_state: "sub-goal", leaves_done: 2, leaves_total: 2 }), done("greet", { parent: "app" }), done("bye", { parent: "app" })] };
  expect(size(finished)).toBe("2 leaves, 2 done, 0 running");
  expect(renderToStaticMarkup(<PlanHeader plan={finished} view="plan" onView={() => undefined} recorded={1} />)).toContain("2 leaves, 2 done, 0 running");
  const overview = text(cut(renderToStaticMarkup(<PlanInspector plan={finished} picked={null} write={async () => null} />), 'data-testid="leaves"', "</dl>"));
  expect(overview).toBe("done2 of 2 leaves");
});

test("with no session recorded, the overview says in words where each executor's work is", () => {
  // alex 13, judge 10: "the record" was disabled with its reason only in a hover title
  const html = renderToStaticMarkup(<PlanInspector plan={plan} picked={null} write={async () => null} recorded={0} />);
  expect(text(cut(html, 'data-testid="unrecorded"', "</p>"))).toBe("no Claude Code session was recorded in this repo; what each executor did is in its node's record, on the plan");
  expect(renderToStaticMarkup(<PlanInspector plan={plan} picked={null} write={async () => null} recorded={2} />)).not.toContain("unrecorded");
});

test("a card's second line is its id, and whose it is only when a person's, so a 200px card is not cut", () => {
  // alex 13, judge 11: "xml-source · any agen…", "xml-feed-2 · any agen…"
  const mixed: Plan = { ...feeds, nodes: [node("xml-feed-2"), node("sign", { owner: "alex" })] };
  const html = renderToStaticMarkup(<PlanView plan={mixed} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/class="who">xml-feed-2<title>xml-feed-2<\/title>/);
  expect(html).toMatch(/class="who">sign · alex&#x27;s<title>/);
  expect(html).not.toContain("any agent");
  // alex 13: "run:python3 · finishe…": the executor by its name, and the clock whole
  const ran: Plan = { ...feeds, nodes: [node("readme", { state: "done", display_state: "done", executor: "run:executor.py", finished_at: "2026-09-28T05:17:34Z" })] };
  expect(renderToStaticMarkup(<PlanView plan={ran} picked={null} onPick={() => undefined} />)).toMatch(/class="says">executor\.py · finished \d\d:\d\d<title>/);
});

test("at once says when the leaves it counts start only once accepted", () => {
  // judge 11: "left alone, agents can reach: nothing" beside "3 at once" while nothing was accepted
  const proposed: Plan = { ...feeds, nodes: feeds.nodes.map((n) => ({ ...n, state: "proposed", display_state: "proposed" })) };
  const bar = (p: Plan) => text(renderToStaticMarkup(<LayoutBar plan={p} {...shownLayout(p, null, 2000)} onLayout={() => undefined} />));
  expect(bar(proposed)).toContain("2 at once, once accepted: xml-reader, zero-rule");
  const half: Plan = { ...feeds, nodes: feeds.nodes.map((n) => (n.id === "zero-rule" ? { ...n, state: "proposed", display_state: "proposed" } : n)) };
  expect(bar(half)).toContain("2 at once (1 once accepted): xml-reader, zero-rule");
  expect(bar(feeds)).toContain("2 at once: xml-reader, zero-rule");
  expect(bar({ ...feeds, at_once: [] })).toContain("0 at once: no leaf can start now"); // alex 13: "0 at once" was unexplained
});

test("a wait line names its leaf once", () => {
  // judge 11: "x will wait: x is a proposal nobody has accepted"
  const waits: Plan = { ...plan, forecast: { runs: [], waits: [{ id: "readme", why: ["readme is a proposal nobody has accepted"] }, { id: "test", why: ["reader came back to you"] }] } };
  const said = text(renderToStaticMarkup(<PlanStrip plan={waits} onPick={() => undefined} write={async () => null} />));
  expect(said).toContain("readme will wait: it is a proposal nobody has accepted");
  expect(said).toContain("test will wait: reader came back to you");
});

test("the tree's goal box holds the goal in two lines before it cuts it", () => {
  // judge 11: "the Northwind XML feed loa…" at 1200px
  expect(wrap("the Northwind XML feed loads like csv and json", 176, 6.4)).toEqual(["the Northwind XML feed", "loads like csv and json"]); // 27 characters a line
  expect(wrap("short", 176, 6.4)).toEqual(["short"]);
  const html = renderToStaticMarkup(<PlanTopDown plan={{ ...plan, goal: "the Northwind XML feed loads like csv and json" }} picked={null} onPick={() => undefined} />);
  expect(html).toMatch(/y="44" class="title">the Northwind XML feed<title>/);
  expect(html).toMatch(/y="60" class="title">loads like csv and json<title>/);
});

test("a node's detail lists what the board decided for it, as node show does", () => {
  // alex 11: the contract listed goal, may touch and done when, but not the decided: lines
  const decided: Plan = { ...plan, nodes: [node("api", { decided: ["are prices in cents? → no, dollars"] })] };
  const html = renderToStaticMarkup(<PlanInspector plan={decided} picked="api" write={async () => null} />);
  expect(text(cut(html, 'data-testid="decided"', "</ul>"))).toBe("are prices in cents? → no, dollars");
});
