# How Graphene compares

Read from vendors' own pages, releases and public issues on 14 October 2026 by a model session standing in for a
researcher. Each cell says where it came from; where a page was not read, the cell says so. Graphene is in the same
table, and what it lacks is in the table too. The fuller reading, with every page, is in
[`dev/process/controller/designs.md`](../dev/process/controller/designs.md).

## The problem, in users' words

- "Claude modified files I didn't ask it to modify": the first option on Anthropic's own bug form for model behaviour.
- "reports ALL PASSED when tests are FAILING" ([claude-code issue 46940](https://github.com/anthropics/claude-code/issues/46940)).
- "System-level enforcement that prevents Claude from modifying any files except those explicitly authorized"
  ([claude-code issue 4452](https://github.com/anthropics/claude-code/issues/4452)).

## What each one gives of control

| | A plan before code | The files a piece may change | A check the tool runs itself | A look at the diff before the merge |
|---|---|---|---|---|
| **Graphene**, with Claude Code | a tree you edit and accept | per leaf; a write outside is refused before it happens (Claude Code only; git catches the rest at `done`) | yes, in a clean copy | a leaf marked for sign-off waits on its branch, and `c` in `graphene watch` shows its diff |
| Claude Code, by itself | plan mode; its docs say it is not enforced in interactive sessions where bypass is available | static allow and deny rules, not per piece | only if you write a hook | `claude agents` groups what is "Ready for review" |
| Codex | approvals and a sandbox (read-only, workspace-write) | the sandbox, not a list per piece | not documented | cloud tasks end in a diff or a pull request (third-party guides) |
| Cursor | Plan Mode, editable | hooks can allow or deny a write; no file list tied to a plan item | not documented | background agents open pull requests (third-party) |
| Kiro | specs, then a task graph run in parallel waves | not documented | not documented | not read |
| Cline | Plan and Act modes | auto-approve per category | not read | checkpoints for rollback |
| Spec Kit | spec templates and a CLI | no | no | no |
| GitHub Copilot cloud agent | not read | no per-file limit | required checks run by GitHub | a person merges: the requester cannot approve their own pull request |
| Conductor | no | no | CI checks | a diff viewer, then merge |
| Entire 0.11.5 | trails (intent across branches) | no | gates before merge, evaluated server side | trail review |
| my-pi (Pi agent) | not read | a per-task editable scope; edits outside it are blocked | deterministic validation scripts | stops for review before commit |
| Ralon | no | a kernel-enforced write lock from one static list | no | no |

## What this says, and does not say

For Claude Code, nothing read gives all of this together: a plan where every piece names the files it may change and
the check it must pass, a write outside those files refused as it happens, the check run by the tool in a clean copy,
and a piece landed only when it passes, on your machine with no account. That is the claim, and it is scoped: my-pi
has a per-task file scope with checks for another agent, and Ralon locks writes more strongly than a hook does, from
one static list. Nobody here is "the only one".

What Graphene lacks, in this table: it holds a write before it happens only for Claude Code (for Codex and any other
command, git finds it when the leaf is declared done); its hook fails open if it cannot run; a run says its worst
case before it starts and a Claude Code attempt stops at $2, but no spend cap covers a whole run's total and Codex
has no cap at all; a leaf allowed to edit the test its own check runs can weaken it, and `done` flags that and does
not refuse it; and it is local, so nothing runs off your laptop.

Plan approval, which this project first led with, is in Claude Code, Cursor, Kiro, Cline and Spec Kit. It is no
longer what is different.
