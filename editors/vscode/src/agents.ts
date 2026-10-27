// The Agents view: every running agent, what it is doing now, seconds quiet and dollars.
// A stub the orchestrator left so the lanes could start at once (lane 2a fills it in).
import * as vscode from "vscode";
import type { Session, UI } from "./session.ts";

export function register(context: vscode.ExtensionContext, _session: Session, _ui: UI) {
  context.subscriptions.push(vscode.window.registerTreeDataProvider("graphene.agents", {
    getTreeItem: (n: vscode.TreeItem) => n, getChildren: () => [] as vscode.TreeItem[] }));
}
