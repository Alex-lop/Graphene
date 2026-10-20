# Graph direction for `graphene watch`

Research brief, 2026-10-20. Today (`cockpit/flow_view.py`, `cockpit/flowlayout.py`) `g` draws left to right: a node's layer is its longest path from a source, tree edges (goal → sub-goal → task) are quiet lines with no arrowhead, `needs` edges are arrows. The goal sits at the far left and a task that waits on others sits right of its siblings, as in `docs/assets/graph.png`.

## 1. What pipeline and DAG tools do

Execution UIs put **time along the reading axis**; the data and CI world chose horizontal:

- **GitLab** pipeline graph, "Job dependencies" view: "Jobs in the leftmost column run first, and jobs that depend on them are grouped in the next columns"; hovering a job highlights everything that must run before it ([docs](https://docs.gitlab.com/ci/pipelines/)).
- **GitHub Actions**: "Lines between jobs indicate dependencies" ([docs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-the-visualization-graph), [2020 changelog](https://github.blog/changelog/2020-12-08-github-actions-workflow-visualization/)); the text never states the orientation, so left-to-right is from memory, **unverified**.
- **Airflow**: `dag_orientation` defaults to `LR` ([config.yml, 2.10.5](https://github.com/apache/airflow/blob/2.10.5/airflow/config_templates/config.yml)); the Grid view is "each row represents a task, and each column represents a Dag run" ([UI docs](https://airflow.apache.org/docs/apache-airflow/stable/ui.html)).
- **Dagster 1.6**: "Lineage now flows left-to-right instead of top-to-bottom", with collapsible asset groups ([release](https://github.com/dagster-io/dagster/releases/tag/1.6.0)), after users said the top-down view "tends to build width-first" ([forum, via search summary](https://discuss.dagster.io/t/11985142/an-additional-qol-nice-to-have-in-terms-of-ui-ux-would-be-so)).
- **Prefect 2.14.4**: a temporal graph (scalable x-axis) plus "two non-temporal layout options, designed to provide a clearer picture of the dependency paths" ([release](https://github.com/PrefectHQ/prefect/releases/tag/2.14.4)).
- **n8n**: a connection goes from "the right side of a node" to "the left side of the following node" ([docs](https://docs.n8n.io/workflows/components/connections/)). **Node-RED**: "For nodes that sit at the end of a flow, the convention is to right-align the content" ([docs](https://nodered.org/docs/creating-nodes/appearance)).
- **Temporal** draws no DAG: an Event History list and a Timeline of horizontal bars ([docs](https://docs.temporal.io/web-ui), [blog](https://temporal.io/blog/lets-visualize-a-workflow), blog seen only via a search summary).
- **Argo Workflows**: the UI graph is vertical by default with a "Horizontal/vertical layout" toggle (`horizontal?: boolean; // default "false"`, [graph-panel.tsx](https://github.com/argoproj/argo-workflows/blob/main/ui/src/shared/components/graph/graph-panel.tsx)); the CLI prints a tree, `└─┬─✔ hello2a`, the fork glyph meaning parallel ([walk-through](https://argo-workflows.readthedocs.io/en/latest/walk-through/steps/)).
- **LangGraph** hard-codes `graph TD;` in its Mermaid export ([graph_mermaid.py](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/runnables/graph_mermaid.py)); **Mermaid** defaults a direction-less `graph` to `TB` ([grammar](https://github.com/mermaid-js/mermaid/blob/develop/packages/mermaid/src/diagrams/flowchart/parser/flow.jison), [orientations](https://mermaid.js.org/syntax/flowchart.html)); Graphviz `rankdir` defaults to top-to-bottom ([docs](https://graphviz.org/docs/attrs/rankdir/)).
- **Kiro** "builds a dependency graph of the tasks in your tasks.md and groups independent tasks into waves… Waves execute sequentially; tasks within a wave execute concurrently" ([specs docs](https://kiro.dev/docs/specs/), [0.12 changelog](https://kiro.dev/changelog/ide/0-12/)); no graph view is documented.
- Terminal precedent: `git log --graph` draws "on the left hand side of the output" ([git-log](https://git-scm.com/docs/git-log)); `systemd-analyze critical-chain` "prints a tree of the time-critical chain of units" ([man page](https://www.freedesktop.org/software/systemd/man/latest/systemd-analyze.html)).

## 2. What goal and strategy diagrams do

Two families, disagreeing on where the goal goes:

- **Decomposition diagrams put the goal first.** KAOS: "Near the top of the graph stand business or strategical goals. At the bottom (leaves) stand system requirements", and the refinement arrow points *to the parent*, so arrows run toward the goal ([KAOS tutorial](https://www.objectiver.com/fileadmin/download/documents/KaosTutorial.pdf), pp. 6, 12). GSN v3 is the mirror image: SupportedBy is "'A is supported by B' (from A to B)", top goal down to evidence ([standard](https://scsc.uk/gsn-standard), [GSN/SACM note](https://www.scsc.uk/file/gc-main/GSN-and-SACM-v1-1083.pdf)). OKR chart views are "a nested tree-like structure" cascading downward ([Viva Goals](https://learn.microsoft.com/en-us/viva/goals/understanding-views)). An impact map is a mind map with the goal at the centre ([impactmapping.org](https://www.impactmapping.org/drawing.html)).
- **Causal diagrams put the goal last.** The Kellogg logic model: "When 'read' from left to right, logic models describe program basics over time from planning through results", Resources → Activities → Outputs → Outcomes → Impact ([guide](https://19january2021snapshot.epa.gov/sites/static/files/2015-09/documents/logic-model-development-guide.pdf), pp. 1–2, 7). Theory of change maps backwards from the long-term goal ([theoryofchange.org](https://www.theoryofchange.org/what-is-theory-of-change/how-does-theory-of-change-work/)); the pathway keeps goals "at the top", is "read from the bottom up", and arrows give "the sequence that preconditions should be addressed" ([SC4CCM](https://sc4ccm.jsi.com/emerging-lessons/theory-of-change/)).

The rule underneath: a diagram about *why* puts the goal first; one about *what must happen before what* puts it last. A run cockpit is the second kind.

## 3. What graph-drawing research says

- The dot paper assumes "a directed graph has an overall flow or direction, such as top to bottom… or left to right"; its first aesthetic is "aim edges in the same general direction if possible. This aids finding directed paths and highlights source and sink nodes", and it lets the caller pin nodes to the maximum, minimum or same rank ([Gansner et al. 1993](https://graphviz.org/documentation/TSE93.pdf), pp. 1–2), building on [Sugiyama, Tagawa, Toda 1981](https://ieeexplore.ieee.org/document/4308636).
- Readers of English lay time out left to right, and writing direction affected "only… representations of temporal concepts" ([Tversky, Kugelmass, Winter 1991](https://www.tc.columbia.edu/faculty/bt2158/faculty-profile/files/uralanddevelopmentaltrendsingraphicproductions.pdf)).
- Eye tracking on trees: traditional and orthogonal layouts "significantly outperformed radial"; orientation was varied but the abstract names no winner between top-down and left-right ([Burch et al. 2011](https://doi.org/10.1109/TVCG.2011.193), abstract via [OpenAlex](https://api.openalex.org/works/https://doi.org/10.1109/TVCG.2011.193)); strategies differ by orientation ([Burch et al. 2013](https://publica.fraunhofer.de/handle/publica/383510)). I found no study showing LR beats TD or the reverse.
- Consistent edge direction is a measured aesthetic ("upwards flow", [gdMetriX poster](https://ac.tuwien.ac.at/gd2024/posters/gdMetriX.pdf), seen only via search; [Purchase 2002](https://doi.org/10.1006/jvlc.2002.0232), abstract unavailable, **unverified**).
- Arrowheads are a weak cue; tapered edges won Holten and van Wijk's CHI 2009 study ([DOI](https://doi.org/10.1145/1518701.1519054), secondary summaries only, **unverified**). Position carries direction better than glyphs.

## 4. Answers

**(a) Goal at the end, on the right.** First, Graphene's two edge kinds mean the same thing once the tree is read upward: "greet says hello" must land before "say hello" is done, exactly as before "app says hello and goodbye". Reversing the tree edges gives one arrow meaning, "must land before", and the goal becomes the single sink, which dot's A1 says a consistent direction "highlights". Second, time reads rightward (Tversky; GitLab, Airflow, Dagster, n8n, Node-RED), and a run's question is "how far from the goal are we": the front of done boxes moves toward the goal box, like Impact at the end of a logic model. Third, the cockpit list and plan text already lead with the goal, so the graph can make it the destination. The cost is leaving the KAOS/GSN/OKR root-first convention; that is Alex's call.

**(b) Yes, the same way.** In `flow_graph`, emit tree edges as (child, parent); `_layers` then puts tasks with no needs at layer 0 and dependents after them. Pin all sub-goals to one layer after the last task and the goal to the last layer (dot's same-rank/max-rank idea), or a sub-goal lands in a task's column. Better, draw sub-goals as **lanes** (Dagster and Airflow groups are clusters, not ranks): a rule across the graph with the sub-goal's name and count, costing one row instead of a 16–20 column rank. Then only tasks and the goal are boxes, and every arrow is a need.

**(c) Keep left to right for the titles.** Titles are horizontal text, so a sibling costs 3–4 rows in LR but 25–30 columns in TD: a 100×24 terminal holds about six task boxes in a column and three in a row. Plans grow in tasks, not depth, so breadth must fall on the axis a terminal scrolls, which is vertical (Dagster's width-first complaint again). Size each column to its longest title, cap near 30 cells, and wrap a long title onto a second box line before the `LABELS` ladder shrinks it. Lanes free the roughly 36 columns the sub-goal and goal ranks take today, so three wave columns and the goal fit in 100 cells.

**(d) Waves are columns; the critical path is the double line.** With needs as the only edges, layer = wave, Kiro's definition and GitLab's "leftmost column runs first"; a header per column says `wave 2 · agent 4`, the running wave's in bold. The critical path is "the longest stretch of dependent activities" ([CPM](https://en.wikipedia.org/wiki/Critical_path_method)): the longest chain to the goal, drawn with `═ ║ ╚` (the renderer already ranks `edge_hot` above `edge`), its boxes sorted to the top of their lanes; other needs stay single `─`. The goal box carries `4 of 4`, a lane rule `2 of 2 ✓`. Direction is carried by position plus one `▶` at the box, not arrowheads along the line.

## 5. Mock at 100 columns (86 used, 15 rows)

```
  wave 1 · 3 agents             wave 2 · agent 4                          goal
── say hello ───────────────────────────────────────────────────────────── 2 of 2 ✓ ──
 ✓─────────────────────┐
 │ greet says hello    ├═══╗
 └ 1 ──────────────────┘   ║
 ✓─────────────────────┐   ║
 │ bye says goodbye    ├───╢
 └ 2 ──────────────────┘   ║
── command line ───────────╫────────────────────────────────────────────── 2 of 2 ✓ ──
 ✓─────────────────────┐   ║
 │ banner says welcome ├───╫───────────────────────────────────┐
 └ 3 ──────────────────┘   ║                                   │
                           ║  ✓────────────────────────────┐   │  ✓──────────────────┐
                           ╚═▶│ app says hello and goodbye ├═══╧═▶│ a friendlier app │
                              └ 4 ─────────────────────────┘      └ 4 of 4 ──────────┘
   ═ the longest chain, 1 → 4 → goal      ─ other needs      lanes: sub-goals · columns: waves
```

Lanes are sub-goals, columns are waves, every arrow says "must land before", the goal is where they arrive, and the double line is the chain the goal waits on.

## 6. Unverified or not found

GitHub's graph orientation (memory only); Temporal's timeline details and Dagster's forum thread (search summaries); Holten's tapered-edge result and Purchase's flow metric (secondary sources); no readability study comparing LR with TD for directed graphs.
