# Graphene: what it is, and what has been decided

*Alex, this file is yours. Edit anything here and the next agent that works on this repo treats your
edit as binding: it reads this before it reads the code. It is the same shape as the product: you
shape the plan, the agents execute it. First written 2026-09-20 by the agent that ran the
collaboration directive (`docs/process/directives/COLLABORATION_DIRECTIVE.md`); last added to on
2026-09-24, by the agent that ran the polish directive.*

## What Graphene is

Graphene is the shared plan between a person and their coding agents: a graph of the work, which
both can see, which the person shapes, and which the agents are held to.

You let agents work on your repo for hours. Today the only ways to steer them are a paragraph at the
start and a diff at the end. Graphene puts a plan in between: the work is cut into **nodes**, each
saying what it should achieve, which paths it may touch, how anyone will know it is done, what it
waits on, and whose it is. You edit that plan before anything is spent. You change the next node
when the last one finishes. And for every node there is a **record** of what was really done for it
and how much of that can be verified.

- A **node** is a unit of work someone will do: an agent of any vendor, or you.
- The **plan** (the graph) is the nodes and what they wait on. It is about what will happen.
- The **record** is what did happen, per node: who held it, what was refused, what the check said,
  and an honest count of what cannot be accounted for.

## Decisions taken so far

Each has its reason, so you can tell when it no longer applies. Strike any of them.

1. **One mechanism binds, whoever executes: the boundary.** A node is done only when Graphene
   itself has run the node's check and has asked git what changed since the node was started. A
   change outside the scope keeps the node open, however the file was written, and nothing that waits
   on it can start. *Why:* it needs no vendor. On 2026-09-20 the same gate held a Claude Code agent,
   a Codex agent and a person doing a node by hand.
2. **Two routes sit on that core, and both ship.** Inside a Claude Code session, the hooks refuse a
   write outside the scope before it happens, refuse a stop while a node is open, and the next
   node's contract is read fresh when it is started. For unattended work, `graphene run` takes each
   ready node, hands its contract (and nothing else) to an executor, and decides itself whether it
   is done, sending a refused executor back. *Why both:* the directive leaned to the first route, and
   it is the one a person sits in. The spikes showed its stop refusal is a nag with a ceiling (the
   vendor ends the turn after about 8 refusals, and a headless run that hits `--max-turns` never
   fires the stop hook at all). What held every time was a check made out of process after the
   agent was gone. That check is decision 1, so the second route cost 125 lines.
