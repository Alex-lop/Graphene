// First run without hunting, the VS Code side: graphene found off the PATH is used and said in the status bar;
// none found offers to install it (graphene.install). A folder with no plan is set up on Home in one pick (home.ts);
// Set Up This Folder (graphene.init) on one that has a plan is two quick picks, who plans and who works, then
// `graphene init --planner X --executor Y` in a terminal.
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { candidates, found } from "./find.ts";
import type { Session, UI } from "./session.ts";

const PLANNERS = [
  { label: "Claude Code", description: "claude on the PATH", word: "claude" },
  { label: "Codex", description: "codex on the PATH", word: "codex" },
  { label: "Nemotron on Token Factory", description: "needs a key: Set Key, or NEBIUS_API_KEY", word: "nemotron" },
  { label: "A command of your own", description: "it takes the prompt last", word: "" },
];

async function who(role: "planner" | "executor"): Promise<string | undefined> {
  const pick = await vscode.window.showQuickPick(PLANNERS, { placeHolder: `the ${role}: ${role === "planner" ? "who splits a goal into tasks" : "who does each task"}`, ignoreFocusOut: true });
  if (!pick) return undefined;
  if (pick.word) return pick.word;
  return vscode.window.showInputBox({ prompt: `The ${role}, a command that takes the prompt last`, placeHolder: "my-agent --model x", ignoreFocusOut: true,
                                      validateInput: (v) => (v.trim() ? undefined : "a command") });
}

const uvBin = (): Promise<string | null> => new Promise((resolve) =>
  execFile("uv", ["tool", "dir", "--bin"], { env: C.scrub(process.env) }, (err, out) => resolve(err ? null : String(out).trim() || null)));

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  const setting = () => vscode.workspace.getConfiguration("graphene").inspect<string>("path");
  const unset = () => { const s = setting(); return !s?.globalValue && !s?.workspaceValue && !s?.workspaceFolderValue; };

  // graphene off the PATH: found once, used while graphene.path is unset, said in the status bar's tooltip
  const look = async () => {
    if (!unset()) { session.found = null; return; }
    const onPath = (process.env.PATH ?? "").split(path.delimiter).filter(Boolean).length;
    const hit = found(candidates(process.env.PATH, os.homedir(), await uvBin()), existsSync, onPath);
    session.found = hit && !hit.onPath ? hit.path : null;
  };
  let offered = false;
  let looked = false; // not before the look: the first read may run before it ends
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e) => { if (e.affectsConfiguration("graphene.path")) void look().then(() => session.refresh()); }));
  context.subscriptions.push(session.onDidChange(() => {
    if (session.status.kind !== "missing" || offered || !looked) return;
    offered = true; // once a session
    void vscode.window.showWarningMessage("Graphene is not installed, or not on this editor's PATH.", "Install Graphene", "Set graphene.path")
      .then((pick) => {
        if (pick === "Install Graphene") void vscode.commands.executeCommand("graphene.install");
        if (pick === "Set graphene.path") void vscode.commands.executeCommand("workbench.action.openSettings", "graphene.path");
      });
  }));

  context.subscriptions.push(vscode.commands.registerCommand("graphene.install", async () => {
    const ok = await vscode.window.showInformationMessage("Install Graphene with uv, in a terminal you can watch? It runs `uv tool install graphene-map`.",
                                                           { modal: true, detail: "uv itself: https://docs.astral.sh/uv/ (one line to install)." }, "Install");
    if (ok !== "Install") return;
    const term = vscode.window.createTerminal({ name: "uv tool install graphene-map", env: C.unmarked(), iconPath: new vscode.ThemeIcon("cloud-download") });
    term.show(true);
    term.sendText("uv tool install graphene-map", true);
    const done = vscode.window.onDidCloseTerminal((t) => { if (t === term) { done.dispose(); void look().then(() => { session.moved(); return session.refresh(); }); } });
    context.subscriptions.push(done);
  }));

  // Set Up This Folder: planner, executor, then `graphene init --planner X --executor Y` in a terminal; once
  // the store appears (uninitialised -> empty), Auto… is offered, once
  let setUp = false;
  context.subscriptions.push(vscode.commands.registerCommand("graphene.init", async () => {
    // a folder with no plan is set up on Home, in one pick; the two picks here change who plans and who works
    if (session.status.kind === "uninitialised") return void vscode.commands.executeCommand("graphene.home");
    const planner = await who("planner");
    if (!planner) return;
    const executor = await who("executor");
    if (!executor) return;
    setUp = true;
    session.terminal("graphene init", [...C.init(), "--planner", planner, "--executor", executor]);
  }));
  context.subscriptions.push(session.onDidChange(() => {
    if (!setUp || session.status.kind !== "empty") return;
    setUp = false;
    void vscode.window.showInformationMessage("This folder is set up. Say what you want done on Graphene's Home.", "Open Home")
      .then((pick) => { if (pick) void vscode.commands.executeCommand("graphene.home"); });
  }));

  void look().then(() => { looked = true; return session.refresh(); });
}
