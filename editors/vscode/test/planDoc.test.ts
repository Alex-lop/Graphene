import assert from "node:assert/strict";
import { test } from "node:test";
import * as C from "../src/commands.ts";

test("a refusal's faults land on their lines, over the line's own words", () => {
  const lines = ["goal: invoices as PDF", "", "- the renderer  [pdf]", "    scope app.py", "  ? the template"];
  const r = C.parseApplied(JSON.stringify({ applied: false, said: [], faults: [{ line: 4, text: "line 4: scope needs a colon" }, { line: 99, text: "pdf: already running" }, { line: 0, text: "x" }] }));
  assert.equal(r.applied, false);
  assert.deepEqual(C.faultRanges(r.faults, lines), [
    { line: 3, start: 4, end: 16, text: "line 4: scope needs a colon" },
    { line: 4, start: 2, end: 16, text: "pdf: already running" },
    { line: 0, start: 0, end: 21, text: "x" },
  ]);
});

test("an applied save has no faults; what is not JSON is one fault on line 1 with the refusal", () => {
  assert.deepEqual(C.parseApplied('{"applied": true, "said": ["+ render [render]"], "faults": []}'),
                   { applied: true, said: ["+ render [render]"], faults: [] });
  assert.deepEqual(C.parseApplied("", "only the person edits the plan\n"),
                   { applied: false, said: [], faults: [{ line: 1, text: "only the person edits the plan" }] });
});

test("an empty text has one line for a fault to sit on", () => {
  assert.deepEqual(C.faultRanges([{ line: 3, text: "t" }], []), [{ line: 0, start: 0, end: 0, text: "t" }]);
});