3. **The plan's surface is the command line, not an MCP server.** `graphene plan`, `graphene node
   start|done|release`. *Why:* every executor has a shell, including Codex and you; every real agent
   tonight (Claude Code and Codex) used it correctly from its help and its refusals alone. An MCP server would add typed tools for one vendor and no
   binding power. Revisit if agents start fumbling the commands.
4. **While a plan is in force, work happens inside nodes, and a finished plan stays in force** until
   you archive or pause it. A session that holds no node writes nothing in the repo. *Why:* the first
   real agent run did both nodes properly, waited until no node was open, then made the edit no node
   allowed, and said so ("no node was open. Graphene accepted the write"). With this rule the same
   agent, refused, proposed a node for the edit and asked you to accept it. That is the behaviour
   the product wants: scope creep becomes a proposal you can see.
5. **Agents propose; only a person disposes.** Accepting a proposal, editing a contract, signing
   off, reopening, overruling the gate, pausing, archiving and acknowledging loose changes are a
   person's. A person is someone at a terminal, or the map started from one. Anything without a
   terminal is treated as an agent.
6. **When "done" needs a person, nothing is surprised.** A node that is yours is never handed to an
   agent. A node with a sign-off stops in `review` after its check passes, and what waits on it
   waits. `graphene plan accept` says before the run which nodes agents can reach alone and which
   will wait for whom; an agent that runs out of ready nodes is told it can stop, and `graphene plan`
   shows "waiting on a person" with what is asked of you.
7. **Graphene runs the check, not the executor.** "It passed" is then a fact about the repo, not a
   sentence in an agent's summary.
8. **Only writes are scoped. Reads never are.** A node that depends on another has to read what that
   one did.
9. **Graphene never commits, merges or pushes, and never calls a model itself.** `graphene run`
   starts the executor *you* name, with the permissions *you* give it. The old law "Graphene never
   runs an agent" is replaced by that sentence.
10. **Every hole is printed next to the control it weakens** (README, `docs/HOW_IT_WORKS.md`, the
    map). The known ones are in "What does not bind" below.
11. **The name, the package and PyPI are yours.** I renamed nothing and published nothing (0.2.0 on
    PyPI is yours, from 2026-09-20). The import package is still `graphene_debrief`.
12. **What was demoted.** `graphene why`, the session card, `graphene sessions` and the session map
    stay as commands because they are verified and useful; none of them is the product. The
    guess at "not what you asked for" from prompt text is deleted: scope is a fact of the node now.

## Decisions taken on 2026-09-21 (the tree directive)

Taken by the agent that ran `docs/process/directives/TREE_DIRECTIVE.md`, each with its reason and,
under it, the question I would otherwise have asked. Strike any of them. Where one changes a decision
above, the old one is left as written and the change is named here.

13. **The plan is a tree, and the root is a sentence of yours.** `graphene plan goal '…'` is the
    root: why any of this is being done. A node's `parent` says what it helps achieve; a node with
    children is a **sub-goal** and needs only a title; a node without is a **leaf**, with a scope
    and a check exactly as before. A node from 0.3 has no parent and sits under the root; nothing
    in the store was migrated, a node is a JSON document and gained two fields. *Why a sentence and
    not a root node:* one goal a plan is what the directive describes, and a row nobody can take,
    finish or drop would need an exception in every operation. *Question:* do you want several
    goals in one repo at once? Today that is several sub-goals under one sentence.
14. **Hierarchy is meaning, `needs` is order, and what a sub-goal needs its leaves wait on.** A
    cycle through needs, through the tree, or through both is refused when the plan is edited.
15. **Done rolls up, and a sub-goal's own check is where integration lives.** When the last leaf
    under a sub-goal is done Graphene runs the sub-goal's check, if it has one, in the checkout
    where the leaves' work is together. Failing, the sub-goal stays open, the plan says "its leaves
    are done and its own check fails", what waits on it waits, and the way on is a leaf under it
    for what is missing. A new or reopened child reopens a finished sub-goal.
16. **A proposal is a subtree; you accept at any level.** `graphene plan propose` takes nested
    `children`. Accepting a node accepts the proposals under it, and the proposals it sits under (a
    leaf is never in the plan without its why). A leaf too big to do is split by proposing children
    under it (`--parent`) and handing it back; dropping the children makes it a leaf again, which
    is how a split is undone. Dropping a sub-goal drops what is under it.
17. **Every executor is told the path from the goal to its leaf**, above its contract, as `why:`
    lines, root first: `graphene node start`, `graphene node show`, and the prompt `graphene run`
    hands over are the same words. The person reads the same lines in `graphene plan`.
18. **A request you type into a session is a leaf. This changes decision 4.** With a plan in force
    and no node held, the first write of a turn makes a leaf from your prompt, held by that session.
    You run nothing. If you typed the CLI's flags in the prompt (`--scope 'src/db/**' --check 'make
    test'`), they bind like any
    leaf's; if you did not, it may touch anything, it ends when the turn ends, and its record is
    git's list of what it changed. The scope is never guessed from the prose. No edit, no leaf.
    A session that holds a planned leaf is still held to it. `graphene run`'s executors never get
    one. `graphene plan prompts strict` gives decision 4 back as written. *Why:* the first night's
    numbers: a plan in force cost a second terminal for a one-word fix, and people pause a plan that
    taxes them and never unpause it. What you asked for in your own words is not scope creep; it is
    now on the plan with a record instead of refused. Shown on a real agent:
    `docs/proof/tuesday.sh`. *Question:* is "anything, until the turn ends" too loose a default for
    you? The alternative I can defend is "anything no other open leaf claims".
19. **A plain yes typed into the session accepts. This changes decision 5 in one place.** A short
    prompt that starts with yes / ok / go ahead / accept (80 characters at most, no question mark, no
    "but", "not", "drop" and the like) accepts what that
    session proposed, or the proposals it names, or everything when it says so, as you, and the log
    says "by their prompt in the session". Everything else in decision 5 stands. *The hole:* an
    agent that starts a second agent chooses its prompt. `graphene run` marks its executors so they
    are never read this way; nothing marks an agent your agent starts by hand.
20. **Whoever carries no agent's mark is the person, terminal or not. This changes decision 5's
    last two sentences.** Claude Code, Codex and `graphene run`'s executors mark their shells, and a
    mark outranks everything. No terminal (an editor task, a pipe) no longer turns your `add` into a
    proposal you then cannot accept; the log says "(no terminal)" and that is all the terminal
    decides. *The cost, said plainly:* an agent of a vendor Graphene has never heard of, which sets
    none of the marks, is taken for you. It was refused before. The page's token is still the model
    for the page.
21. **`graphene run --parallel N` commits and merges, on branches of its own. This changes decision
    9 for that one command.** Each ready leaf runs in `.graphene/worktrees/<id>` on `graphene/<id>`.
    A leaf that passes its boundary is committed there by Graphene (your git identity; the message
    is the title, the goal, the why path and `Graphene-Node: <id>`) and merged `--no-ff` into the
    checkout you started the run from. Plain `graphene run` is unchanged and commits nothing.
    Graphene still never pushes and never calls a model. *Why:* work in a worktree can only reach
    your branch as a commit, and a commit a leaf with its why in the message is how `git log` reads
    as the tree. Shown on two real agents at once: `docs/proof/parallel.sh`.
