// Graphene: Watch the Demo: the auto replay plays into a directory of its own under the OS temp dir, as a
// child this module owns, and a graph panel of its own shows it. No key and no network. Closing the panel
// stops the replay and removes the directory; so does the editor quitting, before its host goes.
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { GraphHost } from "./graph.ts";
import { Session, STORE, type UI } from "./session.ts";
import type { State } from "./state.ts";

/** Where a replay plays: a new directory under the OS temp dir, never in the person's folder. */
export const demoDir = (tmp = tmpdir()) => mkdtempSync(path.join(tmp, "graphene-demo-"));

/** What the replay says of itself until its store is read: no model ran, by construction. */
export const STAND_IN: C.Replay = { shown: "a scripted stand-in, no model ran", day: "", repository: "" };

/** The replay's session: every state it holds carries `replay`, so the graph draws the replay line and
 *  offers nothing that changes a plan (state.ts does not read the snapshot's `replay` yet). */
export class ReplaySession extends Session {
  replay: C.Replay = STAND_IN;
  override take(state: State) {
    super.take({ ...state, replay: this.replay } as State);
  }
}

/** The replay's end: its child stopped and its directory removed. From the panel's close the child gets TERM
 *  and 500 ms to go before the directory does. From the extension's dispose (the editor quitting) no timer
 *  would ever fire, so the child is killed and the directory removed before dispose returns. */
export function end(child: { exitCode: number | null; kill(signal: "SIGTERM" | "SIGKILL"): boolean }, dir: string, atOnce: boolean) {
  const rm = () => rmSync(dir, { recursive: true, force: true });
  if (atOnce) {
    if (child.exitCode === null) child.kill("SIGKILL");
    return rm();
  }
  if (child.exitCode === null) child.kill("SIGTERM");
  setTimeout(rm, 500);
}

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  let running: { child: ChildProcess; dir: string; stop: (atOnce?: boolean) => void } | null = null;

  context.subscriptions.push({ dispose: () => running?.stop(true) });
  context.subscriptions.push(vscode.commands.registerCommand("graphene.watchDemo", async () => {
    if (running) return void vscode.window.showInformationMessage("The demo is already playing. Close its graph to stop it.");
    const dir = demoDir();
    const child = spawn(session.path, C.demoInto(dir), { cwd: dir, env: C.scrub(process.env), stdio: ["ignore", "pipe", "pipe"] });
    let err = "";
    child.stderr?.on("data", (b: Buffer) => { err += String(b); });
    child.stdout?.resume();
    const replay = new ReplaySession(dir);
    const graph = new GraphHost(context, replay, "Graphene demo");
    const tick = setInterval(() => void replay.refresh(), 1000);
    const stop = (atOnce = false) => {
      if (!running) return;
      running = null;
      clearInterval(tick);
      replay.dispose();
      end(child, dir, atOnce);
    };
    running = { child, dir, stop };
    child.on("exit", (code) => {
      if (running?.child !== child) return;
      if (code) void vscode.window.showErrorMessage(`graphene demo ended: ${C.plain(C.firstLine(err, "", `exit ${code}`))}`);
      stop();
    });
    child.on("error", (e) => { void vscode.window.showErrorMessage(`graphene demo: ${C.plain(e.message)}`); stop(); });

    // the store appears once the replay has set its repo up; then the graph of its own
    const t0 = Date.now();
    while (!existsSync(path.join(dir, STORE)) && child.exitCode === null && Date.now() - t0 < 30_000) {
      await new Promise((r) => setTimeout(r, 300));
    }
    if (!running) return;
    if (!existsSync(path.join(dir, STORE))) {
      void vscode.window.showErrorMessage(`graphene demo made no store in ${dir}: ${C.plain(C.firstLine(err, "", "it said nothing"))}`);
      return stop();
    }
    replay.replay = C.parseReplay((await replay.run(C.stateJson())).stdout) ?? STAND_IN; // its day and repository
    await replay.refresh();
    graph.show();
    context.subscriptions.push(graph.onDidClose(() => stop())); // the panel closing is the end
  }));
}
