// A file a running task owns: which agent has it, and its copy to diff with.
// A stub the orchestrator left so the lanes could start at once (lane 2b fills it in).
import * as vscode from "vscode";
import type { Session, UI } from "./session.ts";

export function register(context: vscode.ExtensionContext, _session: Session, _ui: UI) {
  context.subscriptions.push(vscode.commands.registerCommand("graphene.diffWithAgent", () =>
    vscode.window.showInformationMessage("Graphene: diffWithAgent is not built yet.")));
}
