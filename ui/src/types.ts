// The contract the page draws: a mirror of src/graphene_map/graph.py, which is the source of
// truth. Every position here was computed in Python. The page adds `dy` and `extra` when the
// person opens a group or a directory, and decides no order and no size of its own.

export type Grade = "edit" | "shell" | "commit" | "window" | "unknown" | "record";

export interface Lane {
  id: string;
  kind: "main" | "agent" | "group" | "unknown";
  session: string | null;
  agent: string | null;
  t0: string;
  t1: string | null;
  parent: string | null; // the lane that spawned it
  group: string | null; // the collapsed group it is drawn on until the person opens it
  depth: number;
  type: string | null;
  task: string | null;
  prompt: string | null;
  cwd: string | null;
  worktree: string | null;
  run: string | null;
  phase: string | null;
  label: string | null;
  closing: string | null;
  x0: number;
  x1: number;
  y: number;
  dy: number; // added to y when its group is open
  members: number;
  extra: number; // height a group adds below itself when open
  source: string;
}

export interface Row {
  id: string;
  kind: "dir" | "file";
  path: string;
  t0: string;
  dir: string | null;
  y: number;
  dy: number; // added to y when its directory is open
  files: number;
  changes: number;
  extra: number;
  collision: boolean;
  agents: string[];
}

export type MarkKind =
  | "prompt"
  | "step"
  | "spawn"
  | "check"
  | "commit"
  | "failure"
  | "refused"
  | "outside"
  | "change"
  | "evidence";

export interface Mark {
  id: string;
  kind: MarkKind;
  region: "lanes" | "rows";
  at: string; // the lane or row it sits on
  x: number;
  y: number;
  t: string;
  agent: string | null; // the lane whose colour it takes
  grade: Grade;
  ref: string; // the first record behind it
  count: number;
  label: string | null;
  ok: boolean | null;
  shared: boolean;
  copy: boolean;
  committed: string | null; // a commit mark: git's committer time (t is when the recorded call began)
}

export interface Link {
  id: string;
  kind: "spawned" | "returned" | "touched" | "committed-in" | "ran" | "blocked";
  source: string;
  target: string;
  grade: Grade;
  ref: string;
  count: number;
}

export interface Task {
  id: string;
  subject: string | null;
  ref: string;
  lane: string;
  created: string;
  x: number;
  started: string | null;
  done: string | null;
}

export interface Coverage {
  committed_files: number;
  write: number;
  edit: number;
  shell: number;
  commit: number;
  nothing: number;
  window: number;
  paths: { commit: string[]; nothing: string[] };
}

export interface Graph {
  version: number;
  caption: string;
  run: {
    sessions: { id: string; source: string; recorded_by: string; started: string | null; ended: string | null }[];
    repo: string;
    started: string | null; // the sessions' own start and end, as the card and the rail print them
    ended: string | null;
    t0: string | null;
    t1: string | null;
    prompts: number;
    agents: number;
    commits: number;
  };
  axis: {
    unit: string;
    width: number;
    bucket: number;
    breaks: { kind: "break"; t0: string; t1: string; x0: number; x1: number; seconds: number }[];
    ticks: { x: number; t: string }[];
  };
  lanes: Lane[];
  rows: Row[];
  marks: Mark[];
  links: Link[];
  tasks: Task[];
  coverage: Coverage;
  counters: Record<"failed_checks" | "rerun_green" | "refused" | "failures" | "outside" | "collisions", number>;
  omitted: Record<string, number>;
  rules: Record<"collision" | "outside", string>; // the rule behind a claim the page makes, in words
}

export interface Run {
  id: string;
  started_at: string | null;
  ended_at: string | null;
  source: string;
  prompts: number;
  calls: number;
  agents: number;
  files: number;
}

// -- the plan: a mirror of src/graphene_map/plan_view.py, which computes every position ------

export type NodeState = "proposed" | "open" | "running" | "review" | "done";
export type Shown = NodeState | "waiting" | "ready" | "came back" | "sub-goal";

export interface Entry {
  at: string;
  kind: string;
  actor: string;
  said: string;
}

export interface PlanNode {
  id: string;
  title: string;
  goal: string;
  scope: string[];
  check: string | null;
  signoff: boolean;
  needs: string[];
  owner: string; // "agent", or a person's name
  parent: string | null; // the node this one helps achieve; null is directly under the plan's goal
  aside: boolean; // made from what the person typed into a session
  sub_goal: boolean; // it has children: nobody takes it, and it is done when they are
  depth: number; // how far below the root it sits: what the page indents by
  why: string[]; // the path from the goal down to this node, root first
  leaves_done: number; // a sub-goal's progress, in the leaves beneath it
  leaves_total: number;
  state: NodeState;
  display_state: Shown; // an open node that cannot start yet is waiting, not ready; one handed back came back
  rev: number;
  executor: string | null;
  started_at: string | null;
  finished_at: string | null;
  waits: string[]; // why it is not moving, in sentences
  log: Entry[];
  lane: string;
  column: number;
  row: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlanLane {
  id: string;
  label: string;
  person: boolean;
  y: number;
  height: number;
  nodes: number;
}

export interface PlanEdge {
  id: string;
  source: string; // the node that must finish
  target: string; // the node that waits on it
  points: number[][];
}

export interface Waiting {
  id: string;
  title: string;
  why: string;
}

export type Hole = "scope" | "check" | "stop" | "person";

export interface Plan {
  version: number;
  repo: string; // the checkout, by name: a plan exists before any run has been recorded in it
  goal: string; // the root of the tree: why any of this is being done, in the person's words
  person: string;
  paused: boolean;
  width: number;
  height: number;
  nodes: PlanNode[];
  lanes: PlanLane[];
  edges: PlanEdge[];
  counts: Record<NodeState, number>;
  waiting_on_person: Waiting[];
  loose: string[]; // changed while no node owned it
  all_done: boolean; // every node done: still in force until the person archives or pauses
  forecast: { runs: string[]; waits: { id: string; why: string[] }[] };
  holes: Record<Hole, string>; // where the mechanism behind a control stops, printed beside it
  writable: boolean; // false for an exported file, and for a page opened from an agent's shell
  token: string | null; // this launch's, and never in an export
}

// What the server answers on GET /api/graph?sessions=… and what an exported file carries inline.
export interface Payload {
  runs: Run[];
  plan: Plan;
  graph: Graph;
}
