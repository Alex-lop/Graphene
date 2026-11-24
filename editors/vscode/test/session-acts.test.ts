// What a page of sessions may ask its host (src/sessions/acts.ts), and which sessions get a page (src/open.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { column, pages, wrote } from "../src/open.ts";
import { checkPage } from "../src/sessions/acts.ts";
import { parseState } from "../src/state.ts";

const s = parseState(readFileSync(new URL("./fixtures/sessions.json", import.meta.url), "utf8"));
const card = s.tasks.find((t) => t.changed.length)!, session = s.sessions![0]!;

test("a page's message is an act it knows, about a card or a session it draws, and a file that card names", () => {
  assert.deepEqual(checkPage({ type: "ready" }, s), { type: "ready" });
  assert.deepEqual(checkPage({ type: "act", act: "terminal", id: card.id }, s), { type: "act", act: "terminal", id: card.id });
  assert.deepEqual(checkPage({ type: "act", act: "resume", id: session.id }, s), { type: "act", act: "resume", id: session.id });
  assert.deepEqual(checkPage({ type: "act", act: "takeOff", id: session.id }, s), { type: "act", act: "takeOff", id: session.id });
  assert.deepEqual(checkPage({ type: "act", act: "addSession", id: "anything" }, s), { type: "act", act: "addSession", id: "" });
  assert.deepEqual(checkPage({ type: "act", act: "replay" }, null), { type: "act", act: "replay", id: "" });
  assert.deepEqual(checkPage({ type: "act", act: "openFile", id: card.id, file: card.changed[0] }, s), { type: "act", act: "openFile", id: card.id, file: card.changed[0] });
  for (const bad of [null, "terminal", {}, { type: "act" }, { type: "act", act: "start", id: "" }, { type: "act", act: "run", id: card.id },
                     { type: "act", act: "terminal", id: "no such card" }, { type: "act", act: "resume", id: card.id }, { type: "act", act: "takeOff", id: "" },
                     { type: "act", act: "openFile", id: card.id }, { type: "act", act: "openFile", id: card.id, file: "/etc/passwd" },
                     { type: "act", act: "openFile", id: card.id, file: "../outside.py" }]) {
    assert.equal(checkPage(bad, s), null, JSON.stringify(bad));
  }
  assert.equal(checkPage({ type: "act", act: "terminal", id: card.id }, null), null); // nothing drawn yet: nothing to act on
});

test("a session gets a page when it begins or writes while the window is open, once, and never for what was there before", () => {
  const a = { file: "/s/a.jsonl", size: 100 }, b = { file: "/s/b.jsonl", size: 40 };
  assert.deepEqual(wrote(null, [a, b]), []); // the first look: every session there is old
  const before = new Map([[a.file, 100]]);
  assert.deepEqual(wrote(before, [a]), []); // nothing written
  assert.deepEqual(wrote(before, [{ ...a, size: 180 }, b]), [a.file, b.file]); // one wrote, one began
  assert.deepEqual(wrote(before, [{ ...a, size: 60 }]), []); // a file that shrank wrote nothing
  assert.equal(pages({ on: true, paged: false, opened: false }), true);
  assert.equal(pages({ on: false, paged: false, opened: false }), false); // graphene.graph.openOnStart is off
  assert.equal(pages({ on: true, paged: true, opened: false }), false); // a page draws it already
  assert.equal(pages({ on: true, paged: false, opened: true }), false); // opened once, and closed: not chased
});

test("a page that opens by itself never covers the file in front: beside it, or with the other pages where they are not in its group", () => {
  const file = { uri: "notes.md" };
  assert.equal(column({ front: file, active: 1, pages: [] }), "beside");
  assert.equal(column({ front: file, active: 1, pages: [2] }), 2); // the pages' own group: they gather there
  assert.equal(column({ front: file, active: 1, pages: [1] }), "beside"); // a page shares the file's group: not there, over the file
  assert.equal(column({ front: file, active: 1, pages: [1, 3] }), 3);
  assert.equal(column({ front: undefined, active: 1, pages: [] }), "active"); // nothing in front: nothing to cover
  assert.equal(column({ front: undefined, active: 1, pages: [1] }), 1);
  assert.equal(column({ front: undefined, active: 2, pages: [undefined, 1] }), 1);
  // one of the pages is what is in front: the next joins it there, and no third group is made beside the pages' own
  assert.equal(column({ front: { viewType: "page" }, own: true, active: 2, pages: [2, 2] }), 2);
  assert.equal(column({ front: { viewType: "page" }, own: true, active: undefined, pages: [] }), "active");
});
