// The harness's own pieces that need no app: `node --test unit.test.mjs` (part of `npm test`).
import assert from "node:assert/strict";
import { test } from "node:test";
import * as L from "./lib.mjs";
import { line, summary } from "./measure/stats.mjs";

test("shell keeps a quoted argument whole, as the driver's `sh` line needs", () => {
  const out = L.shell(process.execPath, `-e "console.log(JSON.stringify(process.argv.slice(1)))" node set top --title "a new title" --note 'two words'`, { encoding: "utf8" });
  assert.deepEqual(JSON.parse(out), ["node", "set", "top", "--title", "a new title", "--note", "two words"]);
});

test("Cursor's project dir for a folder: its path with dashes, under ~/.cursor/projects", () => {
  assert.equal(L.cursorProjectDir("/tmp/shots-cursor-sGsk18/wordkit"), `${process.env.HOME}/.cursor/projects/tmp-shots-cursor-sGsk18-wordkit`);
});

test("a sample's summary: nearest-rank percentiles, the mean rounded", () => {
  assert.deepEqual(summary([582, 515, 194, 537, 147]), { n: 5, min: 147, p50: 515, p90: 582, max: 582, mean: 395 });
  assert.deepEqual(summary([3, 1, 2, 4, 5, 6, 7, 8, 9, 10]), { n: 10, min: 1, p50: 5, p90: 9, max: 10, mean: 6 });
  assert.match(line([1, 2, 3]), /^n 3: p50 2 ms, p90 3, max 3, mean 2, min 1 \(load \d+\.\d\)$/);
});

test("an app the harness launches cannot reach the real Token Factory: no shell profile, a fake key, a local URL", () => {
  const dead = L.safeEnv();
  assert.equal(dead.NEBIUS_API_KEY, "fake-key");
  assert.equal(dead.GRAPHENE_KEYCHAIN, "off");
  assert.match(dead.GRAPHENE_TOKENFACTORY_URL, /^http:\/\/127\.0\.0\.1:/);
  assert.ok(dead.ZDOTDIR && dead.ZDOTDIR !== process.env.HOME, "zsh reads no profile in the app's terminals");
  assert.equal(L.safeEnv("http://127.0.0.1:5000/v1").GRAPHENE_TOKENFACTORY_URL, "http://127.0.0.1:5000/v1");
  // launch() puts it in the app's environment after the person's own variables, so it wins over them
  assert.match(L.launch.toString(), /\.\.\.cleanEnv\(\), \.\.\.safeEnv\(standin\)/);
});
