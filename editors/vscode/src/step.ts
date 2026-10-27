// Adding a step. Lane 2b makes Add Step a sentence the planner turns into a proposed step; until then it is
// the four boxes, which stay as Add Step by Hand for people who want to type a scope themselves.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import type { Session, UI } from "./session.ts";
import type { Task } from "./state.ts";

type Arg = string | { id?: string; task?: Task; after?: boolean; under?: boolean } | undefined;

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  const byHand = (arg?: Arg) => addByHand(session, arg);
  context.subscriptions.push(vscode.commands.registerCommand("graphene.addStep", byHand),
                             vscode.commands.registerCommand("graphene.addStepByHand", byHand));
}

/** Title, where, scope and check, one box each; then `graphene node add`. */
export async function addByHand(session: Session, arg?: Arg) {
  const id = typeof arg === "string" ? arg : arg?.task?.id ?? arg?.id;
  const near = id ? session.tasks().find((t) => t.id === id) : undefined;
  const title = await vscode.window.showInputBox({ prompt: "The new step, as a title", ignoreFocusOut: true,
                                                  validateInput: (v) => (v.trim() ? undefined : "a title") });
  if (!title?.trim()) return;
  let parent: string | null = near?.parent ?? null;
  const needs: string[] = [];
  const given = typeof arg === "object" ? arg : undefined;
  if (near && given?.after) needs.push(near.id);
  else if (near && !given?.under) {
    const where = await vscode.window.showQuickPick([
      { label: `after “${near.title}”`, description: "waits on it", v: "after" },
      { label: "beside it", description: near.parent ? `under the same sub-goal` : "at the top", v: "under" },
    ], { placeHolder: "where it goes" });
    if (!where) return;
    if (where.v === "after") needs.push(near.id);
  } else if (!near && session.state?.goals.length) {
    const goals = session.state.goals;
    const where = await vscode.window.showQuickPick([
      { label: "at the top", description: "under the goal itself", id: null as string | null },
      ...goals.map((g) => ({ label: g.title, description: g.id, id: g.id as string | null })),
    ], { placeHolder: "under which sub-goal" });
    if (!where) return;
    parent = where.id;
  }
  const scope = await vscode.window.showInputBox({ prompt: "The files it may write (globs, spaces or commas between), or nothing for now",
                                                  placeHolder: "app.py tests/test_app.py", ignoreFocusOut: true });
  if (scope === undefined) return;
  const check = await vscode.window.showInputBox({ prompt: "The command that passes only when it is done, or nothing for now",
                                                  placeHolder: "pytest -q tests/test_app.py", ignoreFocusOut: true });
  if (check === undefined) return;
  await session.act(C.addStep({ title: title.trim(), parent, needs, scope: C.globs(scope), check: check.trim() || null }));
}