22. **When a merge is not clean, nothing of yours is touched and the leaf waits for you.** Leaves
    whose scopes overlap are never in flight together (the second starts when the first has
    landed, on top of it), and a write outside a scope is refused, so two leaves cannot have
    written one file. What is left is your own work in the way. Then the merge is aborted, the leaf
    stops in `review` with its work on `graphene/<id>`, what needs it waits with it, and you are
    told the two commands: `git merge graphene/<id>`, `graphene node signoff <id>`; or `reopen` it
    to have it done again on top of what is there. An executor is never asked to resolve a conflict.
23. **The live view is a refreshing print: `graphene watch`.** It redraws the lines `graphene plan`
    prints, once a second, with the last few events under them; what waits on you is first. *Why not
    a full-screen interface with keys:* I could verify a print tonight (it is the same function, and
    it is tested) and not a key-driven interface; shaping is done with the commands, which agents
    and you share. `graphene plan` folds finished work once the tree is longer than a dozen lines;
    `--all` unfolds.
24. **The banned-words test is gone**, and deliberate shortcuts in the code are marked `TODO:`.

25. **The session product is cut down to a node's record. This replaces decision 12.** `graphene
    why`, the session card and `graphene sessions` are gone, with `debrief.py` and `why.py` (the
    three files the directive named went from 2,181 lines to 966). A leaf's coverage line is
    computed for any executor from the node's log, git and the check Graphene ran; Claude Code's
    records, where a session held the leaf, add which path traces to a recorded write. *Why cut
    rather than keep:* both commands rested wholly on Claude Code's edit payloads, and could answer
    nothing for Codex, `graphene run --with …` or you. The record rolls up the way done does:
    `graphene node show <sub-goal>` adds up the leaves under it, `graphene plan record` the whole
    plan, and a leaf that could not be counted is named, never counted as zero. *Left for a
    follow-up:* four store methods only the card called (`add_debrief_run`, `last_debrief_run`,
    `recent_paths`, `recorded_path_count`).
26. **On the page, "why" is the path, in a node's detail.** The goal is in the header, the plan is
    an indented outline above the unchanged canvas, a sub-goal shows `n/m done`, and a node's detail
    opens with the same `why:` lines an executor is told. Nothing else on the page changed.

27. **What the closing review changed** (two adversaries, 47 findings, each reproduced twice; the
    reports are in `local/reviews/`, untracked). The ones that changed a decision above: the check
    Graphene runs is never the person (decision 20 had made a test file the person, because pytest
    takes the terminal away); a proposal binds nobody, so a proposed child does not turn the leaf it
    is under into a sub-goal (16); a leaf in a run's own worktree does not answer for what changes in
    your checkout meanwhile, so you can work there during a run (21; this gives up noticing an
    executor that writes into your checkout by absolute path from its worktree, which the hooks
    still refuse when outside its scope); scopes that *could* meet are kept apart, not only scopes
    that share a tracked file (22); a merge of your own in progress is never aborted; a run on a
    detached HEAD, and a second run at once, are refused in words; a killed run's leaves are handed
    back by the next one; you can overrule a sub-goal's check with a reason; and the terminal print
    folds any sub-goal with nothing moving under it, so sixty leaves just accepted are a dozen lines.

## Your answer, 22 September

The question this file asked, whether you would rather shape a tree than type a paragraph, has your
answer, and it is neither. On the 22nd you sat down as the person for the first time: you shaped a
tree, added a leaf of your own, ran two executors at once and watched hand-backs come in. Watching a
leaf come back with a reason taught you what the product is (the boundary is the scope and the
check, not the executor's opinion), and typing the tree was the expensive part. Both stand-in tests
had measured the same mistake: they had the person author the tree. So the paragraph stays the
input, the agent proposes the tree from it, and your job is reading and pruning. The terminal
directive (`docs/process/directives/TERMINAL_DIRECTIVE.md`) is built on that sentence.

## Decisions taken on 2026-09-23 (the terminal directive)

Taken by the agent that ran the terminal directive, each with its reason and, where there is one,
the question I would otherwise have asked. Strike any of them. Where one changes a decision above,
the old one is left as written and the change is named here.

9, amended by the directive in one word: **Graphene starts the planners and executors the person
names, and never holds a key.**

28. **A paragraph typed into a session becomes a tree before any code. This narrows decision 18.**
    When a prompt of 240 characters or more reaches a session that holds no leaf, the hook tells the
    agent, next to the prompt, to propose the tree in the plan's text and stop, and it refuses that
    session a write until a leaf is accepted and taken. A prompt under 240 characters is still
    decision 18's leaf, done at once and recorded. "just do it" in a paragraph skips the tree.
    *Why a rule and not the session's judgement:* I first taught it only at session start ("when the
    person describes work bigger than one change, propose the tree"), ran your paragraph through a
    real session, and it wrote the code in 48 seconds. With the rule at the prompt it proposed four
    leaves with their needs in 35 seconds and touched nothing. *Why length:* your paragraph was 330
    characters and your one-line asks were under 100; a person writes a piece of work as a paragraph
    and a fix as a line. *Question:* is 240 the right line for you, and do you want the rule off in
    some repos (`graphene plan prompts` has leaf and strict; this would be a third)?
29. **The plan has a text form, and it is the floor.** One line a node: `- title  [id]` is in the
    plan, `? title  [id]` is a proposal (make it `-` to accept); indentation is the tree; under a
    node, `scope:` `check:` `needs:` `owner:` `signoff:` and any other line is what it should
    achieve; `#` lines are Graphene's notes. `graphene plan --text` prints it; `graphene plan edit
    [id]` and `graphene node edit <id>` open it in `$EDITOR`; `graphene plan propose -` reads it from
    an agent (JSON is still read). *How a save applies:* as the operations the plan already has (add,
    edit, accept, drop, reorder), in one transaction, and only what the person changed in the text:
    each field is compared with the text as it was opened, so a change someone made meanwhile to a
    node the person did not touch is kept, and one to a node they did touch is refused ("changed by
    someone else"; delete the note and save again to make your change over theirs). *What is refused,
    by its line number:* a line under no node, a line that does not line up with its node's other
    lines, a key written twice or words after the keys in an edited text (what a deleted node line
    leaves behind), a child typed between a node and its own lines, spellings that carry paths or
    commands (`files:`, `tests:`), braces in a glob, a `needs:` that names no node, a new leaf from an
    agent with no scope and no check. Synonyms that say nothing else are read (`depends on:` for
    needs, `sign-off:` for signoff). *Why:* your afternoon's "adding a node was cumbersome" was the
    CLI's flags; a text a person and an agent both write is the fix that works in nvim on day one.
    54 adversarial agents attacked it (49 findings, each re-checked after the fix; a regression test
    each in `tests/test_plan_text_findings.py`).
30. **`graphene watch` is the Textual screen. This changes decision 23.** One screen: the tree and
    the node under the cursor side by side, stacked below 110 columns; the top line says which
    repository and which plan; the bottom two name the planner and the executors and say which
    command the last key ran. `--once` prints. The directive's keys, all of them, each a `graphene`
    command. Two I decided: `?` on a leaf that came back asks the planner (the directive gives `?` to
    both help and that; elsewhere it is help), and `n` is the next search match after a search, else
    the "wait on" offer. `:stop` stops a run started from the screen. *Why Textual works at 80
    columns:* checked in a WezTerm mux at 80x24, reading the screen back.
31. **Planners: `graphene ask` and `graphene node split`.** A planner is started the way `run` starts
    an executor, with the command you name (default: Claude Code with only Read, Grep and Glob); what
    it prints is read as the plan's text and added as its proposals. It is refused a write by the hooks
    and a leaf by `start` (it carries `GRAPHENE_PLANNER`); asking is the person's, because it spends.
    *Why printed text and not a command:* then a planner of any vendor needs no permission but to
    read, and "its only output is a proposal" is true by construction.
32. **A leaf that comes back offers its own fix.** From what it tried to write outside its scope (a
    refused write, a refused `done`, what changed when it was handed back): `w` widens its scope to
    those paths, `b` makes a sibling leaf for them that it then waits on, and `n` makes it wait on the
    nodes its reason names. The sibling's check is `true`: the first leaf's own check, run after it,
    says whether the two work together, which was the question.
33. **The run lets go when told.** Executors start in sessions of their own; Ctrl-C reaches Graphene,
    which hands back every leaf it started (in place and in worktrees) and stops the executors; a
    leaf that passed but had not landed is committed on its branch and waits in review. A leaf the
    person releases or drops stops its executor. A run that died is swept by the next one, by the pid
    it wrote. A leaf whose need is done but not here (never landed, or uncommitted where it was done)
    waits, and says why. `start` asks git before it takes the write lock. The default executor may
    edit files and run `graphene` (its `done` and `release`), and nothing else unless you say so with
    `--with`.
34. **The executor's tail comes from both.** Each attempt's output streams to
    `.graphene/runs/<leaf>-<time>-<n>.txt` (`l` shows it); the hooks' record gives a Claude Code
    executor's last tool call. The age of whichever is newer is "seconds since it did anything".
35. **`graphene plan undo` puts back your last act on the plan's shape** (an edit, an add, a drop, an
    acceptance, a saved text), unless something it touched moved on since; twenty are kept.
36. **A node's check runs with bash** when there is one (people write bash). **A check that names a
    path neither in the repo nor in the leaf's scope is warned about when it is written** (your `n9`
    named `test/test_csvfeed.py`). **Every write names the repository.**
37. **Textual 8.2 is a new dependency** (rich stays at 15). *Why not an extra:* the screen is where the
    first ten minutes happen; one more install step is ceremony.
38. **What I found in my own session.** This repository has Graphene's hooks installed, so the
    paragraph rule ran in the session that was building it: a long background-task notification was
    read as a person's paragraph, and my session was refused writes. Prompts the vendor makes itself
    (task notifications, reminders) are now never the person's. Two of my edits went in before I knew
    the session was held, by scripts the hook cannot read (the hole this file names); once I knew, I
    made none that way, and waited for the next prompt to clear it.
39. **What the closing review and its recheck changed.** Six adversaries over the whole branch, 78
    findings confirmed by a second agent each, all collected before any was fixed (`a384829`); then
    a recheck of every one with a regression test: 46 held, 25 partly, 4 not, 3 only documented, and
    11 regressions the fixes had caused. Those were fixed by three agents in worktrees and me, and
    merged. The ones that change a decision above, each with its reason:
    - *The paragraph's wait (28).* Its tree is what that session, the planner or you proposed
      after it, never another agent's session. A second paragraph while the first waits keeps the
      first one's start. A short answer that says "no plan" lifts it. The refusal says what lifts it.
      *Why:* the recheck found sessions refused for good after a question, and told to "propose it"
      with an accepted tree in front of them.
    - *The run (33).* A dead run is known by pid and start time, and its executor is stopped TERM
      then KILL before the leaf goes back. A closed terminal or a `kill` is a Ctrl-C. A stop ends
      the checks at once, with everything they started; a leaf that had passed and not landed still
      waits in review, and one that had landed stays done. A merge is aborted only if it is the
      run's own. *Why:* a pid recorded days ago can belong to a stranger by now, and a sweep killed
      one in the recheck.
    - *A need done elsewhere (33).* It counts as here when its files were committed after it
      finished, even when the content was edited again before that commit. *Why:* the exact-content
      rule kept a dependant waiting for ever after a formatter touched the file.
    - *Offers (32).* `w` and `b` take exactly the paths they showed. A second `b` for the same paths
      is refused.
    - *Undo (35).* Undoing an edit to a running leaf leaves its holder alone. Only an act that let
      the executor go is undone into `open`.
    - *The goal.* An agent's proposed sentence may replace a goal only when nothing under that goal
      is left to do. It then sets the old goal aside (its text stays in the log) until you accept or
      decline the new one; if you decline, the plan has no goal. *Question:* is setting it aside
      right, or should a finished goal stay until you replace it?
    - *The terminal mark (20).* What you type in `graphene watch` is logged as typed at a terminal
      (`GRAPHENE_WATCH`). The hook refuses that variable in an agent's command, as it refuses
      `GRAPHENE_AS`.
    - *A visual `d`* is one act: all of the selection or none, and one `u` puts it back.
    Still open, by choice: a need committed on another branch of the same checkout still counts as
    here after a branch switch; a held node's committed stray edit is excused when a landing merges
    into the same file; and some phrases said in passing still skip the tree.
40. **The hold, and what it showed.** At 09:15Z a subagent's report reached this session as a
    prompt, and the hook read it as your paragraph. Every agent I started carries this session's id,
    so for an hour nothing could write. I did not route around it: no writes the hook could not read,
    no clone to write from, nothing in the store. What was committed before the hold was pushed.
    Another report, which quoted "just do it", lifted the wait for a few minutes, in your name. I
    wrote nothing in that window, and I would not have counted it as yours. You lifted the hold
    with "just do it". The harness's report prompt is now the vendor's (`_NOT_A_PROMPT`), so it can
    neither arm the wait nor speak for you. *What it says about the product:* a wait armed by
    mistake has one way out, and that way is you. That is the promise working. A command to lift a
    session's wait from outside it (from `watch`) would have cost you less than resuming this
    session; it is not built.

## Decisions taken on 2026-09-24 (the polish directive)

Taken by the agent that ran `docs/process/directives/POLISH_DIRECTIVE.md`, which added no mechanism
and judged everything at the screen: the feeds task built by `docs/proof/try.sh`, a real Claude Code
session and real executors, `graphene watch` driven by keys in a WezTerm mux at 80×24 and 120×36.
Each decision has its reason. Strike any of them. Where one changes a decision above, the old one is
left as written and the change is named here.

41. **One row grammar, everywhere: the title, then the id, then one word for the state.** `○ an xml
    reader  xml-reader  ready`, in fixed columns (ids under ids, words under words, at any depth; a
    title is cut at a word with an ellipsis; nothing scrolls sideways, and an id is never cut). The
    same row on the screen, in `graphene plan`, and in what `node add`, `propose` and `accept` print;
    the text form's `#` notes say the same words. *Why the id after the title:* a person reads what
    a node is, and the id is a handle for commands; the text form already writes `- title  [id]`.
