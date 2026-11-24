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
import { behind, candidates, found, olderWords } from "./find.ts";
import { ASK, NOT_CURSOR } from "./home/who.ts";
import type { Session, UI } from "./session.ts";

const PLANNERS = [
  { label: "Claude Code", description: "claude on the PATH", word: "claude" },
  { label: "Codex", description: "codex on the PATH", word: "codex" },
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

  // an older graphene reads, but every pane would say Not held: said once a version here (Home says it for as long
  // as it holds), and the walkthrough's Install step is not done while it does
  let told = "", old = false;
  context.subscriptions.push(session.onDidChange(() => {
    if (old !== behind(session.version)) void vscode.commands.executeCommand("setContext", "graphene.older", old = !old);
    if (!old || told === session.version) return;
    told = session.version ?? "";
    void vscode.window.showWarningMessage(olderWords(session.file || session.path, session.version).replaceAll("`", ""), "Upgrade Graphene")
      .then((pick) => { if (pick) void vscode.commands.executeCommand("graphene.install"); });
  }));

  context.subscriptions.push(vscode.commands.registerCommand("graphene.install", async () => {
    const [word, line] = behind(session.version) ? ["Upgrade", C.UV_UPGRADE] : ["Install", C.UV_INSTALL];
    const ok = await vscode.window.showInformationMessage(`${word} Graphene with uv, in a terminal you can watch? It runs \`${line}\`.`,
                                                           { modal: true, detail: "It gets the newest graphene-map from where uv installed it: PyPI, or the folder it was installed from (then pull that folder first, or `uv tool install --force graphene-map`); this extension needs 0.10 or later. uv itself: https://docs.astral.sh/uv/ (one line to install)." }, word);
    if (ok !== word) return;
    const term = vscode.window.createTerminal({ name: line, env: C.unmarked(), iconPath: new vscode.ThemeIcon("cloud-download") });
    term.show(true);
    term.sendText(line, true);
    const done = vscode.window.onDidCloseTerminal((t) => { if (t === term) { done.dispose(); void look().then(() => { session.moved(); return session.refresh(); }); } });
    context.subscriptions.push(done);
  }));

  // Set Up This Folder: planner, executor, then `graphene init --planner X --executor Y` in a terminal; once
  // the store appears (uninitialised -> empty), a toast says the plan comes from your agent's chat, once
  let setUp = false;
  context.subscriptions.push(vscode.commands.registerCommand("graphene.init", async () => {
    // a folder with no plan is set up on Home, in one pick; the two picks here change who plans and who works
    if (session.status.kind === "uninitialised") return void vscode.commands.executeCommand("graphene.setUpScreen");
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
    const cursor = vscode.env.appName.includes("Cursor") ? ` ${NOT_CURSOR}` : "";
    void vscode.window.showInformationMessage(`This folder is set up. ${ASK}: its plan shows on the graph.${cursor}`, "Open Home")
      .then((pick) => { if (pick) void vscode.commands.executeCommand("graphene.home"); });
  }));

  void look().then(() => { looked = true; return session.refresh(); });
}
