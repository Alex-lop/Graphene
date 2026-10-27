import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { backoff, lines, Stream, unsupported, WATCH } from "../src/stream.ts";

test("the stream's line splitting: a chunk may end mid-line or hold several, and blank lines are nothing", () => {
  let got = lines("", '{"a":1}\n{"b"');
  assert.deepEqual(got, { whole: ['{"a":1}'], rest: '{"b"' });
  got = lines(got.rest, ':2}\n\n{"c":3}\n');
  assert.deepEqual(got, { whole: ['{"b":2}', '{"c":3}'], rest: "" });
  assert.deepEqual(lines("", "no newline yet"), { whole: [], rest: "no newline yet" });
});

test("the fallback decision: an older CLI's refusal of --watch means the poll; any other death means a restart", () => {
  assert.ok(unsupported("Usage: graphene state [OPTIONS]\nTry 'graphene state --help' for help.\n\nError: No such option: --watch\n"));
  assert.ok(!unsupported("the store did not open; locked"));
  assert.ok(!unsupported(""));
  assert.deepEqual([1, 2, 3, 4, 5, 6, 9].map(backoff), [1000, 2000, 4000, 8000, 16000, 30000, 30000]);
  assert.deepEqual(WATCH(), ["state", "--json", "--watch"]);
});

// a stand-in for the graphene command: a shell script that hands its argv to node, so the Stream spawns it as it
// spawns graphene (the path, then `state --json --watch`)
function fake(dir: string, name: string, code: string): string {
  const js = path.join(dir, `${name}.cjs`);
  writeFileSync(js, code);
  const sh = path.join(dir, name);
  writeFileSync(sh, `#!/bin/sh\nexec "${process.execPath}" "${js}" "$@"\n`);
  chmodSync(sh, 0o755);
  return sh;
}

test("an older CLI's child ends the stream for the poll; a newer one's lines each reach the session, and it is live", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "graphene-stream-"));
  try {
    const older = fake(dir, "older", `process.stderr.write("Error: No such option: --watch\\n"); process.exit(2);`);
    const seen: string[] = [];
    const s1 = new Stream({ path: older, cwd: dir, onLine: (l) => seen.push(l) });
    s1.start();
    await new Promise((r) => setTimeout(r, 700));
    assert.ok(s1.unsupported, "the CLI refused --watch: the poll takes over");
    assert.ok(!s1.live);
    assert.deepEqual(seen, []);
    s1.dispose();

    const newer = fake(dir, "newer", `
      if (process.argv.slice(2).join(" ") !== "state --json --watch") { process.stderr.write("wrong argv " + process.argv.slice(2).join(" ")); process.exit(3); }
      process.stdout.write('{"schema":1,"cursor":1}\\n{"schema":1,"cur');
      setTimeout(() => { process.stdout.write('sor":2}\\n'); setTimeout(() => process.exit(0), 600); }, 100);
    `);
    const got: string[] = [];
    const s2 = new Stream({ path: newer, cwd: dir, onLine: (l) => got.push(l) });
    s2.start();
    for (let i = 0; i < 40 && got.length < 2; i++) await new Promise((r) => setTimeout(r, 50)); // node starts in its own time
    assert.ok(s2.live, "a line arrived: the stream is live");
    await new Promise((r) => setTimeout(r, 900));
    assert.deepEqual(got, ['{"schema":1,"cursor":1}', '{"schema":1,"cursor":2}']);
    assert.ok(!s2.live, "the child ended: not live until the next line");
    assert.ok(!s2.unsupported, "it died for another reason: it is started again, with a backoff");
    s2.dispose();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
