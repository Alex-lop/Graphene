# Graph Necessity Evaluation

**Status: NOT YET RUN. No participant result is claimed.**

This protocol tests whether the decision-first viewer helps an unfamiliar developer understand the same public evidence faster or more accurately than a canonical flat transcript. It does not test agent quality, memory efficacy, human attestation, live execution, or correctness of the fixture change.

## Frozen Inputs

Use only the checked-in event fixture materialized through the v2 verifier and served by `verified-replay`. Before a session, run:

```bash
uv run --frozen python scripts/generate_viewer_replay.py --check
uv run --frozen python scripts/generate_viewer_replay.py --flat-output /tmp/graphene-replay-flat.txt
shasum -a 256 backend/graphene/viewer/static/replay.json
cat backend/graphene/viewer/static/replay.sha256
```

The two printed digests must match and `--check` must succeed. Stop the study if either condition fails. The replay is a deterministic event fixture, not evidence that these events were captured from a live run.

The viewer condition uses the authenticated `verified-replay` server. The flat condition uses the generated 111-line `/tmp/graphene-replay-flat.txt`: the same mode/meta, five checkpoint heads/attention/stages/outcomes, final public nodes and relationships, Review Brief facts, support paths, and unknowns in canonical text order. It excludes only visual grouping, layout, and interaction and adds no answer-key prose. Participants may not open the README, source fixture, evaluation answer key, or application code.

## Questions

Ask each participant, verbatim:

1. What needs attention now?
2. What changed?
3. Which verified evidence supports each changed path?
4. Where did a human intervene, and was it real or simulated?
5. What remains unknown or outside capture?
6. What entered—and did not enter—the handoff?
7. What later operation explicitly opened or referenced that context?
8. What final outcome exists, and what external outcome does not?

## Frozen Answer Key

1. The replay includes a checkpoint with exactly one pending candidate approval/rejection, then ends with no unresolved Graphene decision after the simulated approval and `Promotion Completed`/`PROMOTED`. Historical Billing and completion denials remain evidence, not current work.
2. The public fixture declares a bounded candidate for `app/auth/limiter.py` and `tests/test_security_policy.py`. Raw source and diff are absent, and this replay performs no new write or test execution.
3. The changeset and hunk references support the declared candidate; the test-receipt node is bound to the changeset, and the candidate is bound to both. The replay proves those committed fixture relationships, not underlying source bytes or test stdout.
4. Clarification answer, feedback, memory approval, and promotion approval are `simulated_fixture`. No real human attestation exists in this mode.
5. Timing does not prove causality; only explicit committed fixture evidence is shown; graph layout and sequence do not prove importance or correctness. Authorized source/diff/test-output bytes may exist only in private live-driver artifacts and are not publicly projected. Live agent behavior, new test execution, arbitrary shell/editor work, deployment, and external model behavior are not observed by this replay.
6. Billing received nothing: zero model dispatch, evidence, memories, source paths, and tools. The Auth path contains a bounded context-brief/decision relationship; exact private brief contents are not public evidence and must not be inferred.
7. Consumer sequence 4 records a `runtime_observed` completed `open_evidence` operation. Its typed `opens_reference` relationship points to the same context-brief reference included by source sequence 8 and injected by consumer sequence 2. This proves fixture opening/reference, not that the context caused or improved later work.
8. A verified fixture `promotion.completed` outcome exists. No real human approval, live test, local or remote production commit, push, PR, deployment, Gemini call, or independent-agent result exists.

Score a question correct only when every material clause above is present and the answer does not add an unsupported claim. Question 3 requires both changed paths and their evidence relationship. Question 7 requires the completed `open_evidence` operation, its context-brief relationship, and no causality claim. Question 8 requires both the fixture outcome and absent external outcome.

## Procedure

Recruit five developers unfamiliar with Graphene. Use a counterbalanced crossover: participants 1, 3, and 5 see viewer then flat; participants 2 and 4 see flat then viewer. Reset the replay before each condition. Give no product explanation, hints, or corrections. Start the timer when the condition becomes visible and stop at the eighth submitted answer or 90 seconds. Preserve answers verbatim, score them blind to condition, and record seconds plus correct answers.

Invalidate and rerun a session if the replay digest fails, either condition exposes different public information, a participant opens excluded material, the facilitator gives a hint, or the exact replay truth label is not continuously visible.

## Results — NOT YET RUN

| Participant | Order | Viewer correct / 8 | Viewer seconds | Flat correct / 8 | Flat seconds | Status |
|---|---|---:|---:|---:|---:|---|
| P1 | Viewer → Flat | — | — | — | — | NOT YET RUN |
| P2 | Flat → Viewer | — | — | — | — | NOT YET RUN |
| P3 | Viewer → Flat | — | — | — | — | NOT YET RUN |
| P4 | Flat → Viewer | — | — | — | — | NOT YET RUN |
| P5 | Viewer → Flat | — | — | — | — | NOT YET RUN |

## Exit and Kill Criteria

Ship the graph as the primary decision surface only if at least four of five participants answer all eight viewer questions correctly within 90 seconds and either: viewer median time is at least 20% lower without more errors, or viewer errors are at least 25% lower without a slower median.

If the viewer provides no measurable advantage, make the Review Brief primary and demote bubbles to an evidence inspector. If a fair independently executed continuation does not benefit from approved-context delivery, remove any claim that Graphene improves agent behavior and retain only proven delivery/audit claims. If no real live-agent path exists, position Graphene as a bounded provenance/review protocol with ADK integration proof, not as a demonstrated autonomous coding-agent product.

Any public/private boundary failure, false human/live-test label, source mismatch between conditions, or unverifiable replay digest stops the study immediately; repair the evidence path before recruiting more participants.
