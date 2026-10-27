// Latency from a store write to the screen: `graphene node set ID --title T`, then the side bar's graph
// shows T. The clock starts when the command returns (the store holds the write), and stops when a graph
// frame draws the new title. The write lands at a random phase of the extension's poll, so one run says
// little: 20 runs, and the spread (p50, p90, max, mean) with the machine's load beside it.
//   node measure/latency.mjs [--app code|cursor] [--vsix FILE] [--runs N]
import { execFileSync } from "node:child_process";
import { rmSync } from "node:fs";
import path from "node:path";
import * as L from "../lib.mjs";
import { line } from "./stats.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const app = await L.findApp(arg("--app", "code"));
const vsix = arg("--vsix", null) ? path.resolve(arg("--vsix")) : L.findVsix();
const graphene = L.findGraphene();
const runs = Number(arg("--runs", 20));
const base = L.scratch("latency-");
const profile = L.makeProfile(base, { graphene });
L.installVsix(app, profile, vsix);
const fx = L.makeFixture(path.join(base, "wordkit"), graphene);
execFileSync(graphene, ["node", "add", "a task to rename", "--id", "t1", "--scope", "wordkit/t1.py", "--check", "true"], { cwd: fx.dir, env: fx.env, stdio: "pipe" });
const s = await L.launch(app, profile, fx.dir);
await L.openSidebar(s.page);
await L.waitForGraph(s.page, { min: 1 });
await s.page.waitForTimeout(3000); // let the first reads settle
const ms = [];
for (let i = 0; i < runs; i++) {
  const title = `renamed ${i + 1} at ${Date.now()}`;
  execFileSync(graphene, ["node", "set", "t1", "--title", title], { cwd: fx.dir, env: fx.env, stdio: "pipe" });
  const t0 = Date.now();
  const short = title.slice(0, 12); // the box cuts long titles
  for (;;) {
    let seen = false;
    for (const f of await L.graphFrames(s.page)) {
      // the graph's boxes, or the side bar's lanes when the canvas is narrow: either drawing shows the title
      const titles = await f.evaluate(() => [...document.querySelectorAll("#view g.task text.title, #lanes:not([hidden]) .lane[data-id] .l-title")].map((t) => t.textContent)).catch(() => []);
      if (titles.some((t) => t.startsWith(short))) seen = true;
    }
    if (seen) break;
    if (Date.now() - t0 > 30000) throw new Error("the new title never showed");
    await s.page.waitForTimeout(20);
  }
  ms.push(Date.now() - t0);
  console.log(`run ${i + 1}: ${ms.at(-1)} ms`);
  await s.page.waitForTimeout(2000);
}
console.log(`${app.name}: store write to screen, ${line(ms)}`);
await L.close(s);
rmSync(base, { recursive: true, force: true });
