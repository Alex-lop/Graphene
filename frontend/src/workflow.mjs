export const TASKS = Object.freeze({
  baseline: "baseline_max_attempts",
  adapted: "adapted_window_seconds",
});

export const EXACT_CORRECTION = "When security-sensitive authentication behavior changes, add or update tests/test_security_policy.py with a regression test covering that behavior.";

export const SCOPE_OPTIONS = Object.freeze([
  { value: "all_auth", label: "Every app/auth/** change" },
  { value: "rate_limiter_only", label: "Only rate-limiter changes" },
]);

function requireValue(value, message) {
  if (value === null || value === undefined || value === "") throw new TypeError(message);
  return value;
}

function latestRun(runs, taskId) {
  return runs
    .filter((run) => run.task_id === taskId)
    .sort((left, right) =>
      String(left.created_at ?? "").localeCompare(String(right.created_at ?? "")) ||
      String(left.run_id).localeCompare(String(right.run_id)),
    )
    .at(-1) ?? null;
}

export function createRunPayload(taskId, idempotencyKey) {
  if (!Object.values(TASKS).includes(taskId)) throw new TypeError("unknown frozen task");
  return { task_id: taskId, idempotency_key: idempotencyKey };
}

export function executeRunPayload(run, idempotencyKey) {
  return {
    expected_run_revision: requireValue(run?.revision, "run revision is missing"),
    idempotency_key: idempotencyKey,
  };
}

export function feedbackPayload(run, selectedHunkId, scopeId, idempotencyKey) {
  if (!SCOPE_OPTIONS.some((option) => option.value === scopeId)) throw new TypeError("unknown server-owned scope option");
  const evidence = run?.proof?.find(
    (item) => item.type === "tool.file_written" && item.payload?.path === "app/auth/limiter.py",
  ) ?? run?.proof?.find((item) => item.type === "tool.file_written");
  return {
    correction: EXACT_CORRECTION,
    evidence_event_id: requireValue(evidence?.event_id, "baseline file-write evidence is missing"),
    selected_hunk_id: requireValue(selectedHunkId, "baseline hunk evidence is missing"),
    scope_id: scopeId,
    expected_run_revision: requireValue(run?.revision, "baseline revision is missing"),
    idempotency_key: idempotencyKey,
  };
}

export function memoryDecisionPayload(memory, idempotencyKey) {
  return {
    decision: "approve",
    expected_revision: requireValue(memory?.revision, "memory revision is missing"),
    idempotency_key: idempotencyKey,
  };
}

export function hasPromotionBindings(run, memory) {
  const candidate = run?.candidate;
  const testReceipt = candidate?.test_receipt;
  const injected = run?.injected_memories?.some(
    (item) => item.memory_id === memory?.memory_id && item.revision === memory?.revision,
  );
  return Boolean(
    run?.state === "waiting_for_promotion" &&
    Number.isInteger(run.revision) &&
    candidate?.base_commit_sha &&
    candidate?.candidate_patch_sha256 &&
    candidate?.candidate_tree_sha256 &&
    candidate?.candidate_tree_hash_version === "graphene.tree.v2" &&
    testReceipt?.receipt_sha256 &&
    run.context_packet_id &&
    run.context_packet_sha256 &&
    Number.isInteger(run.source_graph_revision) &&
    run.source_graph_hash &&
    Array.isArray(run.selected_node_ids) &&
    injected &&
    memory?.state === "approved"
  );
}

export function promotionPayload(run, memory, idempotencyKey) {
  if (!hasPromotionBindings(run, memory)) throw new TypeError("promotion bindings are incomplete");
  return {
    expected_run_revision: run.revision,
    base_commit_sha: run.candidate.base_commit_sha,
    candidate_patch_sha256: run.candidate.candidate_patch_sha256,
    candidate_tree_sha256: run.candidate.candidate_tree_sha256,
    candidate_tree_hash_version: run.candidate.candidate_tree_hash_version,
    memory_id: memory.memory_id,
    memory_revision: memory.revision,
    context_packet_id: run.context_packet_id,
    context_packet_sha256: run.context_packet_sha256,
    source_graph_revision: run.source_graph_revision,
    source_graph_hash: run.source_graph_hash,
    selected_node_ids: [...run.selected_node_ids],
    test_receipt_sha256: run.candidate.test_receipt.receipt_sha256,
    idempotency_key: idempotencyKey,
  };
}

export function deriveControls({ hasToken, busy, baseline, memory, adapted, selectedHunkId }) {
  const idle = hasToken && !busy;
  return {
    reset: idle,
    baseline: idle && (!baseline || baseline.state === "queued"),
    feedback: idle && baseline?.state === "waiting_for_promotion" && !memory && Boolean(selectedHunkId),
    approveMemory: idle && memory?.state === "proposed",
    adapted: idle && memory?.state === "approved" && (!adapted || adapted.state === "queued"),
    promote: idle && hasPromotionBindings(adapted, memory),
    switchBaseline: !busy && Boolean(baseline),
    switchAdapted: !busy && Boolean(adapted),
  };
}

