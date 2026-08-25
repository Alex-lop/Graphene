# Graph economics benchmark

This harness runs one operator-supplied local runner in exactly three modes with the same fixture and deterministic quality gate. It compares economics only for runs that both succeed and pass that gate; every receipt and process capture remains available for audit. No model, network, or paid service is called by default.

The runner reads `GRAPHENE_BENCHMARK_MODE`, `GRAPHENE_BENCHMARK_FIXTURE_ID`, and `GRAPHENE_BENCHMARK_RUN_INDEX`, then prints one JSON receipt. Each receipt must use the schema enforced in `graph_economics.py`, explicitly writing `"unavailable"` for metrics the provider does not expose. The quality-gate digest is SHA-256 of canonical JSON containing only `command`, `deterministic`, and `gate_id`.

```sh
python benchmarks/graph_economics.py template --output results/unrun.json
python benchmarks/graph_economics.py run \
  --fixture-id disposable-repo-v1 \
  --repetitions 5 \
  --raw-directory results/raw-001 \
  --output results/comparison-001.json \
  -- python path/to/local_runner.py
```

**No result is claimed, and none is coming from the deterministic path.** `graph_economics` is deliberately deferred: the credential-free driver emits no token or cost field, and a coordinated-versus-uncoordinated comparison built on scripted workers would measure the fixture rather than the system. See [DEFERRAL.md](DEFERRAL.md) for the reasoning, the designs that were rejected, and what a real result requires.

Outputs and raw directories must be new: the harness atomically creates files and refuses to overwrite evidence. The checked-in template is `NOT PROVEN`; replace it only with real equal-gate receipts, never estimates presented as measurements.
