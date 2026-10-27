// The Needs You view: what waits for the person, first, each with its move inline.
// A stub the orchestrator left so the lanes could start at once (lane 2a fills it in).
import * as vscode from "vscode";
import type { Session, UI } from "./session.ts";

export function register(context: vscode.ExtensionContext, _session: Session, _ui: UI) {
  context.subscriptions.push(vscode.window.registerTreeDataProvider("graphene.needs", {
    getTreeItem: (n: vscode.TreeItem) => n, getChildren: () => [] as vscode.TreeItem[] }));
  context.subscriptions.push(vscode.commands.registerCommand("graphene.answer", () =>
    vscode.window.showInformationMessage("Graphene: answer is not built yet.")));
  context.subscriptions.push(vscode.commands.registerCommand("graphene.handBack", () =>
    vscode.window.showInformationMessage("Graphene: handBack is not built yet.")));
}
