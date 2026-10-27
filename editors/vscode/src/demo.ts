// Graphene: Watch the Demo: the auto replay in the graph, no key and no network.
// A stub the orchestrator left so the lanes could start at once (lane 2b fills it in).
import * as vscode from "vscode";
import type { Session, UI } from "./session.ts";

export function register(context: vscode.ExtensionContext, _session: Session, _ui: UI) {
  context.subscriptions.push(vscode.commands.registerCommand("graphene.watchDemo", () =>
    vscode.window.showInformationMessage("Graphene: watchDemo is not built yet.")));
}
