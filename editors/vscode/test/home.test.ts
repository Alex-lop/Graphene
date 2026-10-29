import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { banner, countsLine } from "../src/home/cards.ts";
import { headline, parseState, type State } from "../src/state.ts";

const fixture = (name: string): State => parseState(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));

test("the header: the goal, else what was last asked; the counts in plain words; a practice run says so", () => {
  const s = fixture("running");
  assert.equal(headline(s), "make the app friendlier");
  assert.equal(headline({ ...s, goal: "", news: ["you asked: a --json flag", "proposed: x"] }), "a --json flag");
  assert.equal(headline({ ...s, goal: "", news: [] }), "");
  assert.equal(countsLine(s), "2 working · 2 need you · 2 of 7 done · $0.42 spent");
  assert.equal(banner(s), "");
  assert.equal(banner({ ...s, stand_in: true }), "Practice run: a scripted stand-in answers for the AI, so nothing is spent");
  assert.equal(banner({ ...s, replay: { shown: "a scripted stand-in, no model ran", day: "", repository: "" } }), "Demo replay: a scripted stand-in, no model ran");
});
