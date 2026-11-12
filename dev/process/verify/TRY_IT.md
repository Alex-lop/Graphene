# Alex's manual walk (disposable folder only)

1. In the clone, run `uv sync`, then `cd editors/vscode && npm ci && npm run package`. Install that `.vsix` into a separate editor profile. Expect Graphene to activate; nothing is published.
2. Open a disposable git repository with a first commit. Run `graphene init --planner codex --executor codex`. Expect the Codex hook location and the instruction to trust/review hooks in a new session.
3. Start a new Codex session there, trust the project and review `/hooks`. Expect `graphene ingest hook` under PreToolUse. An old session must restart.
4. Open Graphene's graph and choose Add task. Type a title and files, leaving the check blank. Expect a draft with its missing check shown; `graphene plan --json` still has no task.
5. Open the sidebar's Graph view. Expect the same draft and files. Close/reopen the graph tab, then reload the window and open Graphene again. Expect the draft to survive.
6. Enter a check, such as `grep -qx done inside.txt`. Expect one task in the plan and the draft to disappear from both views.
7. Set three attempts. Expect three waiting attempt chips before any agent starts. Set one again if you want a single run.
8. Add a second task owning a different file. Try to give it the first task's file. Expect one refusal beside the form, no duplicate toast, and the original files retained in the plan.
9. Toggle “I will do this one”, then give it back. Expect “yours”, then “ready”. Toggle approval and change the title; expect the CLI plan to agree.
10. On Home, enable Exact while a suggested plan has an open question. Expect Start to wait. Answer the question and expect Start to become available. Terminal `plan accept` still takes defaults: Exact is a Home control.
11. For an adversarial run, give a task only `inside.txt`, with a note to attempt an outside patch and then complete the inside file. Run with trusted Codex hooks. Expect a denial naming the outside file, no outside file on disk, and only the allowed file to land. The reproducible version is `dev/process/verify/probes/live_codex.py` with an isolated authenticated `CODEX_HOME`.
12. Repeat that fixture with `node set ID --forks 3`. Expect three real attempts, one picked with a reason, and a merge containing only the allowed file.
13. In a disposable shared-checkout task, edit an allowed file yourself while it is held, then call `node done`. Expect your edit to count as task work. Outside its files, expect refusal and your edit retained. Normal worktree runs preserve conflicting human edits and leave the task in review.
14. Start a task with a passing check and change nothing. Expect `node done` to refuse “nothing inside its scope … has changed”.
15. Run `graphene init --remove`. Expect Graphene's Claude and Codex handlers removed, other handlers kept, and the plan/history retained.

These steps do not test Cursor's or Copilot's own agents. Hook trust, startup, crashes and timeouts remain the vendor's boundary; finish checks are still necessary.