42. **One word and one colour per state, and the colour says whose move it is** (`plan.reads`,
    `plan.look`): proposed (cyan: the agent's guess, yours to prune), ready (plain: an agent can take
    it), waiting (dim), running (yellow: an executor is on it), came back, review and yours (magenta:
    it waits on you), done (green), to fill in (a node with no leaves and no scope yet: dim). A
    sub-goal reads `2/3 done`. Red is only the mark of a command that failed. *Why:* a leaf that came
    back is the loop working, and it was the only red thing on the screen.
43. **The goal is the tree's first row**, folded like any node, and its pane is the overview. The
    top line says only `the plan of ~/repo`, the words every write's last line ends with.
44. **The status line: first the plan, then the moment.** Line one: what waits on you, how many
    executors run, what `R` would start, how much is done, and plan first on or off; a short form at
    80 columns, whole pieces dropped from the end, never a word cut. Line two: what the last command
    said, else what the keys do on the row under the cursor. *Why the planner is no longer named
    there:* it named whichever session last proposed (`planner: claude:59409a10`); who proposed a
    node is in its pane, in words (`proposed by a Claude Code session (59409a10)`), and the help
    names the two agents.
45. **The record (Enter) is laid out, not pasted**: contract, why it came back, each hold (who,
    when, how it ended, where, what changed in and outside its scope), the check Graphene ran, what
    was refused, coverage, what people did; one line when nothing has happened yet. It says that it
    scrolls; the keys are on the status line.
