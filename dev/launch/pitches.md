# Pitch lines

Each is under fifteen words and uses no word the README does not define. Pick by the reader, not by taste.

## For someone who is not an engineer

1. Your AI coding agent stays inside the files you agreed to.
2. See the plan before any code, and say no to what you did not ask for.
3. "Done" means your tests passed, not that the agent said so.
4. When the assistant touches files you never asked about, this is what stops it.

## For an engineer

1. Per-task file scope for Claude Code: refused at the hook, rechecked by git at done.
2. The check runs in a clean worktree, by the tool, not the agent.
3. Each leaf lands as one merge; `git revert -m 1` takes it back.
4. Plan mode asks. This refuses: the files per piece, and a check it runs itself.
