# What an edit does to a task, by its state

Asked of the engine on 10 November 2026 (0.9.0), not assumed: `probes/edits.sh` makes a fixture repo, puts a task in
each state, and changes every field of the pane's form with `graphene node set`. The pane's one line
(`whenEdit` in `editors/vscode/src/graph/words.ts`) says this table in the screen's words.

| State on screen | The engine's answer | The pane says |
|---|---|---|
| suggested | every field is taken; it stays suggested | nothing runs yet; a change binds once you accept it |
| ready, waiting | every field is taken (`n1 is now revision 2: title: … → …`) | its agent starts from what you set here |
| working | taken, and: `n1 is running on revision 10: its next write is held to the new scope, and its done to the new check` | new files hold its agent's next write; a new check, or your approval, its finish; attempts wait for its next start |
| to review | taken; the work stays as it finished | a change binds when it starts again, if you send it back |
| needs help | taken (it is open again) | a change binds when it starts again |
| yours | taken; `--owner agent` gives it back | no agent takes it; untick "I will do this one" and one can |
| done | refused: `n1 is done, and a finished node's contract is not edited` / `graphene node reopen n1 --note '…' opens it again` | a finished task is not edited; send it back to open it again |

Refusals the form meets, shown whole in the pane and never worked round:

- attempts with no check: `n3: 2 forks need a check to keep one; a sign-off cannot choose` (the stepper is off
  until the task has a check, and says so);
- the check taken away from a task with attempts: the same line;
- files another task writes: `n2 and n1 both write wordkit/cli.py. A path has one leaf that writes it: give it to
  one, and let the other wait on it`.

Read from the code, not probed: attempts are read when a run starts a task (`run.forks_of`), your approval when
it finishes (`plan.finish`). To review, a new check does run at Approve when your branch moved since the task was
cut (`run._red_on_merge`); the pane's line leaves that out.
