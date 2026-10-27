// Idle CPU of the extension host and the graphene processes it spawns, over 60 s with the views open and
// nothing happening: CPU time taken by each process in the app's tree over the window, as a percent of it.
//   node measure/idle-cpu.mjs [--app code|cursor] [--vsix FILE] [--seconds 60]
// The graphene processes come and go (one `graphene state --json` a poll), so their share is the sum of the
// CPU time of every graphene process seen, sampled each second.
import { execFileSync } from "node:child_process";
import { rmSync } from "node:fs";
import path from "node:path";
import * as L from "../lib.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const app = await L.findApp(arg("--app", "code"));
const vsix = arg("--vsix", null) ? path.resolve(arg("--vsix")) : L.findVsix();
const graphene = L.findGraphene();
const seconds = Number(arg("--seconds", 60));
const base = L.scratch("idle-cpu-");
const profile = L.makeProfile(base, { graphene });
L.installVsix(app, profile, vsix);
const fx = L.makeFixture(path.join(base, "wordkit"), graphene);
for (const [id, title] of [["top", "the CLI prints the top words"], ["reading", "a reading time in minutes"], ["hyphens", "hyphenated words stay whole"]]) {
  execFileSync(graphene, ["node", "add", title, "--id", id, "--scope", `wordkit/${id}.py`, "--check", "true"], { cwd: fx.dir, env: fx.env, stdio: "pipe" });
}
const s = await L.launch(app, profile, fx.dir);
await L.openSidebar(s.page);
await L.waitForGraph(s.page, { min: 3 });
await L.openPanel(s.page);
await s.page.waitForTimeout(5000); // settle
const root = s.electronApp.process().pid;

/** Every process under the app: pid, ppid, CPU time in ms, command. */
function tree() {
  const rows = execFileSync("ps", ["-axo", "pid=,ppid=,time=,command="], { encoding: "utf8" }).trim().split("\n").map((l) => {
    const m = l.trim().match(/^(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/);
    if (!m) return null;
    const [, pid, ppid, time, command] = m;
    const parts = time.split(/[-:]/).map(Number); // [[dd-]hh:]mm:ss.cc
    let ms = 0;
    for (const p of parts) ms = ms * 60 + p * 1000; // days overshoot, never seen here
    return { pid: Number(pid), ppid: Number(ppid), ms: Math.round(ms), command };
  }).filter(Boolean);
  const under = new Set([root]);
  let grew = true;
  while (grew) { grew = false; for (const r of rows) if (under.has(r.ppid) && !under.has(r.pid)) { under.add(r.pid); grew = true; } }
  return rows.filter((r) => under.has(r.pid));
}
const isHost = (c) => /extensionHost|Helper \(Plugin\)|extension-host/.test(c);
const isGraphene = (c) => /graphene/.test(c) && /python|\/graphene( |$)/.test(c) && !/Code|Cursor|Electron/.test(c.split(" ")[0]);

const t0 = Date.now();
const first = tree();
const hostAt0 = first.filter((r) => isHost(r.command)).reduce((a, r) => a + r.ms, 0);
const allAt0 = first.reduce((a, r) => a + r.ms, 0);
const grapheneSeen = new Map(); // pid -> last CPU ms seen (a process that ended keeps its last)
let samples = 0;
while (Date.now() - t0 < seconds * 1000) {
  await new Promise((r) => setTimeout(r, 200)); // a `graphene state --json` lives about 100 ms
  for (const r of tree()) if (isGraphene(r.command)) grapheneSeen.set(r.pid, Math.max(grapheneSeen.get(r.pid) ?? 0, r.ms));
  samples++;
}
const last = tree();
const elapsed = (Date.now() - t0) / 1000;
const hostMs = last.filter((r) => isHost(r.command)).reduce((a, r) => a + r.ms, 0) - hostAt0;
const allMs = last.reduce((a, r) => a + r.ms, 0) - allAt0;
const grapheneMs = [...grapheneSeen.values()].reduce((a, b) => a + b, 0);
const pct = (ms) => (ms / 10 / elapsed).toFixed(1);
console.log(`${app.name}: idle over ${elapsed.toFixed(0)} s with the views open (${samples} samples)`);
console.log(`  extension host: ${pct(hostMs)} % (${hostMs} ms CPU)`);
console.log(`  graphene processes seen: ${grapheneSeen.size}, ${pct(grapheneMs)} % (${grapheneMs} ms CPU, 200 ms samples: a shorter process may be missed, and the last sample of one undercounts it)`);
console.log(`  the whole app tree: ${pct(allMs)} % (${allMs} ms CPU; ps time has 10 ms steps)`);
await L.close(s);
rmSync(base, { recursive: true, force: true });
