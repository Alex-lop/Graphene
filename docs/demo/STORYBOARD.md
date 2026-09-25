# The video: three minutes, the loop on screen

A draft for Alex. The rules ask for a public video of three minutes or less whose audio covers how
Token Factory and Nemotron are used. So the narration says what runs where, and nothing about why
software should be written this way. Everything on screen is `docs/proof/nemotron.sh`, run for real on
the feeds repository and cut only where an agent is thinking. The terminal parts can be rendered from
`docs/proof/nemotron.tape` with VHS.

| Time | On screen | Narration |
| --- | --- | --- |
| 0:00–0:12 | Two panes: a terminal on the left, `graphene watch` on the right, empty. | "This is Graphene, on a small Python repository. I'm going to ask for a feature in a paragraph and watch NVIDIA Nemotron models build it on Nebius Token Factory." |
| 0:12–0:40 | The paragraph typed into `graphene ask`. The right pane fills with a tree, every row `?`. | "The planner is Nemotron 3 Ultra, called through Token Factory's OpenAI-compatible API. It reads the repository with read-only tools (list, grep, read) and answers with a tree: sub-goals, and leaves that each name the files they may change and the command that proves them done." |
| 0:40–1:05 | `j` `k`; `Enter` on a leaf shows its scope and check; `E` opens the plan in the editor and a path leaves a scope; `y` on the goal accepts. | "Before anything runs, I prune. This leaf may touch these files and is done when this check passes. I take one path out of its scope, and accept the rest." |
| 1:05–1:50 | `R`. Four leaves turn yellow at once; the node pane shows the executor, its sandbox, its last step and seconds since. | "R runs every ready leaf. Each gets a Nemotron Nano executor on Token Factory. Its loop runs here, and every tool call it makes runs in a Token Factory Sandbox forked from the same checkpoint of the repository. It is held three ways. Its write tools refuse a path outside the scope before writing it. In the sandbox it is a user who can't write outside the scope. And the leaf is done only when Graphene's own check passes and git shows nothing outside the scope." |
| 1:50–2:15 | A leaf comes back, magenta: its reason, and `w  widen …` / `b  a sibling …`. `w`, then `R`. | "This leaf needed the file I took away. It comes back with the reason and the fix already written. One key widens its scope, and it runs again." |
| 2:15–2:40 | Every row green. The left pane: `git log --graph --oneline`, one merge per leaf. | "Every leaf landed as a merge on my branch, with its reason in the message, so git's history reads as the tree." |
| 2:40–2:55 | The bill: dollars per leaf and for the run, at Token Factory's list price, from the usage each call returned. | "Each call's token usage comes back from Token Factory, priced at the list price: this is what each leaf cost, and the run." |
| 2:55–3:00 | The repository's URL. | "Graphene, on GitHub." |

What must be true before recording: the demo run is live, with the frozen configuration, and every
number on screen comes from that run. The numbers in the narration are read off the screen, never
written in advance, and the model named for the executors is the one the frozen configuration uses (Nano, Super, or Nano then Super).
