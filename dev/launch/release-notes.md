# Graphene 0.8.0

Install: `uv tool install graphene-map` (over 0.6.0, `uv tool upgrade graphene-map`), or `uv tool install
'graphene-map[nemotron]'` for the Nemotron path. Or try it with nothing installed: `uvx graphene-map demo --auto`,
a scripted replay of auto mode on Nemotron (no key, nothing written to your project); `uvx graphene-map demo` is
the older one, a run you steer by hand.

0.7.0 was tagged but never published (its tag built 0.6.0 again): everything it had ships here.

## What you get that 0.6.0 did not have

- **Auto mode.** `graphene auto "<goal>" --budget 2 --forks 3 --check "python3 -m pytest -q"`: the planner drafts
  the goal as tasks that can run at once, Graphene accepts what fits your envelope, runs it with forks, lands
  what passes, then runs the goal's own check; when that is red it plans the fix, at most `--rounds` times,
  inside the budget. Ctrl-C stops it, `graphene auto` with no goal goes on, and `graphene plan log` keeps every
  round.
- **The envelope is your settings.** `auto`, `budget`, `tasks` and `rounds` beside `protected`, `readonly`,
  `forks` and `review`, in `graphene config edit` or one at a time with `graphene config set auto on`. While auto
  is on, a plan that fits is accepted at once, from `graphene ask` or from any agent's own proposal, so three
  Claude Code sessions do not wait on you to click; a task that could reach the agents' own settings and hooks
  never fits; and every run counts against the budget. Only you can set it.
- **Fork a task.** `graphene run --forks 3` puts three agents on each task at once, each in its own copy and held
  to the task's files; `--with claude:opus --with claude:sonnet --with codex` gives each fork its own agent.
  Among the forks whose check passed, a rule written before any fork ran keeps one: the most of the other forks'
  tests passed, then the check's own files left alone, the smallest, the cheapest, the first. It says why in one
  line, lands that fork alone, and keeps every fork on a ref (`graphene node diff <task> --fork b`).
- **The race on screen.** Every agent's row names its model (Nano, Super, Ultra, Haiku, Sonnet, Codex), each fork
  its own line with its dollars, the auto line its round, stage and budget; on the graph, `+` adds a step after
  a task and `L` links two (`graphene node set B --add-needs A`), and its head says how many can run at once.
- **Graphene for VS Code.** `editors/vscode`: the plan as a graph in an editor tab and the sidebar, forks racing,
  the status bar, and every click a `graphene` command run as you (add a step, link, edit, drop, accept, tell an
  agent, Auto…). It reads `graphene state --json`, one snapshot of everything the cockpit shows.
- **Any model behind Graphene's own loop.** `graphene run --with 'nemotron --endpoint nim'` runs the same
  Nemotron loop on NVIDIA's API catalog, and `--endpoint ollama` or `--endpoint openai` on any OpenAI-compatible
  host, writes still refused before they happen; `{prompt}` and `{prompt_file}` let any CLI agent take the task.
- **A port a task.** Every agent a run starts gets `PORT`, its own, said in its contract and given to its check.
- **The graph flows into your goal, and the gate fails closed.** `g` draws the goal as the last box; on Claude
  Code 2.1.295 or later a hook that cannot run refuses the call, and the hook reads more of the shell before a
  write.

## What it does not do

- A write outside a task's files is refused before it happens by Claude Code's hooks and by Nemotron's edit and
  write; with Codex, any other CLI agent, or a write the hook cannot read (a target in a variable it was not
  given, a glob, a script that opens a file itself), git finds it when the task says it is done.
- Auto mode ran end to end against a scripted stand-in of Token Factory, not yet live; the envelope decides what
  is accepted, not whether the work is good, which is the checks' job.
- Nemotron bills each call after it ends, so auto mode reads the budget between rounds; Codex has no cap of its
  own, and `--max-usd` stops starts, not an attempt that is going.
- The rule keeps one fork by the check and a few counts; it does not read the code, and `graphene node pick` is
  yours when you disagree. Whether forks land more tasks is not measured yet.
- A task allowed to edit the test its own check runs can weaken it: it is flagged, not refused.
- The VS Code extension is built and tested here, not yet on the Marketplace: `npm run package` in
  `editors/vscode` makes the `.vsix`.