export class GoldenDemo {
  #mutate;
  #keyFactory;
  #keys = new Map();
  #token = null;
  #onChange;

  constructor({ mutate, keyFactory = () => crypto.randomUUID(), onChange = () => {} }) {
    this.#mutate = mutate;
    this.#keyFactory = keyFactory;
    this.#onChange = onChange;
    this.state = {
      hasToken: false,
      busy: null,
      error: null,
      baseline: null,
      memory: null,
      adapted: null,
      activeTask: null,
    };
  }

  get snapshot() {
    return { ...this.state };
  }

  #notify() {
    this.#onChange(this.snapshot);
  }

  #key(operation) {
    if (!this.#keys.has(operation)) this.#keys.set(operation, `${operation}_${this.#keyFactory()}`);
    return this.#keys.get(operation);
  }

  #requireToken() {
    if (!this.#token) throw new Error("Enter the runtime demo token first.");
    return this.#token;
  }

  async #perform(operation, action) {
    if (this.state.busy) throw new Error("Another demo action is still running.");
    this.state.busy = operation;
    this.state.error = null;
    this.#notify();
    try {
      return await action();
    } catch (error) {
      this.state.error = error instanceof Error ? error.message : "Demo action failed";
      throw error;
    } finally {
      this.state.busy = null;
      this.#notify();
    }
  }

  setToken(token) {
    this.#token = String(token ?? "");
    this.state.hasToken = Boolean(this.#token);
    this.state.error = null;
    this.#notify();
  }

  clearToken() {
    this.#token = null;
    this.state.hasToken = false;
    this.#notify();
  }

  hydrateRuns(runs) {
    this.state.baseline = latestRun(runs, TASKS.baseline);
    this.state.adapted = latestRun(runs, TASKS.adapted);
    if (!this.state.activeTask) {
      this.state.activeTask = this.state.adapted ? TASKS.adapted : this.state.baseline ? TASKS.baseline : null;
    }
    this.#notify();
  }

  hydrateMemory(memory) {
    if (!memory?.memory_id || !memory?.revision || !memory?.state) return;
    this.state.memory = memory;
    this.#notify();
  }

  setActiveTask(taskId) {
    if (taskId !== null && !Object.values(TASKS).includes(taskId)) return;
    this.state.activeTask = taskId;
    this.#notify();
  }

  controls(selectedHunkId = null) {
    return deriveControls({ ...this.state, selectedHunkId });
  }

  async reset() {
    return this.#perform("reset", async () => {
      const result = await this.#mutate(
        "/api/demo/reset",
        { idempotency_key: this.#key("reset") },
        this.#requireToken(),
      );
      this.#keys.clear();
      Object.assign(this.state, {
        baseline: null,
        memory: null,
        adapted: null,
        activeTask: null,
      });
      return result;
    });
  }

  async #createAndExecute(taskId, stateKey) {
    let run = this.state[stateKey];
    if (!run) {
      run = await this.#mutate(
        "/api/runs",
        createRunPayload(taskId, this.#key(`${stateKey}-create`)),
        this.#requireToken(),
      );
      this.state[stateKey] = run;
      this.state.activeTask = taskId;
      this.#notify();
    }
    if (run.state !== "queued") return run;
    run = await this.#mutate(
      `/api/runs/${encodeURIComponent(run.run_id)}/execute`,
      executeRunPayload(run, this.#key(`${stateKey}-execute`)),
      this.#requireToken(),
    );
    this.state[stateKey] = run;
    this.state.activeTask = taskId;
    return run;
  }

  async runBaseline() {
    return this.#perform("baseline", () => this.#createAndExecute(TASKS.baseline, "baseline"));
  }

  async submitFeedback(selectedHunkId, scopeId) {
    return this.#perform("feedback", async () => {
      const memory = await this.#mutate(
        `/api/runs/${encodeURIComponent(this.state.baseline?.run_id ?? "")}/feedback`,
        feedbackPayload(
          this.state.baseline,
          selectedHunkId,
          scopeId,
          this.#key("feedback"),
        ),
        this.#requireToken(),
      );
      this.state.memory = memory;
      return memory;
    });
  }

  async approveMemory() {
    return this.#perform("approve-memory", async () => {
      const memory = this.state.memory;
      const approved = await this.#mutate(
        `/api/memories/${encodeURIComponent(memory?.memory_id ?? "")}/decision`,
        memoryDecisionPayload(memory, this.#key("approve-memory")),
        this.#requireToken(),
      );
      this.state.memory = approved;
      return approved;
    });
  }

  async runAdapted() {
    if (this.state.memory?.state !== "approved") throw new Error("Approve memory revision 1 first.");
    return this.#perform("adapted", () => this.#createAndExecute(TASKS.adapted, "adapted"));
  }

  async promote() {
    return this.#perform("promote", async () => {
      const run = this.state.adapted;
      const promoted = await this.#mutate(
        `/api/runs/${encodeURIComponent(run?.run_id ?? "")}/promote`,
        promotionPayload(run, this.state.memory, this.#key("promote")),
        this.#requireToken(),
      );
      this.state.adapted = promoted;
      return promoted;
    });
  }
}
