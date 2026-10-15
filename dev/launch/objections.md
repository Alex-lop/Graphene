# The five hardest questions, answered plainly

1. **Isn't this plan mode?** Plan mode asks the agent to plan and, in Claude Code's own docs, is not enforced in
   interactive sessions where bypass is available. Here the plan is a set of pieces that each name the files they may
   change and the check they must pass, a hook refuses a write outside them as it happens, and the tool runs the
   check. Cursor, Kiro and Cline have plan approval too: that is not what is different. See docs/COMPARE.md.
2. **Does a tree beat a good paragraph?** Not so far. On small tasks a plain paragraph did as well for less (modelled
   person-seconds 2,626 against 3,869; $0.97 against $1.47: dev/test/results-2026-09-23.md). What the tree adds is
   timing (you see the misunderstanding before the money is spent) and a record: seven of eight factual questions
   answered where `git log -p` answered five, with AI readers (dev/process/prove/after.md).
3. **Where is the diff before the merge?** A leaf marked for sign-off waits on its branch, `c` in `graphene watch`
   shows its whole diff, and `y` merges it. A leaf without sign-off lands when its check passes, as one merge you
   can `git revert -m 1`. Other tools put a diff or a pull request in front of every change; this does for the
   leaves you mark.
4. **What does it record, and what can it cost me?** `graphene init` adds hooks to one project; they record that
   project's Claude Code sessions on your machine only, and `graphene init --remove` takes them out. With Claude
   Code an attempt stops at $2, three attempts at most, and `graphene run` says the worst case before it starts and
   stops with `graphene run --stop`; Codex has no cap and nothing caps a whole run's total.
5. **Has anyone but you used it?** No person has been timed. Every walk and measure used model sessions standing in
   for people (dev/process/controller/). It is early; the first-hour form is how a real hour reaches the repository.