46. **Plan first is a mode, not a reading of your words. This replaces decision 28's rule, and
    withdraws decision 19.** `graphene plan first on|off`, `P` in the screen, shown on the status
    line; never set, it is on while a plan is in force, and `graphene init` sets it on. On, a
    session that holds no leaf proposes before it writes; one leaf it proposes after your prompt is
    yours at once (the one-line ask stays free: 25 seconds, nothing to press, on 24 September), and a
    tree waits for you. *Why:* the directive's rule that nothing reads your prose for length or for
    magic words, anywhere; the 240 characters were a heuristic about how you write, and they caused
    the hold of decision 40. *What it gives up:* decision 19's "a plain yes typed into the session
    accepts" read your words, so it is gone; you accept with `y` in the screen. *Question:* this
    repository was set up before the mode and has no plan in force, so plan first is off here; is
    "on while a plan is in force" the default you meant, or on everywhere Graphene is installed?
47. **`ack` means: the uncommitted changes in the checkout are yours, as they stand.** A commit is
    the repository moving (your `.gitignore`, a `git pull`), and the plan follows it: only
    uncommitted changes no leaf made are loose. Committing them does what `ack` does. *The hole it
    opens,* written down and not guarded: an agent that writes outside every leaf between leaves and
    commits it is not seen at the next start.
