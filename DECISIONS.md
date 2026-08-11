# ReviewLatch decision log

## 2026-08-11 — Phase 0 scope lock

- `ULTRA_MVP_EXECUTION.md` is authoritative. ReviewLatch targets Collaborative Partner with one controlled Python fixture and one ADK/Gemini path.
- `contracts/golden_path.json` is the machine-readable source of truth for tasks, prompt, tools, scope, tests, retrieval, API, and lifecycle. Implementation may not silently revise it.
- Python is pinned to 3.13, Node to 22, Google ADK to 2.5.0, the model policy to `gemini-3.5-flash`, Cloud Run to `us-central1`, and Vertex to `global`.
- The fixture runner executes only `python -m pytest -q -p no:cacheprovider`; writes are limited to `app/auth/limiter.py` and `tests/test_security_policy.py`.
- Observed toolchain: `uv` uses Python 3.13.9; the system `python3` is 3.14.3; Docker 29.6.1 is running; Git 2.39.3 is available. Local Node is 23.11.0 and Node 22 remains unavailable; `gcloud` is absent.
- Cloud/model access is not verified: `gcloud`, ADC/project configuration, and Gemini credentials are absent locally. No cloud or model result is claimed.
- The credit request, Devpost draft, and saved Collaborative Partner selection are not evidenced locally and need Alex's confirmation.
- Native hooks, MCP, SQLite, multi-vendor adapters, graph UI, import analysis, invalidation/repair, A/B evaluation, arbitrary repositories, and multi-user auth remain explicitly cut.
