import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { autoLine, autoNews, errorOf, headline, mdText, parseState, summary, usd } from "../src/state.ts";

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8");

test("the empty plan parses to no tasks and a zero scoreboard", () => {
  const s = parseState(fixture("empty"));
  assert.equal(s.schema, 1);
  assert.deepEqual(s.tasks, []);
  assert.deepEqual(s.goals, []);
  assert.equal(s.auto, null);
  assert.equal(s.scoreboard.total, 0);
  assert.equal(summary(s), "no plan yet");
  assert.equal(autoLine(s), "");
});

test("proposals carry their question, their sub-goals and the edges between them", () => {
  const s = parseState(fixture("proposals"));
  assert.equal(s.tasks.length, 4);
  assert.ok(s.tasks.every((t) => t.state === "proposed" && t.needs_you));
  assert.equal(s.questions[0]?.about, "greet");
  assert.deepEqual(s.goals.map((g) => g.id), ["words", "api"]);
  assert.equal(s.edges.length, 4);
  assert.equal(summary(s), "4 need you");
});

test("a running plan with three forks keeps each fork's letter, model, state and the kept one", () => {
  const s = parseState(fixture("running"));
  const greet = s.tasks.find((t) => t.id === "greet")!;
  assert.equal(greet.state, "running");
  assert.equal(greet.model, "Nano");
  assert.deepEqual(greet.forks.map((f) => [f.letter, f.model, f.state]),
                   [["a", "Nano", "gave up"], ["b", "Nano", "passed"], ["c", "Super", "running"]]);
  assert.deepEqual(greet.kept, { letter: "b", why: "4 lines against 12", by: "rule" });
  assert.equal(s.run.pid, 4242);
  assert.equal(summary(s), "2 working · 2 need you · $0.42");
});

test("auto waiting reads as a header with the stage and why, then the round and the spend of the budget", () => {
  const s = parseState(fixture("auto"));
  assert.equal(s.envelope.auto, "on");
  assert.equal(s.auto?.stage, "waits");
  assert.equal(autoLine(s), "waits for you: the goal's check is still red after 2 rounds · round 2 of 3 · $1.37 of $2.00", "why first: a narrow tab cuts the bookkeeping");
  assert.equal(summary(s), "1 needs you · $1.37", "the task that needs you says it waits");
  assert.equal(summary({ ...s, scoreboard: { ...s.scoreboard, need_you: 0 } }), "waits for you · 3 of 4 done · $1.37", "waiting on no task (a key, the budget): said");
  // a practice run and a replay spend nothing: no screen says a cost, the status bar and auto's line alike
  const replay = { shown: "a scripted stand-in, no model ran", day: "", repository: "" };
  for (const free of [{ ...s, stand_in: true }, { ...s, replay }]) {
    assert.equal(autoLine(free), "waits for you: the goal's check is still red after 2 rounds · round 2 of 3");
    assert.equal(summary(free), "1 needs you");
  }
  const done = { ...s, stand_in: true, auto: { ...s.auto!, stage: "done" } };
  assert.equal(autoNews(s, done)?.text, "Graphene finished on its own: the goal's check passed in round 2");
});

test("the status bar leads with auto's round while it runs on its own, and says nothing of it once done", () => {
  const done = parseState(fixture("real-auto"));
  assert.equal(summary(done), "4 of 4 done · $0.02");
  const left = { ...done, scoreboard: { ...done.scoreboard, proven: 1, need_you: 0 } };
  assert.equal(summary(left), "1 of 4 done · $0.02", "not done beside three tasks that wait");
  const going = parseState(JSON.stringify({ ...JSON.parse(fixture("real-auto")),
    auto: { round: 1, rounds: 2, stage: "running", spent: 0.01, budget: 2 } }));
  assert.ok(summary(going).startsWith("on its own, round 1 · "), summary(going));
});

test("a planner writing a plan is `drafting`: its steps so far, each with what of its lines is complete", () => {
  const s = parseState(fixture("drafting"));
  assert.equal(s.drafting?.by, "claude");
  assert.equal(s.drafting?.live, true);
  assert.deepEqual(s.drafting?.steps.map((d) => [d.id, d.parent, d.leaf]), [["export", null, false], ["failing", "export", true], ["rows", "export", true],
                                                                           ["button", "export", true], ["empty", "export", true]]);
  assert.deepEqual(s.drafting?.steps[2], { id: "rows", title: "Export the visible rows", parent: "export", leaf: true, scope: ["src/export/**"],
                                           check: "pytest -k export", needs: ["failing"] });
  assert.deepEqual(s.drafting?.steps[4]?.scope, [], "its files line is not written yet");
  assert.equal(parseState(fixture("empty")).drafting, null, "an older CLI says nothing: no planner is seen writing");
  assert.equal(parseState(JSON.stringify({ drafting: null })).drafting, null);
  assert.equal(parseState(JSON.stringify({ drafting: [] })).drafting, null, "junk is no planner writing");
  assert.deepEqual(parseState(JSON.stringify({ drafting: { by: "codex", steps: [{ title: "no id" }, { id: "a" }] } })).drafting,
                   { by: "codex", live: false, steps: [{ id: "a", title: "", parent: null, leaf: true, scope: [], check: null, needs: [] }] });
});

