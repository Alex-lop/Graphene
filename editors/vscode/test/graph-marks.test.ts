import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { attemptsMark, checkMark, cornerMark, doneWhen, filesLine, goalCells, legend, markWord, midCut, nextWanting, stateMark, tally, wanting, wantingLine, type CheckMark, type Mark } from "../src/graph/marks.ts";
import { checkWords, cut, fan, type TaskX } from "../src/graph/words.ts";
import { parseState, parseTask, WORDS, type Word } from "../src/state.ts";

const big = parseState(readFileSync(new URL("./fixtures/big.json", import.meta.url), "utf8"));

/** A step in a state, as the parser fills an older CLI's snapshot, with what the case is about on top. */
const step = (state: Word, more: Partial<TaskX> = {}): TaskX => ({ ...parseTask({ id: more.id ?? state, state }), ...more });

test("every state wears one mark, and the full card's corner leaves out the three its border says", () => {
  const rows: [Word, Mark, Mark | "", string][] = [
    ["waiting", "waiting", "", "waiting"], ["ready", "ready", "", "ready"], ["running", "working", "working", "working"],
    ["review", "you", "you", "to review"], ["yours", "yours", "yours", "yours"], ["came back", "back", "back", "came back"],
    ["done", "landed", "landed", "landed"], ["proposed", "suggested", "", "suggested"],
  ];
  assert.deepEqual(rows.map((r) => r[0]).sort(), [...WORDS].sort(), "a state the snapshot can say has no row");
  for (const [state, mark, corner, word] of rows) {
    assert.equal(stateMark(step(state)), mark, state);
    assert.equal(cornerMark(step(state)), corner, `${state}'s corner`);
    assert.equal(markWord(mark, step(state)), word, `${state}'s word`);
  }
});

test("the first match decides: landed, came back and suggested before what needs you; a step past the line asks you", () => {
  const cases: [string, TaskX, Mark, string][] = [
    ["a write the gate stopped on a working step: only the person can widen it", step("running", { needs_you: true }), "you", "asks you"],
    ["a step past the line is the person's move", step("yours", { leaves: true, command: "git push" }), "you", "asks you"],
    ["the snapshot says needs_you of every yours step: it stays the hollow diamond", step("yours", { needs_you: true }), "yours", "yours"],
    ["to review, as the snapshot sends it", step("review", { needs_you: true }), "you", "to review"],
    ["came back, as the snapshot sends it", step("came back", { needs_you: true }), "back", "came back"],
    ["suggested, as the snapshot sends it", step("proposed", { needs_you: true }), "suggested", "suggested"],
    ["landed stays landed", step("done", { needs_you: true }), "landed", "landed"],
    ["a step past the line that has not come up yet waits", step("waiting", { leaves: true, command: "git push" }), "waiting", "waiting"],
    ["and once it ran it landed", step("done", { leaves: true, command: "git push" }), "landed", "landed"],
  ];
  for (const [why, t, mark, word] of cases) {
    assert.equal(stateMark(t), mark, why);
    assert.equal(markWord(mark, t), word, why);
  }
  assert.equal(markWord("you"), "to review", "the legend's word for the filled diamond");
});

const plan: TaskX[] = [
  step("done", { id: "schema", parent: "store" }), step("review", { id: "cache", parent: "store", needs_you: true }),
  step("running", { id: "audit", parent: "store" }), step("waiting", { id: "purge", parent: "store" }),
  step("done", { id: "models", parent: "api" }), step("came back", { id: "cancel", parent: "api", needs_you: true }),
  step("ready", { id: "auth", parent: "api" }), step("yours", { id: "a11y", parent: "ui", needs_you: true }),
  step("proposed", { id: "changelog", parent: null, needs_you: true }), step("yours", { id: "pr", parent: null, leaves: true, command: "gh pr create", needs_you: true }),
];
const calm: TaskX[] = [step("done", { id: "a" }), step("running", { id: "b" }), step("ready", { id: "c" }), step("waiting", { id: "d" }), step("proposed", { id: "e" })];

