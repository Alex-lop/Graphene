# A three-minute video for the hackathon: one goal, a race on every task, the fix

A pitch, not a tutorial: the judges may score from the video alone, and the aha has to come by 0:30. Everything on
screen is either a command anyone can run for free (`graphene demo --auto`, `graphene demo --cheat`) or your own
live take (`dev/proof/auto.sh`, which spends on your Token Factory key). Say "Nemotron" and "Token Factory" out
loud; say which model does what. Narrate in your own words; the SAY lines are a draft. Record from the released
0.8.0 wheel so the words match (`uvx graphene-map@0.8.0 …`).

1. **0:00 to 0:20, the problem** (`beat1-problem`)**.** Your face or a plain slide. SAY: "Yesterday I ran three coding agents on one repo
   by hand: one reviewing, two building, each told which folder was theirs. It worked until it didn't: one agent's
   dev server restarted on every save the other made. Telling agents where they may write is a prompt. I wanted it
   to be a rule."
2. **0:20 to 0:35, the aha** (`beat2-aha`)**.** Type `graphene demo --auto --speed 4`. The goal at the top, Nemotron 3 Ultra's three
   tasks, then nine agents at once. Pause on the race (`space`). SAY: "One goal in. Nemotron 3 Ultra plans it as
   tasks that can run at once, each owning its files. Three Nemotron 3 Nano agents race every task. This one tried
   to write a file that isn't its task's: refused, before the write."
3. **0:35 to 1:15, the check decides, then the goal** (`beat3-check`)**.** Play on (`space`). Each task keeps one fork; all three land;
   the auto line turns to `fixing: FAIL: test_a_hyphen_splits_a_word`. SAY: "No model picks the winner: the tests
   do. The fork that passes the others' tests, then the smallest, the cheapest. All three tasks pass on their own,
   and then my whole test suite fails: the hyphen task broke an old test nobody owned. Graphene catches it because
   it checks the goal, not just the tasks, and Ultra plans the fix. It races, it lands, the suite is green."
4. **1:15 to 1:45, it was real** (`beat4-real`)**.** Your live take of `dev/proof/auto.sh` (or `graphene demo` on its recording), on
   Token Factory: the bill at the end. SAY: "That was the replay. This is the same thing live on Token Factory:
   Ultra planning, Nano racing, Super on a retry, and every call priced, so every task has its own bill. Racing
   three small models costs cents, and the rules are what make a cheap model safe to spend in bulk."
5. **1:45 to 2:10, the locks** (`beat5-locks`)**.** Type `graphene demo --cheat`. SAY: "And when an agent tries to get round the locks:
   six refused, one flagged, none through."
6. **2:10 to 2:35, where you work** (`beat6-editor`)**.** VS Code with the extension: the graph, forks fanning out, the details pane;
   drag one task's dot onto another to link them; then the Explorer, each file a running agent writes marked with
   its number. SAY: "The same plan in VS Code. Every click is a Graphene command run as me, and you can see which
   agent owns which files. I set the envelope once (a budget, how many tasks, the files no agent may touch) and
   it does the rest."
7. **2:35 to 3:00, why** (`beat7-why`)**.** SAY your "Why I built this", in your words: the limit on software won't be tokens; it's
   the direction a person gives. Then the README's first line: `uvx graphene-map demo --auto`.

Things to keep true while filming: the replay's dollars are the stand-in's prices, so don't read them out as
Token Factory's; say the live take's bill instead. Don't say unattended runs are safe (`claims.md`): say the
envelope decides what is accepted, and the tests decide what lands.
