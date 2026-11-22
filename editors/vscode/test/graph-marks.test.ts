import assert from "node:assert/strict";
import { test } from "node:test";
import { cornerMark, goalCells, legend, markWord, nextWanting, stateMark, tally, wanting, wantingLine, type Mark } from "../src/graph/marks.ts";
import type { TaskX } from "../src/graph/words.ts";
import { parseTask, WORDS, type Word } from "../src/state.ts";

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
