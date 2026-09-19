// The contract the page draws: a mirror of src/graphene_debrief/graph.py, which is the source of
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

// What the server answers on GET /api/graph?sessions=… and what an exported file carries inline.
export interface Payload {
  runs: Run[];
  graph: Graph;
}