48. **What the check creates is not the executor's change.** At `done`, when the only strays are new
    untracked files, they are set aside while the check runs; what it makes again (the `__pycache__`
    of an executor's own test run, in a repository with no `.gitignore`) stays, is not counted, and
    is not committed with the leaf. This is a small mechanism, and the directive asks for the real
    fix to be named: run the check in a clean copy of the leaf's own commit (a worktree), so nothing
    it writes ever lands in the executor's tree. *Its hole:* an untracked file of yours that the
    executor deleted outside its scope is not caught (a tracked one is).
49. **The text form reads every key or refuses it by its line.** `parent: <id>` places the node
    under that one (it was read as the node's goal, and the node landed at the root); `id:` is the
    node's id; `title:` and `children:` are refused (the title is the line, children are
    indentation).
50. **A person's own leaf with no scope is a to-do**, not "a sub-goal with no leaves yet": `y` in the
    screen (`graphene node done`) finishes it on your word, and `start` says it is yours to do by
    hand. An agent's node with no scope and no leaves is "to fill in": `s` asks the planner, `e` gives
    it a scope and a check.
51. **Refusals are one shape and said once**: what was refused and why, the paths, one or two
    commands; the explanation the first time a caller meets it in a hold, a short line after
    (`plan.refusal`, `plan.first_time`; the hook's scope lecture too). `next:` is one line. A command
    never tells you to run itself. `reopen` and `release` ask for their note at a terminal; a
    missing option anywhere is one line, not a usage box.
52. **What sitting in it found that the tests did not**, each now with a test that fails without its
    fix: keys typed in one burst after `:`, `/`, `a`, `A` or `x` ran as commands on the tree (a
    terminal delivers them before a binding's action runs; the headless pilot pressed them one at a
    time and hid it); a leaf that passed and did not land was signed off mid-merge, conflict open,
    and read as landed; two screens starting at once on a new store crashed on `database is locked`;
    `:ask add a --dry-run flag` took the flag for ask's own option; the offers lost their commands at
    120 columns; `graphene watch` spawned by a harness as a person ran with the agent's marks.

## Decisions taken on 2026-09-25 (the Nemotron directive)

Taken by the agent that ran `docs/process/directives/NEMOTRON_DIRECTIVE.md`, each with its evidence.
Strike any of them. Where one changes a decision above, the old one is left as written and the
change is named here.

53. **The import package is `graphene_map`, matching the distribution. This changes decision 11's
    last sentence.** Not `graphene`: that import name belongs to the GraphQL library on PyPI, and a
    person with both installed gets whichever wins. The command stays `graphene`, so hooks already
    installed (`graphene ingest hook`) keep working. Dated records (`docs/test/results-*`,
    `docs/test/findings/`, the diary in `docs/process/`) keep the old name, because they describe
    what was there then.
54. **Graphene calls a model when you name its Nemotron planner or executor. This changes decision 9,
    as amended on 23 September.** `--with nemotron` is Graphene's own code calling Nebius Token Factory
    with your `NEBIUS_API_KEY`. The key is read from the environment at each call and written nowhere:
    not in the store, a log, the ledger, a recording or a sandbox. What leaves the machine is the
    prompts about the repository, the files the model asks to read, and, in a sandbox, the leaf's
    checkout. Claude Code and Codex are started exactly as before. *Why:* the directive makes Nemotron
    how Graphene works, and a planner or executor that is Graphene's own code is the only way to hold it
    before the write (55). *Evidence:* `tests/test_executor.py` shows a command the model runs has
    `GRAPHENE_NODE` in its environment and no key. `tests/test_tokenfactory.py` shows the ledger and a
    recording hold no key.
55. **The placement is "the loop here, the tools there."** Graphene's loop runs on this machine and
    calls Token Factory. Every tool call runs in the leaf's placement: its checkout, or a Token Factory
    Sandbox. *Why, with the evidence:*
    - Only a loop of ours can refuse a write before it happens. The edit and write tools do
      (`gate.scope_refused`, the hook's own words, not a copy).
    - The refusal is logged where the hand-back's offers are read from, so a leaf that comes back
      offers `w` for exactly the path it was refused (`tests/test_executor.py`).
    - The key never enters the machine where model-written code runs.
    - In the Docker stand-in, a command took 1.3 to 2.3 s and making the sandbox 7.5 s
      (`tests/test_escape.py`'s log).
    - ConTree's own latencies, and any number with a real model, are not measured: this shell had no
      key.
    The other placement, a harness such as OpenCode inside the sandbox, is spiked in
    `docs/test/spikes/harness_there/`; its numbers are there.
56. **No model id is written into Graphene: the live list names them.** `tokenfactory.roles` picks the
    Nemotron Ultra, Super and Nano out of `GET /v1/models` by name, the newest of each, a `-fast` twin
    second. The executor's default is the smallest listed, the planner's the largest. `graphene init`
    writes the ids it saw into the repo's config, so a run can be repeated. *Evidence:* none from the
    live list tonight (no key). The picking is tested on a list shaped like the documented one.
57. **Layer 2 is directory-grained, and what it cannot stop never comes back.** In a sandbox the
    leaf's user owns the scope's files and whole-scope directories. In a directory where the scope
    names a file it may create files (sticky bit), and nowhere else. POSIX grants "may create" per
    directory, not per name. So a command there can make a file the scope does not name: it is never
    brought back to the checkout, it is logged as a breach and removed before the next command, and the
    check, which runs from the checkout, never sees it. *Evidence:* `tests/test_escape.py`. A redirect,
    `sed -i`, `python open(w)`, `mv`, `rm`, git, a symlink over the file and `chmod` all exit non-zero.
    A new `tests/conftest.py` and a link out are made, refused and never brought back. Every in-scope
    write succeeds.
58. **The bill is Token Factory's own usage at its list price.** Each call's `usage`, priced by the
    `pricing` the verbose model list gives, goes into a `usage` row per attempt in the leaf's record,
    per planner call in the plan's log, and into a ledger when one is named. The ledger's cap refuses
    the next call at 100%, before it is sent.
59. **The ConTree SDK is pinned at 0.3.6, and ConTree is spoken to in one class.** The docs' Getting
    Started describes an SDK that takes a `contree_client` client. No release does that: 0.3.6 and
    0.4.0.dev5 both take a config or a token. 0.4.0.dev5 also needs `contree-client~=0.2` where the CLI
    needs `~=0.4`. `tests/test_sandbox_contract.py` binds every call Graphene makes to the pinned
    SDK's signatures.
60. **A leaf can be forked: N conversations from one checkpoint, and the check picks** (`--forks N`).
    The first fork whose check passes is copied in, what its scope covers and nothing else, and
    Graphene's own `done` decides. When every fork gives up, the leaf comes back with every path they
    wanted. *Why:* the directive's thesis is "fork it again, or step up a size, and let the check
    decide." `--model` given twice is the step up. Whether forks pay for themselves is a number for the
    benchmark, not tonight.

## What does not bind (say it wherever you sell it)

- A shell command can write a file in a way nothing reads beforehand (a script that opens files
  itself). The hook refuses the forms it can parse (`>`, `>>`, `tee`, `sed -i`, `mv`, `cp`, `rm`);
  the rest is caught only at `done`, by git. Until then the stray change is on disk.
- A file created outside the scope and moved out of the repo before `done` is invisible to git. It
  is caught when it comes back, at the next start, as a change no node owned.
- Claude Code lets a session end after about 8 refused stops in a row. The node then stays
  `running` on the plan, which is how you see it. `graphene run` has no such ceiling.
- A hook that crashes or times out lets the call through (the vendor's rule). The boundary holds
  without it.
- "A person" rests on the environment. Inside an agent's shell `GRAPHENE_AS` changes nothing; an agent
  that first strips its own markers and then sets it passes for a person, and the log marks the act
  "(no terminal)". No command line can do better than that.
- The plan's store is a file in the repo that git ignores: a script that opens it directly is
  neither stopped nor noticed. What git ignores, nobody audits.
- `graphene run` works in one checkout, one node at a time. Two agents at once in one checkout are
  kept off each other's paths by scope; they are not isolated from each other's half-written files.
  (`graphene run --parallel N` gives each leaf a worktree of its own: decision 21.)
- A prompt is taken as yours (decisions 18 and 19). An agent that starts another agent writes its
  prompt. The log names every acceptance made "by their prompt", and every leaf made from one.
- A leaf made from a prompt with no `--scope` may touch anything but the plan's store and the hooks'
  settings; it is a record, not a fence. Its record lists what changed in the checkout during the
  turn, which includes what you changed by hand meanwhile.
- Both rest on the vendor being the only caller of the hook. An agent that pipes a hand-written
  event into `graphene ingest hook` is refused by the ordinary spelling and not by a determined one.
  Found by the closing review, which did it; the acts are logged "(no terminal) … by their prompt".
- Every request that became a leaf is on the plan in your words, and `graphene ui --export` carries
  the plan.
- Whoever carries no agent's mark is taken for you (decision 20).
- While a parallel run is going, a commit of your own on the branch it merges into can make a leaf
  in another worktree look as if it changed your files, and its `done` is refused. It is sent back,
  and says so; nothing is lost. Work in the same checkout through a session (a leaf made from your
  prompt answers for it), or let the run finish.
- With plan first on (decision 46) the agent judges what is a tree and what is one leaf; one leaf
  it proposes after your prompt is accepted as yours, and the log says so.
- A commit is the repository moving (decision 47): an agent that commits what it wrote outside every
  leaf, between leaves, is not seen at the next start.
- The Nemotron executor in the local placement is held before the write by its tools only. A command
  it runs can write anywhere your user can, and is caught at `done`, by git. In a sandbox a command
  can make a new file in a directory where the scope names a file; it never reaches your checkout
  (decision 57).
- With Nemotron named, the prompts about your repository and the files the model reads go to Token
  Factory, and in a sandbox the leaf's checkout goes to Sandboxes (decision 54).
- The planner of `graphene ask` has read-only tools because you (or the default) named them. A planner
  started with tools that write is held by the hooks (Claude Code) and by `start`, and not otherwise.

## What comes next, in the order I would do it

1. You run the test (`docs/test/PROTOCOL.md`, ten minutes) on a task of your own. Everything below
   waits on whether you would rather shape a plan than type a paragraph.
2. The recording: you shaping a plan in the map, an agent doing one node and stopping at the
   boundary, you changing the next node. `docs/proof/proof.sh` is that scene in a terminal.
3. The same hooks for Codex. Its hook JSON has the same shape as Claude Code's (checked against its
   docs on 2026-09-20), so `graphene init --codex` is mostly a settings file.
4. A worktree per node in `graphene run`, then nodes in parallel. It buys isolation: refused work
   never reaches your branch. It costs branches, merges and conflicts the person has to understand.
5. The vendor's sandbox as a third layer for scope when it is on: the only thing that stops a
   script from opening a file itself.

## What comes next, from 23 September

1. You run the ten minutes: `docs/proof/try.sh`, the two panes, your own paragraph. What you feel at
   the prune is the thing the third test can only model.
2. The page gets the tree's prune and run, from the same commands (`y`, `d`, `R` are commands).
3. Codex hooks, then the vendor's sandbox as a third layer for scope, as before.
4. The planner told the run what it could not settle ("the legacy importer skips the zero rule");
   those lines could be nodes of their own (owner: you), not prose in the session.

## What comes next, from 24 September

1. You sit in it for ten minutes: `docs/proof/try.sh`, the two panes, your own paragraph, at the
   width your WezTerm really is. This run's judge was an agent's eye through a mux; yours outranks it.
2. The page gets the screen's row grammar and palette, then the tree's prune and run.
3. The check in a clean worktree of the leaf's commit (decision 48's real fix).
4. Codex hooks, then the vendor's sandbox as a third layer for scope, as before.

## How this file is used

An agent starting work here reads this file first, then `docs/HOW_IT_WORKS.md`. Where this file and
a directive disagree, this file wins, because it is the one you edit. Where the agent disagrees
with you, it says so in writing, with evidence, in `docs/process/morning.md`, and then does what
you decided.