test("a tally reads as a bar: landed first, then loudest first, and says in words what wants the person", () => {
  assert.deepEqual(tally(plan), {
    landed: 2, total: 10, portion: 0.2,
    marks: ["landed", "landed", "you", "you", "back", "yours", "working", "ready", "waiting", "suggested"],
    wants: [{ mark: "you", text: "1 to review" }, { mark: "back", text: "1 came back" }, { mark: "yours", text: "1 yours" }, { mark: "you", text: "1 asks you" }],
  });
  const store = tally(plan.filter((t) => t.parent === "store"));
  assert.deepEqual([store.landed, store.total, store.portion, store.wants.map((w) => w.text)], [1, 4, 0.25, ["1 to review"]]);
  assert.deepEqual(tally([]), { landed: 0, total: 0, portion: 0, marks: [], wants: [] }, "an empty plan: nothing, and no division by none");
  assert.deepEqual(tally(calm).wants, [], "nothing needs the person: no words");
  assert.equal(tally([step("done"), step("done", { id: "b" })]).portion, 1);
  const many = tally([step("review"), step("review", { id: "r2" }), step("running", { id: "w1", needs_you: true }), step("running", { id: "w2", needs_you: true })]);
  assert.deepEqual(many.wants.map((w) => w.text), ["2 to review", "2 ask you"]);
});

test("the steps that want the person, in plan order, and the next one round again", () => {
  const ids = wanting(plan);
  assert.deepEqual(ids, ["cache", "cancel", "a11y", "pr"]);
  assert.equal(nextWanting(ids, null), "cache", "none selected: the first");
  assert.equal(nextWanting(ids, "cache"), "cancel");
  assert.equal(nextWanting(ids, "pr"), "cache", "after the last: round again");
  assert.equal(nextWanting(ids, "schema"), "cache", "a step that wants nothing is selected: the first");
  assert.equal(nextWanting(["cache"], "cache"), "cache", "the only one: itself, brought on screen");
  assert.deepEqual([wanting([]), nextWanting([], null), nextWanting([], "cache")], [[], null, null]);
  assert.deepEqual(wanting(calm), []);
  assert.deepEqual([wantingLine(3), wantingLine(1), wantingLine(0)], ["3 need you · show the next", "1 needs you · show it", ""]);
  assert.equal(wantingLine(wanting(plan).length), "4 need you · show the next");
});

test("the legend lists the marks the plan has, loudest first, each with its word and its count", () => {
  assert.deepEqual(legend(plan), [["you", "to review / asks you", 2], ["back", "came back", 1], ["yours", "yours", 1], ["working", "working", 1],
                                  ["landed", "landed", 2], ["ready", "ready", 1], ["waiting", "waiting", 1], ["suggested", "suggested", 1]]);
  assert.deepEqual(legend(calm), [["working", "working", 1], ["landed", "landed", 1], ["ready", "ready", 1], ["waiting", "waiting", 1], ["suggested", "suggested", 1]]);
  assert.deepEqual(legend([]), [], "an empty plan has no legend");
  assert.deepEqual(legend([step("yours", { leaves: true })]), [["you", "asks you", 1]], "a diamond that is no review says what it is");
  assert.deepEqual(legend([], 2), [["suggested", "a draft", 2]], "drafts on an empty canvas: the dashed ring, by its own word");
  assert.deepEqual(legend(calm, 2).at(-1), ["suggested", "suggested / a draft", 3]);
});

test("the goal's row groups the marks by sub-goal, in the order the plan first names each", () => {
  const goals = [{ id: "api", title: "the API serves them" }, { id: "store", title: "the store keeps orders" }];
  assert.deepEqual(goalCells(plan, goals), [
    { id: "store", title: "the store keeps orders", marks: ["landed", "you", "working", "waiting"] },
    { id: "api", title: "the API serves them", marks: ["landed", "back", "ready"] },
    { id: "ui", title: "ui", marks: ["yours"] }, // a sub-goal the snapshot does not name: its id
    { id: "", title: "", marks: ["you", "suggested"] }, // under no sub-goal: where the plan first has one, here last
  ]);
  const loose = [step("ready", { id: "x" }), ...plan.slice(0, 2)];
  assert.deepEqual(goalCells(loose, goals).map((g) => g.id), ["", "store"], "and first when the plan starts with one");
  assert.deepEqual(goalCells([], goals), []);
  assert.equal(goalCells(plan, goals).flatMap((g) => g.marks).length, plan.length, "a cell a task");
});

// ---- the check ----
const CHECK = "uv run pytest -q tests/store/test_cache.py";
const RED = "failed before the work, so it can tell", PASSES = "passed before the work: it proves nothing yet";
const PASSED = "passed after the work, in a clean copy", UNRUN = "not run on the code as it is yet: it runs once before the work starts";
const checked = (before: string | null, after: string | null) => ({ before, after });

