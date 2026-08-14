# Graphene, simply

Graphene shows what a scoped coding agent actually did and which committed evidence supports it. It records only operations routed through its closed production service. A human can anchor a correction, approve a scoped memory, and promote a verified candidate. A fresh agent gets only an authorized brief and evidence allowlist. The visualization explains explicit relationships; it does not infer hidden causality, importance, or correctness.

## Run it

```bash
uv sync --frozen
uv run --frozen graphene demo --driver scripted-local
```

The command creates its own private runtime and opens a local read-only viewer. Each gate first shows the bounded correction/scope, memory revision/digest, or candidate/test receipt you are deciding. Press Enter to accept the displayed safe demo default. Ctrl-C stops the viewer but retains the runtime; add `--cleanup` to delete it.

## Read the bubbles

- Color means entity kind: agent, tool, file/evidence, human/memory, policy, test, handoff, or promotion.
- Size means capped observed **activity**, never importance, correctness, or impact.
- Lines mean explicit committed evidence/source relationships; width uses a capped observed edge activity count.
- Borders/badges mean state and truth provenance. The status strip reports verification, connection, and omissions.

## Truth levels

- **Scripted local:** no ADK Runner, no model, zero Gemini calls; exercises production v2 services and the macOS fixed-test path.
- **ADK fake:** real Google ADK 2.5.0 Runner plus deterministic fake LLM, zero Gemini calls; component proof only. It is tested but not yet a `graphene demo` driver.
- **Verified replay:** no live agent; replays verified sanitized v2 fixture events. Its gates are explicitly simulated, so it is visual proof—not human, process, or model proof—and is not yet a `graphene demo` driver.
- **Real Gemini:** not currently claimed or exposed; requires explicit credentials, project, spend, and observed model identity with no fallback.

Automated process fixtures are a separate proof level: their decision events are durably labeled `simulated_fixture`, never `human_attested`, in addition to the terminal/viewer warning.

Current support is macOS plus the checked-in sanitized Auth fixture. Linux/Docker fixed tests fail closed. Graphene is not approved here for arbitrary confidential repositories, real cloud deployment, autonomous push, or whole-repository capture.

## Troubleshooting

1. Confirm `python --version` is 3.13 and `uv --version` works.
2. Confirm `test -x /usr/bin/sandbox-exec` succeeds on macOS.
3. Run `uv sync --frozen` from the repository root.
4. Use `--no-open` if the browser does not launch, then open the printed loopback URL.
5. Read `DEMO_ERROR` in the terminal; the printed private runtime is retained unless `--cleanup` was explicit.

## Roadmap

- **Now:** visual observer over verified commits.
- **Next:** complete and prove the v2 Google ADK/Gemini execution path.
- **Then:** allow an agent to receive/query only a bounded, authorized graph-derived context brief and evaluate whether it improves continuation.
- **Later:** Linux isolation, durable cloud artifacts, retention, and scale only after evidence warrants them.
