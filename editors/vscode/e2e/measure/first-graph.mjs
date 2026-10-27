// Seconds from installing the .vsix to the first graph drawn in the side bar, in the real app:
//   node measure/first-graph.mjs [--app code|cursor] [--vsix FILE] [--runs N]
// One run: a fresh profile, install, a fixture with three tasks, launch, open Graphene, wait for the graph.
import { execFileSync } from "node:child_process";
import { rmSync } from "node:fs";
import path from "node:path";
import * as L from "../lib.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const app = await L.findApp(arg("--app", "code"));
const vsix = arg("--vsix", null) ? path.resolve(arg("--vsix")) : L.findVsix();
const graphene = L.findGraphene();
const runs = Number(arg("--runs", 3));
const times = [];
for (let i = 0; i < runs; i++) {
  const base = L.scratch("first-graph-");
  const profile = L.makeProfile(base, { graphene });
  const fx = L.makeFixture(path.join(base, "wordkit"), graphene);
  for (const [id, title] of [["top", "the CLI prints the top words"], ["reading", "a reading time in minutes"], ["hyphens", "hyphenated words stay whole"]]) {
    execFileSync(graphene, ["node", "add", title, "--id", id, "--scope", `wordkit/${id}.py`, "--check", "true"], { cwd: fx.dir, env: fx.env, stdio: "pipe" });
  }
  const t0 = Date.now();
  L.installVsix(app, profile, vsix);
  const t1 = Date.now();
  const s = await L.launch(app, profile, fx.dir);
  const t2 = Date.now();
  await L.openSidebar(s.page);
  const g = await L.waitForGraph(s.page, { min: 3, timeout: 60000 });
  const t3 = Date.now();
  times.push({ install_s: (t1 - t0) / 1000, launch_s: (t2 - t1) / 1000, graph_s: (t3 - t2) / 1000, total_s: (t3 - t0) / 1000, tasks: g.tasks });
  console.log(`run ${i + 1}: ${JSON.stringify(times.at(-1))}`);
  await L.close(s);
  rmSync(base, { recursive: true, force: true });
}
const med = (k) => times.map((t) => t[k]).sort((a, b) => a - b)[Math.floor(times.length / 2)];
console.log(`${app.name}: install to first graph, median of ${runs}: ${med("total_s").toFixed(2)} s (install ${med("install_s").toFixed(2)}, launch to workbench ${med("launch_s").toFixed(2)}, open to graph ${med("graph_s").toFixed(2)})`);