test("the check's box says what the snapshot said of the check, in the pane's words, and no more", () => {
  const rows: [string, TaskX, CheckMark][] = [
    ["no check: the person's approval, in any state", step("ready"), { box: "approval", tone: "you", words: "no check: your approval finishes it" }],
    ["no check, landed", step("done"), { box: "approval", tone: "you", words: "no check: your approval finishes it" }],
    ["not run yet", step("waiting", { check: CHECK }), { box: "unrun", tone: "dim", words: UNRUN }],
    ["it fails now, as it should: good news, never red", step("ready", { check: CHECK, checked: checked("red", null) }), { box: "tells", tone: "plain", words: RED }],
    ["the same while an agent works", step("running", { check: CHECK, checked: checked("red", null) }), { box: "tells", tone: "plain", words: RED }],
    ["it already passes: it proves nothing yet", step("ready", { check: CHECK, hollow: true, checked: checked("passes", null) }), { box: "hollow", tone: "warn", words: PASSES }],
    ["the cockpit's hollow alone says the same", step("waiting", { check: CHECK, hollow: true }), { box: "hollow", tone: "warn", words: PASSES }],
    ["the verdict alone says the same", step("ready", { check: CHECK, checked: checked("passes", null) }), { box: "hollow", tone: "warn", words: PASSES }],
    ["it fails on a path outside its files", step("ready", { check: CHECK, checked: checked("outside", null) }),
     { box: "hollow", tone: "warn", words: "failed before the work on a path outside its files" }],
    ["it could not be run here", step("running", { check: CHECK, checked: checked("environment", null) }), { box: "hollow", tone: "warn", words: "could not be run here before the work" }],
    ["landed once and reopened", step("ready", { check: CHECK, checked: checked("landed", null) }),
     { box: "unrun", tone: "dim", words: "passed when it landed; reopened, it passes until the check is changed" }],
    ["failed before the work, passes now", step("done", { check: CHECK, checked: checked("red", "passed") }), { box: "passed", tone: "ok", words: `${RED} · ${PASSED}` }],
    ["to review, the same", step("review", { check: CHECK, checked: checked("red", "passed") }), { box: "passed", tone: "ok", words: `${RED} · ${PASSED}` }],
    ["it passes, as it did before: a tick that warns", step("done", { check: CHECK, hollow: true, checked: checked("passes", "passed") }),
     { box: "passed", tone: "warn", words: `${PASSES} · ${PASSED}` }],
    ["passed, and nobody said what it did before", step("done", { check: CHECK, checked: checked(null, "passed") }), { box: "passed", tone: "ok", words: PASSED }],
    ["failed after the work", step("came back", { check: CHECK, checked: checked("red", "failed") }), { box: "failed", tone: "red", words: `${RED} · failed after the work` }],
    ["a cross outranks a hollow check", step("came back", { check: CHECK, hollow: true, checked: checked("passes", "failed") }),
     { box: "failed", tone: "red", words: `${PASSES} · failed after the work` }],
    ["landed with no verdict after the work: no tick", step("done", { check: CHECK, checked: checked("red", null) }), { box: "tells", tone: "plain", words: RED }],
    ["landed, hollow, no verdict after: the work is finished, so no hollow box", step("done", { check: CHECK, hollow: true, checked: checked("passes", null) }),
     { box: "unrun", tone: "dim", words: PASSES }],
    // an older CLI: `checked` with both fields null on every task
    ["an older CLI, landed: no verdict, no words", step("done", { check: CHECK }), { box: "unrun", tone: "dim", words: "" }],
    ["an older CLI, to review: the same", step("review", { check: CHECK }), { box: "unrun", tone: "dim", words: "" }],
    ["an older CLI, working: when it runs, not that it has not", step("running", { check: CHECK }), { box: "unrun", tone: "dim", words: "runs in a clean copy when the agent says done" }],
    ["an older CLI, came back", step("came back", { check: CHECK }), { box: "unrun", tone: "dim", words: "runs in a clean copy after the work" }],
    // a command step: its command is its check
    ["a command step before it ran", step("ready", { check: "uv run pytest -q", command: "uv run pytest -q" }),
     { box: "unrun", tone: "dim", words: "it runs once what it waits on has landed" }],
    ["one past the line", step("yours", { check: "gh pr create", command: "gh pr create", leaves: true }), { box: "unrun", tone: "dim", words: "it runs when you approve it" }],
    ["after it ran", step("done", { check: "uv run pytest -q", command: "uv run pytest -q", checked: checked(null, "passed") }), { box: "passed", tone: "ok", words: "it ran, and exited 0" }],
    ["after it failed: a run tries it again", step("ready", { check: "uv run pytest -q", command: "uv run pytest -q", checked: checked(null, "failed") }),
     { box: "failed", tone: "red", words: "it ran, and failed" }],
    ["an older CLI's command step, done: no verdict, no words", step("done", { check: "uv run pytest -q", command: "uv run pytest -q" }), { box: "unrun", tone: "dim", words: "" }],
  ];
  for (const [why, t, want] of rows) assert.deepEqual(checkMark(t), want, why);
});

