// A task's or a fork's changes in VS Code's own diff editor; picking a fork, signing off.
// A stub the orchestrator left so the lanes could start at once (lane 2b fills it in).
import * as vscode from "vscode";
import type { Session, UI } from "./session.ts";

export function register(context: vscode.ExtensionContext, _session: Session, _ui: UI) {
  context.subscriptions.push(vscode.commands.registerCommand("graphene.openDiff", () =>
    vscode.window.showInformationMessage("Graphene: openDiff is not built yet.")));
  context.subscriptions.push(vscode.commands.registerCommand("graphene.compareForks", () =>
    vscode.window.showInformationMessage("Graphene: compareForks is not built yet.")));
  context.subscriptions.push(vscode.commands.registerCommand("graphene.pickFork", () =>
    vscode.window.showInformationMessage("Graphene: pickFork is not built yet.")));
  context.subscriptions.push(vscode.commands.registerCommand("graphene.signOff", () =>
    vscode.window.showInformationMessage("Graphene: signOff is not built yet.")));
}
