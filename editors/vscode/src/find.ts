// Finding graphene on this machine, and offering to install it.
// A stub the orchestrator left so the lanes could start at once (lane 2a fills it in).
import * as vscode from "vscode";
import type { Session, UI } from "./session.ts";

export function register(context: vscode.ExtensionContext, _session: Session, _ui: UI) {
  context.subscriptions.push(vscode.commands.registerCommand("graphene.install", () =>
    vscode.window.showInformationMessage("Graphene: install is not built yet.")));
}