test("whatever the snapshot says, the box agrees with the pane: its words are the pane's lines, a tick or a cross only for a verdict after the work", () => {
  for (const state of WORDS) for (const before of [null, "red", "passes", "outside", "environment", "landed", "a verdict of tomorrow"]) {
    for (const after of [null, "passed", "failed", "something else"]) for (const hollow of [false, true]) {
      const t = step(state, { check: CHECK, hollow, checked: checked(before, after) });
      const m = checkMark(t), at = `${state} · before ${before} · after ${after}${hollow ? " · hollow" : ""}`;
      const pane = [...checkWords(t), ...(hollow ? checkWords({ ...t, checked: checked("passes", after) }) : [])]; // `hollow` is the cockpit's `passes`
      for (const part of m.words ? m.words.split(" · ") : []) assert.ok(pane.some((x) => x.line === part), `${at}: “${part}” is not a line of the pane's`);
      assert.equal(m.box === "passed", after === "passed", `${at}: a tick`);
      assert.equal(m.box === "failed", after === "failed", `${at}: a cross`);
      if (m.box === "hollow") assert.ok(pane.some((x) => x.tone === "warn") && state !== "done" && state !== "review", `${at}: hollow`);
      if (m.box === "tells") assert.equal(checkWords(t)[0]!.tone, "red", `${at}: tells`);
      if (state === "done" || state === "review") assert.doesNotMatch(m.words, /not run|runs in a clean copy/, `${at}: a finished step is told nothing that has yet to happen`);
      if (m.tone === "red") assert.equal(after, "failed", `${at}: red is for a check that failed after the work`);
    }
  }
});

test("a check is cut in its middle, so both ends stay; short ones are left alone; never longer than asked", () => {
  assert.equal(midCut(CHECK, 20), "uv run…test_cache.py");
  assert.equal(midCut("npm test", 20), "npm test");
  assert.equal(midCut("x".repeat(20), 20), "x".repeat(20), "exactly as long as asked: untouched");
  assert.equal(midCut("uv run pytest -q tests", 12), "uv…-q tests", "no space is left hanging at the cut");
  assert.deepEqual([midCut(CHECK, 2), midCut(CHECK, 1), midCut(CHECK, 0), midCut(CHECK, -3), midCut(CHECK, Number.NaN)], ["…y", "…", "", "", ""]);
  for (const s of [CHECK, "a  b  c  d  e  f  g  h", "docker build -q .", "…………………………"]) for (let n = 0; n <= s.length + 2; n++) {
    const out = midCut(s, n);
    assert.ok(out.length <= Math.max(0, n), `“${out}” is longer than ${n}`);
    if (n >= s.length) assert.equal(out, s);
    else if (n >= 5) assert.ok(out.includes("…") && s.startsWith(out.split("…")[0]!) && s.endsWith(out.slice(out.indexOf("…") + 1)), `${n}: “${out}” keeps both ends`);
  }
  // what it is for: the preview's 24 checks read apart at a card's width, where a cut at the end left 16 of them the same
  const checks = big.tasks.map((t) => t.check).filter((c): c is string => c !== null);
  assert.equal(new Set(checks.map((c) => midCut(c, 20))).size, new Set(checks).size);
  assert.equal(new Set(checks.map((c) => cut(c, 20))).size, 9);
});

test("after `done when`, the foot says the check cut in its middle, or that a command step exits 0", () => {
  assert.equal(doneWhen(step("ready", { check: CHECK }), 20), "uv run…test_cache.py");
  assert.equal(doneWhen(step("ready", { check: "gh pr create --draft --fill", command: "gh pr create --draft --fill" }), 20), "it exits 0");
  assert.equal(doneWhen(step("yours"), 20), "", "no check: the box's words say whose approval finishes it");
});

// ---- the files chip, the attempts ----
const FOUR = ["api/create/__init__.py", "api/create/handler.py", "api/create/totals.py", "api/create/validate.py"];
const stop = (path: string) => ({ path, at: "2026-11-21T14:02:11", how: "edit" });

