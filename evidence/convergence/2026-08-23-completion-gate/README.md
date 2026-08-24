# Completion gate — 2026-08-23 live North Star missions

The §8 gate of `GRAPHENE_CONVERGENCE_DIRECTIVE` v2: at least **8/10 ordinary**
and **3/3 controlled-failure** missions finish end to end with receipts. This
directory is the machine record. Every number below is derived from the
committed mission store and its evidence artifacts, not from a console log.

All fourteen missions ran on the same `main` as the commit that carries this
directory, against a freshly materialized North Star target per mission, with
`gemini-3.5-flash` on Vertex AI (`GOOGLE_CLOUD_LOCATION=global`) and
`GRAPHENE_CHECK_EXECUTOR=host-sandbox`.

## Result

| Gate | Required | Observed |
|---|---|---|
| Ordinary missions completing end to end | ≥ 8/10 | **9/10** |
| Controlled-failure missions completing after recovery | 3/3 | **3/3** |

"Completing end to end" means the mission reached `awaiting_result` — every work
task accepted, deterministic assembly accepted, and the policy-bound
verification check passed on the assembled candidate. One of those missions was
then carried the rest of the way by hand (bundle, verification, bundle-bound
approval, isolated commit) and its generated feature was executed; see
`feature_run.txt` and `why.txt`.

## The one ordinary mission that did not complete

`mission_start_b6be7f35ba803c6dc34597b1` failed honestly, and it is the most
interesting row here. Its `markdown_report_renderer` task failed a test the
model itself had written. The retry received the diagnostic — failure class
`checks_failed`, the failing node id
`tests/test_report_markdown.py::test_render_markdown_with_data` — and produced
a second attempt at fence 2 that failed with the **same failure signature**
(`783334908e84…`). Graphene terminalized instead of buying a blind third
attempt, and the mission failed. That is the intended behaviour of the
diagnostic-aware retry, observed in the wild rather than in a fixture.

## The three controlled-failure missions

Each was started with `graphene mission start --inject-check-fault`, which fails
the mission's first trusted check exactly once with exit 97 and a receipt
labelled `simulated_fixture` / `demo_injected_deterministic_check_failure`. In
all three, the failed attempt sat at fence 1, the retry ran at fence 2, it was
`committed`, the sibling work task was untouched, and the mission completed.

| Mission | Faulted task | Failed attempt | Retry | Mission |
|---|---|---|---|---|
| `…1b3279329462` | `implement-report-json` | n=1 fence=1 | n=2 fence=2 committed | `awaiting_result` |
| `…2aa4783fb723` | `implement_report_json` | n=1 fence=1 | n=2 fence=2 committed | `awaiting_result` |
| `…2c52f8029925` | `implement_json_report` | n=1 fence=1 | n=2 fence=2 committed | `awaiting_result` |

The narration for these is **check process**, never "the Gemini worker died".
The diagnostic's own summary says so in words: "The owned check process for
… exited 97 under the deterministic injected fault … No test assertion failed;
the check process itself was made to fail."

## Spend

`receipts.ndjson` is one line per provider call, from evidence-bound receipts,
cost rounded up per receipt at the `gemini-3.5-flash` paid tier
($1.50/1M input, $9.00/1M output, thinking billed as output).

| | |
|---|---|
| Missions with receipts | 14 |
| Planner calls | $0.94 |
| Worker calls | $1.36 |
| **Total** | **$2.30** |

## Files

- `missions.ndjson` — one line per mission: status, head sequence and event
  digest, and every attempt with its fence, state, result code, and the failure
  class / failed check names / signature of its diagnostic where one exists.
- `receipts.ndjson` — one line per provider call with token counts and cost.
- `feature_run.txt` — the generated feature executed from the approved isolated
  commit `64e8aecc9ff7…`, both report formats, plus `git show --stat` proving
  the mission created exactly the four files its policy allowed.
- `why.txt` — `graphene why` on the same mission, chaining target → producer
  attempt → assembly → verification → committed final approval.

## What this does not prove

- Not a claim about any model's ability: 9/10 is this target, this contract
  test, and this model on this day.
- The controlled failure is an injected fault in Graphene's own check runner,
  labelled as such in evidence. It is not a real infrastructure failure.
- Nothing here touches Cloud Run or Firestore.
