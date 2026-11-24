// A real editor on a folder with no Graphene in it: the extension from its .vsix in a throwaway profile, no
// `graphene` on the PATH, and whatever real Claude Code or Codex sessions the folder has. It opens the graph
// and Home, says what each drew, and takes a picture of each.
//   node sessions.mjs --folder DIR [--app code|cursor] [--vsix FILE] [--out DIR] [--width 1280] [--height 800] [--keep]
// The folder is a scratch repository: for Cursor, close() deletes the folder's entry under ~/.cursor/projects.
import path from "node:path";
import * as L from "./lib.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const appName = arg("--app", "code"), folder = path.resolve(arg("--folder", "")), out = path.resolve(arg("--out", "sessions-shots"));
const vsix = arg("--vsix", null) ? path.resolve(arg("--vsix")) : L.findVsix();
const t0 = Date.now(), say = (l) => console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s ${l}`);
if (!arg("--folder", "")) { console.error("--folder DIR: a scratch repository with a session in it"); process.exit(2); }

const app = await L.findApp(appName);
if (!app) { console.error(`no ${appName} here`); process.exit(1); }
// no graphene anywhere the extension looks: the PATH is the system's own, and its setting names nothing
process.env.PATH = L.noGraphene(process.env.PATH);
const profile = L.makeProfile(L.scratch(`sessions-${appName}-`), { graphene: undefined });
L.installVsix(app, profile, vsix);
const session = await L.launch(app, profile, folder, { width: Number(arg("--width", 1280)), height: Number(arg("--height", 800)) });
say(`launched ${appName} on ${folder}`);
let failed = "";
try {
  await L.openPanel(session.page);
  const { frame, tasks, ms } = await L.waitForGraph(session.page, { timeout: 30000 });
  const drawn = await L.readGraph(frame);
  say(`the graph drew ${tasks} card(s) in ${ms} ms: ${JSON.stringify(drawn.tasks.map((t) => [t.title, t.sub, t.mark]))}`);
  say(`its header: ${JSON.stringify(drawn.goal)}`);
  await L.shot(session.page, path.join(out, `${appName}-graph.png`));
  await L.openSidebar(session.page);
  const home = await L.homeFrame(session.page, 30000);
  await home.waitForSelector(".screen h2", { timeout: 20000 });
  say(`Home: ${JSON.stringify(await home.evaluate(() => [...document.querySelectorAll(".screen h2, .screen p, .screen .pick")].map((e) => e.textContent)))}`);
  await L.shot(session.page, path.join(out, `${appName}-home.png`));
} catch (e) {
  failed = String(e?.message ?? e);
  await L.shot(session.page, path.join(out, `${appName}-failed.png`)).catch(() => {});
} finally {
  if (!process.argv.includes("--keep")) await L.close(session);
}
if (failed) { console.error(`FAILED: ${failed}`); process.exit(1); }
say(`pictures in ${out}`);