test("the files chip says the latest fact: what it may change, what it has written, what was refused, what it wrote outside", () => {
  const working = step("running", { scope: ["api/create/**"], files: FOUR, filesN: 4, touched: FOUR.slice(1, 3) });
  const rows: [string, TaskX, ReturnType<typeof filesLine>][] = [
    ["not started: the files it may change", step("ready", { scope: ["store/cache.py", "tests/store/**"] }), { tone: "plain", mark: "▤", text: "store/cache.py +1", refused: "" }],
    ["no files named: no chip", step("waiting"), { tone: "plain", mark: "", text: "", refused: "" }],
    ["working: how many of its files it has written", working, { tone: "working", mark: "✎", text: "2 of 4 files", refused: "" }],
    ["and how many writes were refused, apart", { ...working, stops: [stop("store/repo.py")] }, { tone: "working", mark: "✎", text: "2 of 4 files", refused: "1 refused" }],
    ["a file it created counts, and one file is a file", step("running", { scope: ["store/audit.py"], touched: ["store/audit.py"], stops: [stop("a"), stop("b")] }),
     { tone: "working", mark: "✎", text: "1 of 1 file", refused: "2 refused" }],
    ["working, nothing written yet", { ...working, touched: [] }, { tone: "working", mark: "✎", text: "0 of 4 files", refused: "" }],
    ["working under an older CLI, which counts no files: the scope, as today", step("running", { scope: ["api/list.py"] }), { tone: "plain", mark: "▤", text: "api/list.py", refused: "" }],
    ["working where no file is there yet: the scope, and still the refused write", step("running", { scope: ["src/new/**"], stops: [stop("README.md")] }),
     { tone: "plain", mark: "▤", text: "src/new/**", refused: "1 refused" }],
    ["the count is for a step at work: to review, the scope again", { ...working, state: "review", changed: FOUR.slice(1, 3), touched: [], stops: [stop("x")] },
     { tone: "plain", mark: "▤", text: "api/create/**", refused: "" }],
    ["came back for a write outside its files: which", step("came back", { scope: ["api/cancel.py"], outside: ["store/repo.py"] }), { tone: "back", mark: "✕", text: "wrote store/repo.py", refused: "" }],
    ["and how many more", step("came back", { scope: ["api/cancel.py"], outside: ["store/repo.py", "store/index.py", "README.md"] }),
     { tone: "back", mark: "✕", text: "wrote store/repo.py +2", refused: "" }],
    ["came back for another reason: the scope", step("came back", { scope: ["api/cancel.py"] }), { tone: "plain", mark: "▤", text: "api/cancel.py", refused: "" }],
    ["`outside` on a step that did not come back says nothing here", step("running", { scope: ["api/cancel.py"], outside: ["store/repo.py"] }),
     { tone: "plain", mark: "▤", text: "api/cancel.py", refused: "" }],
    ["a command step keeps its own chip", step("ready", { check: "uv run pytest -q", command: "uv run pytest -q" }), { tone: "plain", mark: "", text: "", refused: "" }],
  ];
  for (const [why, t, want] of rows) assert.deepEqual(filesLine(t), want, why);
});

test("×3 on a step set to attempts that has started none: exactly where the fan hung its waiting chips", () => {
  const ready = step("ready", { check: CHECK });
  const real = [{ letter: "a", state: "passed", why: "", lines: 41, model: "Nano", usd: 0.007, attempts: 1, idle: null, checkout: null },
                { letter: "b", state: "running", why: "", lines: 9, model: "Nano", usd: 0.002, attempts: 1, idle: 3, checkout: null }];
  const rows: [string, TaskX, number | null, string][] = [
    ["its own number", { ...ready, planned: 3 }, null, "×3"],
    ["unset on the step: the limits' number", ready, 2, "×2"],
    ["the step's number comes first, and one attempt is no news", { ...ready, planned: 1 }, 3, ""],
    ["nothing set anywhere", ready, null, ""],
    ["suggested and waiting steps too", step("proposed", { check: CHECK }), 3, "×3"],
    ["waiting", step("waiting", { check: CHECK, planned: 8 }), null, "×8"],
    ["no check: it runs as one agent", step("ready", { planned: 3 }), null, ""],
    ["a command step runs once", step("ready", { check: "uv run pytest -q", command: "uv run pytest -q" }), 3, ""],
    ["started: its real attempts are its chips", step("running", { check: CHECK, planned: 3, forks: real }), 3, ""],
    ["working as one agent", step("running", { check: CHECK, planned: 3 }), null, ""],
    ["landed", step("done", { check: CHECK, planned: 3 }), 3, ""],
  ];
  for (const [why, t, limit, want] of rows) {
    assert.equal(attemptsMark(t, limit), want, why);
    assert.equal(want !== "", !t.forks.length && fan(t, limit).length > 0, `${why}: where the fan has placeholders, and only there`);
  }
});
