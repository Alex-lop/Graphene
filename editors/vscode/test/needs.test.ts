import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { answerWith, answerWords, count, DROPPABLE, keyTrouble, needs, offerOn, offerWords, pickOption, takeDefault, tryAgain } from "../src/needs.ts";
import { parseState } from "../src/state.ts";

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8");

// every kind at once, out of the cockpit's order on purpose: the view puts them in it
const mixed = parseState(JSON.stringify({
  schema: 1,
  auto: { round: 2, rounds: 2, stage: "waits", spent: 0.5, budget: 2, check: null, why: "no key: `graphene key set --endpoint nim` sets one" },
  questions: [{ id: "port", text: "which port?", default: "8000", options: ["pick a free one"], about: "api" }],
  tasks: [
    { id: "docs", title: "the docs", state: "done", scope: ["README.md"] },
    { id: "api", title: "the API", state: "review", scope: ["api.py"], changed: ["api.py"], needs_you: true },
    { id: "db", title: "the schema", state: "came back", scope: ["db/**"], why: "needs app.py, which api owns",
      offers: { w: ["node", "widen", "db", "app.py"], b: ["node", "sibling", "db", "app.py"], n: ["node", "set", "db", "--needs", "api"],
                r: ["node", "reopen", "docs", "--note", "why", "--for", "db"] } },
    { id: "mine", title: "ship it", state: "yours" },
    { id: "ui", title: "the UI", state: "proposed", scope: ["ui/**"], check: "pytest -q" },
    { id: "cli", title: "the CLI", state: "running", agent: 4, scope: ["cli.py"], stopped: ["setup.py"], tail: ["edit cli.py"] },
    { id: "ok", title: "fine", state: "running", agent: 5, scope: ["x.py"] },
  ],
}));

test("what needs you comes in the cockpit's order: auto waiting, questions, then the tasks whose move is yours", () => {
  const list = needs(mixed);
  assert.deepEqual(list.map((n) => n.kind), ["auto", "question", "sign-off", "hand-back", "yours", "proposal", "stopped"]);
  assert.deepEqual(list.map((n) => ("t" in n ? n.t.id : "q" in n ? n.q.id : "auto")), ["auto", "port", "api", "db", "mine", "ui", "cli"]);
  assert.equal(count(list), "7 need you");
  const auto = list[0]!;
  assert.ok(auto.kind === "auto" && auto.key && auto.endpoint === "nim");
});

test("a plan with nothing for you lists nothing, and a running plan lists only what waits", () => {
  assert.deepEqual(needs(parseState(fixture("empty"))), []);
  const running = needs(parseState(fixture("running")));
  assert.ok(running.length > 0 && running.every((n) => n.kind !== "auto" && n.kind !== "question"));
  const auto = needs(parseState(fixture("auto")));
  assert.deepEqual(auto.map((n) => n.kind), ["auto", "question", "proposal"]);
  assert.ok(auto[0]!.kind === "auto" && !auto[0]!.key); // the goal's check is red: no key to set
  assert.equal(count(auto.slice(0, 1)), "1 needs you");
});

test("a question's moves are the board's commands: take its default, pick an option by number, answer in words", () => {
  assert.deepEqual(takeDefault("port"), ["board", "take", "port"]);
  assert.deepEqual(pickOption("port", 1), ["board", "pick", "port", "1"]);
  assert.deepEqual(answerWords("port", "8080, the proxy has 8000"), ["board", "answer", "port", "--", "8080, the proxy has 8000"]);
  assert.deepEqual(answerWords("port", "-1, use the proxy"), ["board", "answer", "port", "--", "-1, use the proxy"], "a dash-first answer is words");
});

test("a hand-back offers what the snapshot carries, in the cockpit's order and words, then trying it again", () => {
  const db = mixed.tasks.find((t) => t.id === "db")!;
  const titles = { api: "the API", docs: "the docs" };
  const moves = offerWords(db, titles);
  assert.deepEqual(moves.map((m) => m.label), [
    "Widen its scope app.py", "A new task for app.py; this one waits on it", "Wait on the API", "Reopen the docs", "Try it again",
  ]);
  assert.deepEqual(moves[0]!.argv, ["node", "widen", "db", "app.py"]);
  assert.deepEqual(moves[4]!.argv, tryAgain("db"));
  assert.ok(moves[4]!.long && moves.slice(0, 4).every((m) => !m.long)); // the run in a terminal, the rest at once
  assert.equal(offerOn("n", ["node", "set", "db", "--needs", "api", "--needs", "docs"], { ...db, needs: ["docs"] }, titles), "the API");
});

test("a running task the gate stopped offers the widen alone, to the path it stopped", () => {
  const cli = mixed.tasks.find((t) => t.id === "cli")!;
  const moves = offerWords(cli);
  assert.equal(moves.length, 1);
  assert.equal(moves[0]!.label, "Widen its scope to setup.py");
  assert.deepEqual(moves[0]!.argv, ["node", "widen", "cli"]);
});

test("a task that came back with no offers still has trying it again", () => {
  const bare = parseState(JSON.stringify({ schema: 1, tasks: [{ id: "t", title: "t", state: "came back" }] })).tasks[0]!;
  assert.deepEqual(offerWords(bare).map((m) => m.label), ["Try it again"]);
});

test("auto waiting on a key offers Set Key however the refusal is worded: the CLI's line, or Token Factory's 401", () => {
  // what `graphene auto` writes when the host refuses the key (dev/process/editor/before/stranger.md, 0.8.0)
  const refused = "the planner could not start: Token Factory answered 401 to GET /models?verbose=true: "
    + '{"detail": "Couldn\'t authenticate. Reason: token is not present"}';
  assert.deepEqual(keyTrouble(refused), { key: true, endpoint: null });
  assert.deepEqual(keyTrouble("the planner could not start: NEBIUS_API_KEY is not set; `graphene key set --endpoint nim` keeps one"), { key: true, endpoint: "nim" });
  assert.deepEqual(keyTrouble("no key: `graphene key set` sets one"), { key: true, endpoint: null });
  assert.deepEqual(keyTrouble("the budget is spent: $2.0000 of $2.00"), { key: false, endpoint: null });
  assert.deepEqual(keyTrouble("the goal's check failed after 2 fix rounds"), { key: false, endpoint: null });
  const s = parseState(JSON.stringify({ schema: 1, auto: { round: 1, rounds: 2, stage: "waits", why: refused } }));
  const [auto] = needs(s);
  assert.ok(auto?.kind === "auto" && auto.key, "Needs You's row offers Set Key");
});

test("an answer given with the command is the option by its words, the default, or the person's own words", () => {
  const q = { id: "port", text: "which port?", default: "8000", options: ["pick a free one", "8080"], about: null, kind: "question" };
  assert.deepEqual(answerWith(q, "8080"), ["board", "pick", "port", "2"]);
  assert.deepEqual(answerWith(q, "8000"), ["board", "take", "port"]);
  assert.deepEqual(answerWith(q, "9000, the proxy has 8080"), ["board", "answer", "port", "--", "9000, the proxy has 8080"]);
});

test("a task that came back can be dropped; a running one cannot", () => {
  assert.ok(DROPPABLE.includes("came back") && DROPPABLE.includes("proposed") && !DROPPABLE.includes("running"));
});
