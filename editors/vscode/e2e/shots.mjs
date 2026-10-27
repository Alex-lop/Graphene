// Screenshots and video of the extension in the real app, on a store a stand-in race changed:
//   node shots.mjs --app code|cursor --vsix FILE --out DIR [--video DIR] [--during] [--keep]
// The side bar at 280, 320 and 400 px; the editor tab at 1280x800 and 1920x1080; each in Dark Modern, Light
// Modern and High Contrast; named APP-WHAT-THEME.png under --out, with smallest-text.json beside them (the
// smallest text drawn in each, font size times the SVG's scale). By default the race runs to its end before
// the window opens, so every shot is the same finished store; --during starts the race after the window
// opens, so the video shows it live. --video puts the session's .webm in DIR.
import { renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import * as L from "./lib.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const flag = (k) => process.argv.includes(k);
const appName = arg("--app", "code"), out = path.resolve(arg("--out", "shots")), video = arg("--video", null);
const vsix = arg("--vsix", null) ? path.resolve(arg("--vsix")) : L.findVsix();
const WIDTHS = [280, 320, 400], SIZES = [[1280, 800], [1920, 1080]];
const t0 = Date.now();
const say = (l) => console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s ${l}`);

const app = await L.findApp(appName);
if (!app) { console.error(`no ${appName} here`); process.exit(1); }
const graphene = L.findGraphene();
const base = L.scratch(`shots-${appName}-`);
const profile = L.makeProfile(base, { graphene });
L.installVsix(app, profile, vsix);
const standin = await L.startStandin();
const fx = L.makeFixture(path.join(base, "wordkit"), graphene, { standin: standin.url });
say(`fixture ${fx.dir}, stand-in ${standin.url}`);
const autoLog = path.join(out, `${appName}-auto.log`);
let auto = null;
if (!flag("--during")) {
  auto = L.startAuto(fx, { log: autoLog });
  const code = await new Promise((r) => auto.on("exit", r));
  say(`the race ran to its end (exit ${code}, log ${autoLog})`);
}
const session = await L.launch(app, profile, fx.dir, { width: 1280, height: 800, video });
say("launched");
if (flag("--during")) auto = L.startAuto(fx, { log: autoLog });
await L.openSidebar(session.page);
await L.waitForGraph(session.page, { min: 1, timeout: 90000 });
say("the side bar's graph is drawn");
const smallest = {};
const take = async (what, theme) => {
  const frames = await L.graphFrames(session.page);
  const file = path.join(out, `${appName}-${what}-${theme}.png`);
  await L.shot(session.page, file);
  const texts = [];
  for (const f of frames) texts.push(await L.smallestText(f).catch(() => null));
  smallest[path.basename(file)] = texts.filter(Boolean).sort((a, b) => a.px - b.px)[0] ?? null;
  say(`shot ${path.basename(file)} smallest text ${JSON.stringify(smallest[path.basename(file)])}`);
};
for (const [key, theme] of Object.entries(L.THEMES)) {
  await L.setTheme(session.page, profile, theme);
  for (const w of WIDTHS) {
    const got = await L.setSidebarWidth(session.page, w);
    if (Math.abs(got - w) > 2) say(`side bar asked ${w}, got ${got}`);
    await session.page.waitForTimeout(500);
    await take(`sidebar-${w}`, key);
  }
}
await L.setSidebarWidth(session.page, 300);
await L.openPanel(session.page);
say("the panel is open");
for (const [key, theme] of Object.entries(L.THEMES)) {
  await L.setTheme(session.page, profile, theme);
  for (const [w, h] of SIZES) {
    await L.setSize(session.electronApp, session.page, w, h);
    await session.page.waitForTimeout(700);
    await take(`panel-${w}x${h}`, key);
  }
}
if (flag("--during") && auto && auto.exitCode === null) {
  say("waiting for the race to end, for the video");
  await new Promise((r) => { auto.on("exit", r); setTimeout(r, 180000); });
  await session.page.waitForTimeout(1500);
  await take("panel-1920x1080-end", "dark");
}
writeFileSync(path.join(out, `${appName}-smallest-text.json`), JSON.stringify(smallest, null, 2));
const clip = video ? await session.page.video()?.path() : null;
await session.electronApp.close();
if (clip) {
  const named = path.join(video, `${appName}-${flag("--during") ? "race" : "shots"}-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.webm`);
  renameSync(clip, named);
  say(`video ${named}`);
}
standin.stop();
auto?.kill("SIGTERM");
say(`done: ${Object.keys(smallest).length} shots in ${out}${flag("--keep") ? `, profile kept at ${base}` : ""}`);
if (!flag("--keep")) (await import("node:fs")).rmSync(base, { recursive: true, force: true });
