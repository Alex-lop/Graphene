// A file a running task owns: the status bar says which agent has it, and offers its copy to diff with.
// The person's own editing is never blocked.
import { existsSync } from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import * as C from "./commands.ts";
import { owner } from "./owners.ts";
import type { Session, UI } from "./session.ts";
import type { Task } from "./state.ts";

/** The snapshot's `checkout` fields (CONTRACT.md), read loosely until state.ts carries them. */
type Where = { checkout?: string | null; forks: { letter: string; checkout?: string | null }[] };

/** The running task whose file the active editor shows, and the file's path inside the repo. */
function held(session: Session, uri: vscode.Uri | undefined): { task: Task; rel: string } | null {
  const root = session.folder?.uri.fsPath;
  if (!root || !uri || uri.scheme !== "file" || !session.state) return null;
  const rel = path.relative(root, uri.fsPath).split(path.sep).join("/");
  if (rel.startsWith("../") || path.isAbsolute(rel)) return null;
  const o = owner(rel, session.state.tasks);
  if (!o || o.state !== "running") return null;
  const task = session.state.tasks.find((t) => t.state === "running" && owner(rel, [t]));
  return task ? { task, rel } : null;
}

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  const bar = vscode.window.createStatusBarItem("graphene.file", vscode.StatusBarAlignment.Right, 100);
  bar.name = "Graphene: whose file";
  bar.command = "graphene.diffWithAgent";
  const show = () => {
    const h = held(session, vscode.window.activeTextEditor?.document.uri);
    if (!h) return bar.hide();
    const who = h.task.agent ? `agent ${h.task.agent}` : "an agent";
    const forks = h.task.forks.length > 1 ? ` (${h.task.forks.length} attempts)` : "";
    bar.text = `$(person) ${who} has ${path.basename(h.rel)}${forks}`;
    bar.tooltip = `${h.task.title}: ${who} is writing it now. Click to diff with its copy. Your own edits are not blocked.`;
    bar.show();
  };
  context.subscriptions.push(bar, vscode.window.onDidChangeActiveTextEditor(show), session.onDidChange(show));
  show();

  context.subscriptions.push(vscode.commands.registerCommand("graphene.diffWithAgent", async () => {
    const h = held(session, vscode.window.activeTextEditor?.document.uri);
    if (!h) return void vscode.window.showInformationMessage("Graphene: no running agent has this file.");
    const root = session.folder!.uri.fsPath;
    const t = h.task as Task & Where;
    const forks = t.forks as Where["forks"];
    const copies = forks.length
      ? forks.map((f) => ({ label: `attempt ${f.letter}`, dir: C.agentCopy(root, t.id, f.checkout, f.letter) }))
      : [{ label: `agent ${t.agent}`, dir: C.agentCopy(root, t.id, t.checkout) }];
    const there = copies.filter((c) => existsSync(path.join(c.dir, h.rel)));
    if (!there.length) return void vscode.window.showInformationMessage(`Graphene: ${copies[0]!.label}'s copy of ${h.rel} is not on this machine yet.`);
    const chosen = there.length === 1 ? there[0] : await vscode.window.showQuickPick(there.map((c) => ({ label: c.label, description: c.dir, c })), { placeHolder: "whose copy" }).then((p) => p?.c);
    if (!chosen) return;
    await vscode.commands.executeCommand("vscode.diff", vscode.Uri.file(path.join(chosen.dir, h.rel)), vscode.window.activeTextEditor!.document.uri,
                                         `${h.rel}: ${chosen.label}'s copy ↔ yours`, { preview: false });
  }));
}
