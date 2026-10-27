// The plan as a text document: saving applies it, refusals are diagnostics on their lines.
// A stub the orchestrator left so the lanes could start at once (lane 2b fills it in).
import * as vscode from "vscode";
import type { Session, UI } from "./session.ts";

export function register(context: vscode.ExtensionContext, _session: Session, _ui: UI) {
  context.subscriptions.push(vscode.commands.registerCommand("graphene.editPlan", () =>
    vscode.window.showInformationMessage("Graphene: editPlan is not built yet.")));
}
