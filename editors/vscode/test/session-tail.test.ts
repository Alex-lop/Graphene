// A file read as it grows (src/sessions/tail.ts).
import assert from "node:assert/strict";
import { appendFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { Tail } from "../src/sessions/tail.ts";

const scratch = () => mkdtempSync(path.join(os.tmpdir(), "graphene-sessions-"));

test("a file is read for what is new only, a last line with no newline waits, and a file that shrank starts over", async () => {
  const dir = scratch(), file = path.join(dir, "s.jsonl");
  try {
    writeFileSync(file, '{"a":1}\n{"b":2}\n{"c":');
    const t = new Tail(file);
    assert.deepEqual((await t.read()).lines, ['{"a":1}', '{"b":2}']);
    assert.deepEqual((await t.read()).lines, []); // nothing new: nothing read again
    appendFileSync(file, '3}\n{"d":"é');
    assert.deepEqual((await t.read()).lines, ['{"c":3}']); // the held half and its end are one line
    appendFileSync(file, 'é"}\n');
    assert.deepEqual((await t.read()).lines, ['{"d":"éé"}']); // a character is never read as two halves
    writeFileSync(file, '{"z":0}\n');
    assert.deepEqual(await t.read(), { lines: ['{"z":0}'], n: 1, reset: true, error: "" });
    // handed over a line at a time, none is kept: a long session's first read holds a line, not the file
    appendFileSync(file, '{"y":1}\n{"x":2}\n');
    const got: string[] = [];
    assert.deepEqual(await t.read((l) => got.push(l)), { lines: [], n: 2, reset: false, error: "" });
    assert.deepEqual(got, ['{"y":1}', '{"x":2}']);
    const gone = await new Tail(path.join(dir, "none.jsonl")).read();
    assert.deepEqual(gone.lines, []);
    assert.match(gone.error, /^cannot read .*none\.jsonl: ENOENT$/); // one line, and no throw
  } finally { rmSync(dir, { recursive: true }); }
});
