// Watch the Demo at one moment, in real VS Code at 1920x1050, in dark and in light: the evidence for the canvas
// run's look (dev/SCOPE.md, leaf 2). The moment is the first frame in which three tasks are working with their
// attempts fanned out, so a before and an after show the same store. No model and no network: the demo replays
// a scripted stand-in.
//   cd editors/vscode && npm run package && cd e2e && npm ci      # once: the .vsix and the harness
//   node dev/process/canvas/shoot.mjs before|after [moment]       # writes NAME-demo-1920x1050-THEME.png here
// `moment` is `working` (the default) or `done` (every task landed).
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as L from "../../../editors/vscode/e2e/lib.mjs";

const name = process.argv[2] || "after", moment = process.argv[3] || "working";
const out = path.dirname(fileURLToPath(import.meta.url));
const app = await L.findApp("code");
if (!app) { console.error("shoot: no VS Code to drive (set VSCODE_EXECUTABLE)"); process.exit(1); }
const graphene = L.findGraphene(), vsix = L.findVsix();

for (const theme of ["dark", "light"]) {
  const base = L.scratch("canvas-");
  const profile = L.makeProfile(base, { graphene, theme: L.THEMES[theme] });
  L.installVsix(app, profile, vsix);
  const fx = L.makeFixture(path.join(base, "wordkit"), graphene);
  const session = await L.launch(app, profile, fx.dir, { width: 1920, height: 1050 });
  try {
    const page = session.page;
    await L.palette(page, "View: Close Primary Side Bar"); // the canvas takes the window, as the target does
    await L.palette(page, "Graphene: Watch the Demo");
    const { frame } = await L.waitForGraph(page, { min: 3, timeout: 90000 });
    const at = moment === "done"
      ? () => { const t = [...document.querySelectorAll("#view g.task")]; return t.length >= 3 && t.every((g) => g.classList.contains("st-done")); }
      : () => document.querySelectorAll("#view g.task.st-running").length >= 3 && document.querySelectorAll("#view g.fork").length >= 9;
    await frame.waitForFunction(at, null, { timeout: 180000, polling: 100 });
    await page.waitForTimeout(600); // the boxes have glided to their places
    const file = path.join(out, `${name}-demo-1920x1050-${theme}${moment === "working" ? "" : `-${moment}`}.png`);
    await L.shot(page, file);
    console.log(`shoot: ${path.relative(process.cwd(), file)} (${session.size.width}x${session.size.height})`);
  } finally {
    await L.close(session);
  }
}
