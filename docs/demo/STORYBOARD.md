# The video: three minutes, the moment before anything runs

A draft for Alex. The rules ask for a public video of three minutes or less whose audio covers how
Token Factory and Nemotron are used. So the narration says what runs where, and nothing about why
software should be written this way. Everything on screen is `docs/proof/nemotron.sh`, run for real on
the feeds repository and cut only where an agent is thinking. The terminal parts can be rendered from
`docs/proof/nemotron.tape` with VHS.

The first minute and a half is shaping: the board, the graph and the prune, before anything is spent.
That is where Graphene differs from the rest of the field (`docs/process/field.md`, "Where Graphene
differs", item 1). The run, the forks and the bill come after it and are shorter, because forking
from one checkpoint is the field's most common pattern (item 3 there).

<!-- For Alex: the board, the tree and graph views, `?` talk, `graphene config` and the Nemotron
shaping commands are merged into `shaping` (at 2111115), not yet into `main`.
docs/proof/nemotron.sh and nemotron.tape do not yet show the board or press Tab; the tape needs the
new keys before this can be recorded. -->

| Time | On screen | Narration |
| --- | --- | --- |
| 0:00–0:10 | Two panes, each 80x24: a terminal on the left, `graphene watch` on the right, empty. The left pane shows `graphene config`: the protected paths, the plan's size, the planner and the executor, and where the key was found (never the key). | "This is Graphene, on a small Python repository. I said once what no agent may touch. Now I'll ask for a feature in a paragraph, and NVIDIA Nemotron models will plan it and build it on Nebius Token Factory." |
| 0:10–0:30 | The paragraph typed into `graphene ask`. The right pane fills with a tree, every row `?`. The left pane lists `proposed …` lines, then `put up …` lines. | "The planner is Nemotron 3 Ultra, called through Token Factory's OpenAI-compatible API. It reads the repository with read-only tools (list, grep, read) and answers with a tree: sub-goals, and leaves that each name the files they may change and the command that proves them done. What the code can't tell it, it asks." |
| 0:30–0:55 | **The board** (frames B1 to B3 below). `graphene board`; then `graphene board pick parser 1`, `take cents`, `take no-zero`, `park json-variant`. The right pane gains a leaf; the left pane shows `node show` with its `decided:` lines. | "Before anything runs, the planner asks instead of guessing: at most three questions or risks, each with a default, and only what changes the tree. I answer each with one command. Picking lxml widens the reader's scope, as my edit. Taking the risk's default adds a leaf. What I take or pick goes to that leaf's executor, as a decided line; what I park is told to no one." |
| 0:55–1:15 | **The graph** (frames G1 and G2 below). `Tab` in the right pane: the tree. `Tab` again: the graph, the critical path heavy, and its note on the bottom line. | "Tab draws the same plan as a tree, and again as a graph of what waits on what. The heavy line is the critical path: the chain the rest waits on." |
| 1:15–1:30 | `j` to a leaf, `?`, then `w`: the planner's why lands on the board. *Only if this ran live on the recording night; if not, cut it and give the time to the run.* | "I can talk to the plan: question mark on a leaf asks the planner why it's there, and the answer lands on the board for me to keep or drop." |
| 1:30–1:40 | `Enter` on a leaf shows its scope and check; `E` opens the plan in the editor and a path leaves a scope; `y` on the goal accepts. | "Then I prune. I take one path out of this leaf's scope, and accept the rest." |
| 1:40–2:10 | `R`. Leaves turn yellow at once; the node pane shows the executor, its sandbox, its last step and seconds since. | "R runs every ready leaf. Each gets a Nemotron Nano executor on Token Factory, and every tool call it makes runs in a Token Factory Sandbox forked from one checkpoint of the repository. Its write tools refuse a path outside the scope, the sandbox refuses it too, and the leaf is done only when Graphene's own check passes." |
| 2:10–2:25 | A leaf comes back, magenta: its reason, and `w  widen …` / `b  a sibling …`. `w`, then `R`. | "This leaf needed the file I took away. It comes back with the reason and the fix already written. One key widens its scope, and it runs again." |
| 2:25–2:40 | Every row green. The left pane: `git log --graph --oneline`, one merge per leaf. | "Every leaf landed as a merge on my branch, with its reason in the message, so git's history reads as the tree." |
| 2:40–2:55 | The bill: dollars per leaf and for the run, at Token Factory's list price, from the usage each call returned. | "Each call's token usage comes back from Token Factory, priced at the list price: this is what each leaf cost, and the run." |
| 2:55–3:00 | The repository's URL. | "Graphene, on GitHub." |

## The board and the graph, frame by frame

What the viewer sees at 80x24 in each pane, and the keys pressed. B1 to B3 were rendered at `integ`
50f12e7 (since merged into `shaping`), and G1 and G2 at `shaping` 2111115, from a scratch repository, with a scripted planner standing in for Nemotron
(`graphene ask --with`), a person set by `GRAPHENE_AS=person:alex`, and no model called. The
recording's words will be whatever Ultra puts up that night; the layout, the commands and the keys
are these. The path on each screen's first line is shortened, and in G1 and G2 the empty rows of
the lower pane are shown as `…`.

<!-- For Alex: these frames were rendered before the rows board merged (decision 84), so
they answer the board in the left pane. `graphene watch` now shows each item as a row under the goal
and counts the open ones on its status line ("+ N on the board"): shoot B1 and B2 in the right pane
with its keys instead (y takes the default, 1 picks option 1, p parks, d drops, Enter answers). -->

**B1, 0:30. Left pane, typed: `graphene board` Enter.**

```
$ graphene board
the board: 4 open
questions
  ◇ which XML parser: the standard library or     parser        open
    lxml?
      default: the standard library's ElementTree; lxml is not installed
      1: lxml, added to pyproject.toml
         then: scope xml-reader + pyproject.toml
      about xml-reader
assumptions
  ◇ prices in the XML are already in cents        cents         open
risks
  ◇ samples/ has no XML with a price of 0, so     no-zero       open
    the check cannot see the skip
      default: add one to the sample
         then: leaf "a zero-price product in samples/prices.xml" under xml
left out
  ◇ the JSON variant of the Northwind feed; the   json-variant  open
    paragraph does not name it
graphene board take|drop|park|unpark ID · pick ID N · answer ID TEXT · note TEXT
```

Hold on this frame for about four seconds: this is the moment the video is about.

**B2, 0:38. Left pane, typed: `graphene board pick parser 1` Enter, `graphene board take cents`
Enter, `graphene board take no-zero` Enter, `graphene board park json-variant` Enter.** Each prints
what it changed (each command's last line, naming the plan's repository, is left out here, and a
line wider than 80 columns wraps in the pane):

```
picked parser: which XML parser: the standard library or lxml? → lxml, added to pyproject.toml
  changed: xml-reader: scope + pyproject.toml
taken cents: prices in the XML are already in cents
taken no-zero: samples/ has no XML with a price of 0, so the check cannot see the skip → add one to the sample
  changed: proposed zero-price-product under xml
parked json-variant: the JSON variant of the Northwind feed; the paragraph does not name it
```

The right pane (`graphene watch`, which reads the plan again every second) gains the new leaf at
the bottom of the tree:

```
 the plan of …
▼ ? the Northwind XML feed loads the way csv and json already do       proposed
└ ▼ ? Northwind XML loads like csv and json        xml                 proposed
  ├   ? an XML reader that returns rows            xml-reader          proposed
  ├   ? wire xml into the load command             xml-wire            proposed
  ├   ? a price of 0 is skipped for every source   zero-rule           proposed
  ├   ? a test that loads samples/prices.xml end…  xml-e2e             proposed
  └   ? a zero-price product in…                   zero-price-product  proposed
```

**B3, 0:48. Left pane, typed: `graphene node show xml-reader` Enter.** What the reader's executor
will be told:

```
xml-reader (revision 2): an XML reader that returns rows
  why:    Northwind XML loads like csv and json (xml)
  goal:   an XML reader that returns rows
  decided:
          which XML parser: the standard library or lxml? → lxml, added to pyproject.toml
          assumed: prices in the XML are already in cents
          risk: samples/ has no XML with a price of 0, so the check cannot see the skip → add one to the sample
  scope:  feed.py, pyproject.toml   (a write anywhere else is refused, and blocks `done`)
```

(The line for the risk is wider than 80 columns and wraps in the pane.)

**G1, 0:55. Right pane, key: `Tab`.** The tree, top-down; `←1` and `←2` count what each leaf still
waits on. The bottom line names the command and the note (G1 and G2 rendered again at `shaping`
2111115, with the same scratch plan and board answers):

```
 the plan of …
      the Northwind XML feed loads the way csv and json already do
                                    │
                                  ? xml
                  Northwind XML loads like csv and json
      ┌─────────────┬──────────────┬┴────────────┬─────────────────┐
? xml-reader  ? xml-wire ←1   ? zero-rule  ? xml-e2e ←2  ? zero-price-product
   an XML…      wire xml…     a price of…  a test that…      a zero-price…
────────────────────────────────────────────────────────────────────────────────
 the Northwind XML feed loads the way csv and json already do
 the goal · proposed with the tree: accepting any of it accepts it
 …
 ? Northwind XML loads like csv and json                         xml  proposed
 …
 waiting  xml is proposed, for you to accept or prune
 …
 you: 1 · 0 running · none ready · 0/0 done · plan first: on
 y accept it all · E edit the plan as text · Tab view · ? help · q quit
 graphene watch --view tree: 1 sub-goal · 5 leaves · 6 proposed
```

**G2, 1:05. Right pane, key: `Tab` again.** The graph: each leaf's column is the longest chain of
needs before it, and the critical path is drawn heavy (`━`):

```
 the plan of …
the Northwind XML feed loads the way csv and json already do
? xml-reader an XML reader… ━━━━▸ ? xml-wire wire xml… ━┓
? zero-rule a price of 0 is… ───────────────────────────┨
                                                        ┗━▸ ? xml-e2e a test…
? zero-price-product a…
────────────────────────────────────────────────────────────────────────────────
 the Northwind XML feed loads the way csv and json already do
 the goal · proposed with the tree: accepting any of it accepts it
 …
 ? Northwind XML loads like csv and json                         xml  proposed
 …
 waiting  xml is proposed, for you to accept or prune
 …
 you: 1 · 0 running · none ready · 0/0 done · plan first: on
 y accept it all · E edit the plan as text · Tab view · ? help · q quit
 graphene watch --view dag: critical ━ xml-reader > xml-wire > xml-e2e (3)…
```

A third `Tab` goes back to the outline. At 80 columns the bottom line keeps only the critical path;
`graphene plan --view dag --width 80` prints the whole note, which ends
`critical ━ xml-reader > xml-wire > xml-e2e (3) · none ready · 2 once accepted · 3 wait` here, and
`… · 2 wait` before the board's new leaf.
<!-- For Alex: after the board's new leaf, the note counts zero-price-product among
"3 wait", though it waits on nothing; it has no scope or check yet, which may be why. Worth a look
before it is on camera. -->

## What must be true before recording

- The demo run is live, with the frozen configuration, and every number on screen comes from that
  run. The numbers in the narration are read off the screen, never written in advance, and the model
  named for the executors is the one the frozen configuration uses (Nano, Super, or Nano then Super).
- The board and the questions on it are Nemotron's, from that run: the frames above show the layout,
  not the words.
- The board, the views, `?` talk and `graphene config` are on `main`, and `docs/proof/nemotron.sh`
  and its tape show the board and press `Tab`.
- Nemotron's shaping prototypes (`graphene plan cover`, `note`, `precheck`) and `?` talk appear only
  if they ran live in that recording. Until then they are not on camera.
- Nothing recorded in the Docker stand-in is shown or described as a Token Factory Sandbox.