test("a task's scope in plain view: its files, what was written, what was stopped, its check before and after, its tokens, how it is held", () => {
  const s = parseState(JSON.stringify({
    tree: ["src/", "tests/", "README.md"], allows: ["graphene node *", "graphene plan *"],
    tasks: [{
      id: "rows", title: "Export the visible rows", state: "running", scope: ["src/export/**"],
      files: ["src/export/csv.py", "src/export/rows.py"], files_n: 4, touched: ["src/export/csv.py"],
      stops: [{ path: "README.md", at: "2026-11-17T05:41:02Z", how: "Write" }, { at: "no path" }],
      checked: { before: "red", after: null }, tokens: { read: 41200, cached: 30100, written: 6100, turns: 14 },
      held: { state: "refused", by: "claude" },
    }, { id: "old", title: "an older CLI's task", held: { state: "a shield nobody proved" } }],
  }));
  assert.deepEqual(s.tree, ["src/", "tests/", "README.md"]);
  assert.deepEqual(s.allows, ["graphene node *", "graphene plan *"]);
  const rows = s.tasks[0]!;
  assert.deepEqual([rows.files, rows.filesN, rows.touched], [["src/export/csv.py", "src/export/rows.py"], 4, ["src/export/csv.py"]]);
  assert.deepEqual(rows.stops, [{ path: "README.md", at: "2026-11-17T05:41:02Z", how: "Write" }]);
  assert.deepEqual(rows.checked, { before: "red", after: null });
  assert.deepEqual(rows.tokens, { read: 41200, cached: 30100, written: 6100, turns: 14 });
  assert.deepEqual(rows.held, { state: "refused", by: "claude" });
  const old = s.tasks[1]!; // what the snapshot does not say is nothing, and never a hold nobody proved
  assert.deepEqual([old.files, old.filesN, old.touched, old.stops, old.checked, old.tokens], [[], 0, [], [], { before: null, after: null }, null]);
  assert.deepEqual(old.held, { state: "", by: "" });
  assert.deepEqual([parseState("{}").tree, parseState("{}").allows], [[], null], "no list named: any command");
});

test("missing keys take defaults and unknown keys are ignored", () => {
  const s = parseState(JSON.stringify({
    schema: 2, goal: "x", colour: "mauve",
    tasks: [{ id: "a", title: "A", state: "running", shiny: true, forks: [{ letter: "a" }] }, { title: "no id" }],
    edges: [["a", "ghost", "needs"], ["a", "a"], "junk"],
  }));
  assert.equal(s.schema, 2);
  assert.equal(s.tasks.length, 1);
  const a = s.tasks[0]!;
  assert.equal(a.state, "running");
  assert.deepEqual(a.scope, []);
  assert.equal(a.kept, null);
  assert.deepEqual(a.forks[0], { letter: "a", state: "", why: "", lines: null, model: "", usd: null, attempts: 0, idle: null, checkout: null });
  assert.deepEqual([a.why, a.checkout, a.base, a.attempts, a.offers], ["", null, null, 0, {}]); // the contract's siblings, absent on an older CLI
  assert.equal(s.replay, null);
  assert.deepEqual(s.edges, [["a", "a", "needs"]]); // an edge to a task that is not there is dropped
  assert.equal(s.envelope.auto, "off");
  assert.equal(s.scoreboard.total, 1);
  assert.equal(s.run.going, false);
});

test("a state word the extension does not know reads as waiting, and an agent number may be a number", () => {
  const s = parseState(JSON.stringify({ tasks: [{ id: "a", state: "dancing", agent: 2 }] }));
  assert.equal(s.tasks[0]?.state, "waiting");
  assert.equal(s.tasks[0]?.agent, "2");
});

test("dollars read as the cockpit shows them", () => {
  assert.equal(usd(0.42), "$0.42");
  assert.equal(usd(0.004), "$0.004");
  assert.equal(usd(0.0002), "<$0.001"); // a stand-in's run: not "$0.000"
  assert.equal(usd(0), "");
  assert.equal(usd(null), "");
  assert.equal(usd(12), "$12.00");
});

test("bad JSON throws, so the caller shows a CLI error rather than an empty plan", () => {
  assert.throws(() => parseState("not json"));
});

