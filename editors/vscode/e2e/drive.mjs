// A driver a stranger can use from a shell: it launches the app with the extension on a fixture and takes one
// command a line on a localhost port, so a reader with only Bash and Read can use VS Code and look.
//   node drive.mjs [--app code|cursor] [--vsix FILE] [--fixture DIR] [--standin] [--auto] [--port N] [--shots DIR]
// It prints `port N` (and writes N to --shots/drive.port). Then, from any shell:
//   printf 'shot first\n' | nc 127.0.0.1 N
// Commands (one a line; the answer ends when the connection closes):
//   shot NAME          a screenshot, NAME.png under --shots; prints its path
//   palette TITLE      run a command by its palette title
//   click TEXT         click the first element with that text, in the page or in a webview frame
//   type TEXT          type into what has focus
//   key COMBO          press a key (Enter, Escape, Meta+Shift+P, ...)
//   frames             print every frame's text
//   graph              print what the graph frames show, as JSON
//   sidebar N          set the side bar's width in px
//   size WxH           set the window's content size; answers with the size it took (what fits the display)
//   theme NAME         set the colour theme (dark, light, hc, or a theme's name)
//   auto               start `graphene auto` against the stand-in in the fixture (once)
//   sh CMD             run a graphene command in the fixture (CMD after `graphene`, quoted as in a shell), print its output
//   quit               close the app and stop
import { mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import path from "node:path";
import * as L from "./lib.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const flag = (k) => process.argv.includes(k);
const appName = arg("--app", "code");
const shots = path.resolve(arg("--shots", "drive-shots"));
mkdirSync(shots, { recursive: true });

const app = await L.findApp(appName);
if (!app) { console.error(`no ${appName} here`); process.exit(1); }
const graphene = L.findGraphene();
const base = L.scratch(`drive-${appName}-`);
const profile = L.makeProfile(base, { graphene });
L.installVsix(app, profile, arg("--vsix", null) ? path.resolve(arg("--vsix")) : L.findVsix());
let standin = null;
if (flag("--standin") || flag("--auto")) standin = await L.startStandin();
let fx;
if (arg("--fixture", null)) {
  fx = { dir: path.resolve(arg("--fixture")), graphene, env: L.fixtureEnv(standin?.url) };
} else {
  fx = L.makeFixture(path.join(base, "wordkit"), graphene, { standin: standin?.url });
}
const session = await L.launch(app, profile, fx.dir, { width: 1280, height: 800, standin: standin?.url });
await L.openSidebar(session.page);
let auto = null;
const startAuto = () => { if (!auto && standin) auto = L.startAuto(fx, { log: path.join(shots, "auto.log") }); return auto ? "auto runs" : "no stand-in: start with --auto"; };
if (flag("--auto")) startAuto();

async function run(line) {
  const [cmd, ...rest] = line.trim().split(/\s+/);
  const text = line.trim().slice(cmd.length).trim();
  const page = session.page;
  switch (cmd) {
    case "shot": { const f = path.join(shots, `${rest[0] || "shot"}.png`); await L.shot(page, f); return f; }
    case "palette": await L.palette(page, text); return "ok";
    case "click": {
      const own = page.getByText(text).first();
      if (await own.count()) { await own.click({ timeout: 5000 }); return "clicked (page)"; }
      for (const f of page.frames()) {
        const el = f.getByText(text).first();
        if (await el.count().catch(() => 0)) { await el.click({ timeout: 5000 }); return "clicked (frame)"; }
      }
      return `err: nothing reads "${text}"`;
    }
    case "type": await page.keyboard.type(text); return "ok";
    case "key": await page.keyboard.press(text); return "ok";
    case "frames": return (await L.framesText(page)).map((f) => `--- ${f.url}\n${f.text}`).join("\n") || "(no text)";
    case "graph": { const out = []; for (const f of await L.graphFrames(page)) out.push(await L.readGraph(f)); return JSON.stringify(out, null, 1); }
    case "sidebar": return `side bar ${await L.setSidebarWidth(page, Number(rest[0]))} px`;
    case "size": { const [w, h] = rest[0].split("x").map(Number); const got = await L.setSize(session.electronApp, page, w, h); return `size ${got.width}x${got.height}${got.width !== w || got.height !== h ? ` (asked ${w}x${h})` : ""}`; }
    case "theme": await L.setTheme(page, profile, L.THEMES[text] || text); return `theme ${L.THEMES[text] || text}`;
    case "auto": return startAuto();
    case "sh": return L.shell(graphene, text, { cwd: fx.dir, env: fx.env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    case "quit": setTimeout(quit, 50); return "bye";
    case "": return "";
    default: return `err: unknown command ${cmd}`;
  }
}

async function quit() {
  await L.close(session);
  standin?.stop();
  auto?.kill("SIGTERM");
  process.exit(0);
}

let busy = Promise.resolve();
// allowHalfOpen: `nc` sends its end-of-input before the answer comes; without it node drops the answer
const server = createServer({ allowHalfOpen: true }, (sock) => {
  let buf = "", ended = false;
  const pending = [];
  const drain = () => {
    busy = busy.then(async () => {
      while (pending.length) {
        const line = pending.shift();
        let answer;
        try { answer = await run(line); } catch (err) { answer = `err: ${err.message.split("\n")[0]}`; }
        sock.write(`${answer}\n`);
      }
      if (ended) sock.end();
    });
  };
  sock.on("data", (d) => {
    buf += d;
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) { pending.push(buf.slice(0, nl)); buf = buf.slice(nl + 1); }
    drain();
  });
  sock.on("end", () => { if (buf.trim()) pending.push(buf); buf = ""; ended = true; drain(); });
  sock.on("error", () => {});
});
server.listen(Number(arg("--port", 0)), "127.0.0.1", () => {
  const port = server.address().port;
  writeFileSync(path.join(shots, "drive.port"), `${port}\n`);
  console.log(`port ${port}`);
  console.log(`fixture ${fx.dir}`);
  console.log(`shots ${shots}`);
});
process.on("SIGTERM", quit);
process.on("SIGINT", quit);
