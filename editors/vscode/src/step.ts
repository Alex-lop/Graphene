// Adding a step. Add Step is one sentence: the planner proposes the step with its scope, check and needs, and
// it appears as a proposal to accept. Add Step by Hand keeps the four boxes for people who want to type a
// scope themselves.
import * as vscode from "vscode";
import * as C from "./commands.ts";
import type { Session, UI } from "./session.ts";
import type { Task } from "./state.ts";

/** `sentence` is for a harness that drives the command; a person is asked for it. */
type Arg = string | { id?: string; task?: Task; after?: boolean; under?: boolean; sentence?: string } | undefined;

export function register(context: vscode.ExtensionContext, session: Session, _ui: UI) {
  context.subscriptions.push(vscode.commands.registerCommand("graphene.addStep", (arg?: Arg) => addStep(session, arg)),
                             vscode.commands.registerCommand("graphene.addStepByHand", (arg?: Arg) => addByHand(session, arg)));
}

/** One line, then `graphene ask --step`: after a task, under a goal, or wherever the planner puts it. */
export async function addStep(session: Session, arg?: Arg) {
  const id = typeof arg === "string" ? arg : arg?.task?.id ?? arg?.id;
  const given = typeof arg === "object" ? arg : undefined;
  const task = id ? session.tasks().find((t) => t.id === id) : undefined;
  const goal = id && !task ? session.state?.goals.find((g) => g.id === id) : undefined;
  // after a task unless told under; under a goal
  const where = !id ? {} : given?.under || goal ? { under: id } : { after: id };
  const near = task?.title ?? goal?.title;
  const sentence = given?.sentence ?? await vscode.window.showInputBox({
    prompt: near ? `The new step, in a sentence (${where.after ? "after" : "under"} “${near}”)` : "The new step, in a sentence",
    placeHolder: "a --json flag on the list command, with a test", ignoreFocusOut: true,
    validateInput: (v) => (v.trim() ? undefined : "say what the step should do"),
  });
  if (!sentence?.trim()) return;
  const out = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Graphene plans the step…" },
                                               () => session.run(C.askStep(sentence.trim(), where)));
  void session.refresh();
  if (out.code !== 0) {
    const why = out.code === -1 ? "graphene was not found" : C.refusal(out.stderr, out.stdout);
    return void vscode.window.showErrorMessage(`graphene ask --step: ${why}`);
  }
  const p = C.proposed(out.stdout);
  if (!p) return void vscode.window.showInformationMessage(`Graphene: ${C.firstLine(out.stdout, out.stderr, "nothing was proposed")}`);
  const pick = await vscode.window.showInformationMessage(`Proposed: ${p.title} (${p.id})`, "Accept", "Drop");
  if (pick === "Accept") await session.act(C.accept(p.id));
  if (pick === "Drop") await session.act(C.dropStep(p.id));
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