test("a real snapshot, `graphene state --json` at the end of the --auto replay, parses whole", () => {
  // made by replaying src/graphene_map/demo-auto.jsonl to its last frame and running `graphene state --json` there
  const s = parseState(fixture("real-auto"));
  assert.equal(s.schema, 1);
  assert.deepEqual(s.tasks.map((t) => [t.id, t.state]), [["top", "done"], ["reading", "done"], ["hyphens", "done"], ["count-test", "done"]]);
  assert.ok(s.tasks.every((t) => t.model === "stand-in-Nano" && t.forks.length === 3));
  assert.deepEqual(s.tasks[0]!.forks.map((f) => f.state), ["passed", "passed", "gave up"]);
  assert.equal(autoLine(s), "done on its own · round 2 of 3 · $0.02 of $2.00");
});

test("auto mode's news is said once, when its round's stage changes, never on the first read", () => {
  const at = (stage: string, round: number, why = "") => parseState(JSON.stringify({ schema: 1, envelope: { auto: "on" },
    auto: { round, rounds: 2, stage, spent: 0.42, budget: 2, check: null, why } }));
  assert.equal(autoNews(null, at("waits", 1, "a question")), null);
  assert.equal(autoNews(at("running", 1), at("running", 1)), null);
  assert.deepEqual(autoNews(at("running", 1), at("waits", 1, "t1 has no check")),
                   { kind: "waits", text: "Graphene waits for you: t1 has no check" });
  assert.deepEqual(autoNews(at("checking", 1), at("fixing", 2, "FAIL: test_x")),
                   { kind: "fixing", text: "Graphene, on its own: the goal's check failed (FAIL: test_x); round 2 plans the fix" });
  assert.deepEqual(autoNews(at("checking", 2), at("done", 2)),
                   { kind: "done", text: "Graphene finished on its own: the goal's check passed in round 2 · $0.42 of $2.00" });
});

test("a hover reads the plan's words as text: no link, image, HTML or icon of an agent's renders", () => {
  const said = mdText("look ![x](https://e.vil/p.png?k=1) [ok](command:x) <img src=y> $(alert) a`b\nc");
  assert.ok(!/(?<!\\)[!\[\]()<>`$:]/.test(said), said); // every one of them escaped, so read as itself
  assert.ok(!said.includes("\n"));
  assert.equal(mdText("greet says hi"), "greet says hi"); // spaces stay, so it wraps
  assert.equal(mdText("a_b *c*"), "a\\_b \\*c\\*");
});

test("auto waiting on a key says `graphene key set` in its notification, where the Set Key button finds it", () => {
  const base = JSON.parse(fixture("real-auto"));
  const going = parseState(JSON.stringify({ ...base, auto: { round: 1, rounds: 2, stage: "planning", spent: 0, budget: 2 } }));
  const why = "the planner could not start: NEBIUS_API_KEY is not set: Token Factory needs a key (tokenfactory.nebius.com); "
    + "`graphene key set` keeps one";
  const waits = parseState(JSON.stringify({ ...base, auto: { round: 1, rounds: 2, stage: "waits", spent: 0, budget: 2, why } }));
  const said = autoNews(going, waits);
  assert.equal(said?.kind, "waits");
  assert.ok(/`graphene key set(?: --endpoint (\w+))?`/.test(said!.text), said!.text);
});

test("the contract's siblings parse when the CLI has them: a hand-back's why and offers, a fork's idle, a replay's header", () => {
  const s = parseState(JSON.stringify({
    schema: 1, replay: { shown: "a scripted stand-in, no model ran", day: "2026-10-26", repository: "wordkit" },
    tasks: [{ id: "a", title: "A", state: "came back", why: "needs app.py", checkout: "/w/a", base: "abc123", attempts: 2,
              offers: { w: ["node", "widen", "a", "app.py"], junk: "not argv" },
              forks: [{ letter: "b", state: "running", idle: 3.5, attempts: 1, checkout: "/w/a-b" }] }],
  }));
  const a = s.tasks[0]!;
  assert.deepEqual([a.why, a.checkout, a.base, a.attempts], ["needs app.py", "/w/a", "abc123", 2]);
  assert.deepEqual(a.offers, { w: ["node", "widen", "a", "app.py"] });
  assert.deepEqual([a.forks[0]!.idle, a.forks[0]!.attempts, a.forks[0]!.checkout], [3.5, 1, "/w/a-b"]);
  assert.deepEqual(s.replay, { shown: "a scripted stand-in, no model ran", day: "2026-10-26", repository: "wordkit" });
});

test("the no-plan line is a status, not a snapshot: `state --json` on exit 1 and the stream mid-way print it", () => {
  // what `graphene state --json` prints while `graphene init` still asks at its terminal (the store is there)
  const asking = '{"schema": 1, "error": "nothing is set up or planned here yet: `graphene init`, then `graphene ask`"}';
  assert.equal(errorOf(asking), "nothing is set up or planned here yet: `graphene init`, then `graphene ask`");
  assert.equal(errorOf(fixture("empty")), null);
  assert.equal(errorOf("not json"), null);
  assert.throws(() => parseState(asking), /graphene init/); // never an empty plan
});

test("`stand_in` rides through as a sibling of `replay`, false when the CLI does not say it", () => {
  assert.equal(parseState(JSON.stringify({ schema: 1, stand_in: true })).stand_in, true);
  assert.equal(parseState(JSON.stringify({ schema: 1, stand_in: "yes" })).stand_in, false);
  assert.equal(parseState(fixture("running")).stand_in, false);
});

test("a task's attempts, approval and owner come from `plan --json`: unread until then, and junk reads as nothing", async () => {
  const { parseContracts, withContracts, parseState } = await import("../src/state.ts");
  const s = parseState(JSON.stringify({ tasks: [{ id: "n1", title: "a" }, { id: "n2", title: "b" }] }));
  assert.deepEqual(s.tasks.map((t) => [t.planned, t.signoff, t.owner]), [[null, null, ""], [null, null, ""]]);
  const c = parseContracts(JSON.stringify({ nodes: [{ id: "n1", signoff: true, owner: "alex", forks: 3 }, { id: "n2", signoff: false, owner: "agent" }, { title: "no id" }] }));
  assert.deepEqual(c.get("n1"), { planned: 3, signoff: true, owner: "alex" });
  assert.deepEqual(c.get("n2"), { planned: null, signoff: false, owner: "agent" }, "forks unsaid: the limits' number decides");
  const filled = withContracts(s, c);
  assert.deepEqual(filled.tasks.map((t) => [t.planned, t.signoff, t.owner]), [[3, true, "alex"], [null, false, "agent"]]);
  assert.deepEqual(withContracts(filled, parseContracts("not json")).tasks[0]!.signoff, null, "a task the plan's JSON does not name is unread again");
  assert.equal(parseContracts("{}").size, 0);
});

test("engine prose uses the screen's task, files and attempt words while commands and paths stay exact", async () => {
  const { screenWords } = await import("../src/state.ts");
  assert.equal(screenWords("n1: 3 forks need a check; a leaf is outside its scope"), "n1: 3 attempts need a check; a task is outside its files");
  const command = "`graphene node set n1 --forks 3 --scope node.py`";
  assert.equal(screenWords(command), command);
  assert.equal(screenWords("fork.py node/file.py --forks scope.json"), "fork.py node/file.py --forks scope.json");
  assert.equal(screenWords("graphene node done n1"), "graphene node done n1");
});

test("what was asked stays the title once the news no longer says it: the goal first, then the news, then what was kept", () => {
  const s = parseState(fixture("running"));
  const ask = { ...s, goal: "", news: ["you asked: a --json flag", "top started"] };
  assert.equal(headline(ask), "a --json flag");
  assert.equal(headline({ ...ask, news: ["top started"], kept: "a --json flag" }), "a --json flag", "scrolled out of the news, kept by the session");
  assert.equal(headline({ ...ask, kept: "an older ask" }), "a --json flag", "a new ask in the news is the one");
  assert.equal(headline({ ...ask, goal: "the goal", kept: "an ask" }), "the goal");
});

test("the title is the ask whole: the news cuts it at 60 characters, the snapshot's `asked` does not", () => {
  const whole = "wordkit grows three things: a --top N option, a reading time in minutes, and a --json flag";
  const s = parseState(JSON.stringify({ schema: 1, asked: whole, news: ["you asked: wordkit grows three things: a --top N option, a reading tim…", "top started"] }));
  assert.equal(s.asked, whole);
  assert.equal(headline(s), whole);
  assert.equal(headline({ ...s, asked: "" }), "wordkit grows three things: a --top N option, a reading tim…", "an older CLI says no `asked`: the news line, cut");
  assert.equal(headline({ ...s, asked: "an ask after it" }), "wordkit grows three things: a --top N option, a reading tim…", "another ask's words never title this one");
  assert.equal(headline({ ...s, news: ["you asked: a --json flag"], asked: "a --json flag" }), "a --json flag", "short: the same words");
  assert.equal(headline({ ...s, news: [] }), "", "out of the news, and nothing kept: the session's, not the snapshot's, keeps it (session.ts kept)");
  assert.equal(parseState(JSON.stringify({ schema: 1 })).asked, "", "an older snapshot: none");
});
