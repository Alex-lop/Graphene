# Nemotron takes for the video, 7 October

`dev/proof/nemotron.sh` with `RECORD=`, eight times between 01:00 and 01:40: Ultra plans
(`nvidia/Nemotron-3-Ultra-550b-a55b`), Nano then Super do the leaves in Token Factory Sandboxes (ConTree's
whoami grants this key everything a leaf uses). All on the night's ledger, purpose `nemotron-take`.

| take | task | planner | what happened |
|---|---|---|---|
| 1 | feeds | 30 steps | no proposal, twice: Ultra read for 30 calls and never answered ($0.29) |
| 2 | report | 30 steps | no proposal, twice: markdown headings instead of the plan's text |
| 3 | feeds | 60 steps | no proposal, twice: it wrote `<tool_call>{…}</tool_call>` and the planner took that for its answer |
| 4 | report | 60 steps | a 2-leaf tree on the second try; the first leaf came back: its check runs a test file the other leaf writes |
| 5 | feeds | 60 steps, fixed | no proposal, twice: the plan's format broken (a question with no words) |
| 6 | report | 60 steps, fixed | a 2-leaf tree on the first try ($0.06); Nano's leaf landed in a Sandbox; the test leaf came back: the Sandbox's Python has no pytest |
| 7 | report | `--prepare 'pip install -q pytest'` | no proposal, twice: headings |
| 8 | report | the same | a 3-leaf tree on the second try ($0.29); the first leaf came back: it needs the test file another leaf writes |

**Kept: take 6**, as `tests/recordings/meter-nemotron-take-6.jsonl`. It replays with no key and no network,
and the leak check counts no key, no project and no home path in it. Ultra planned it; Nano did the leaf
that landed, in a Sandbox; the leaf that came back was Nano's, then Super's, and its reason is the
Sandbox's, not the model's. No take ran clean to the end.

**Why:** Ultra planned a readable tree in 3 of 8 takes. The other five broke the plan's format or never
answered. In 2 of the 3 it did, a leaf's check needed a file another leaf writes, which the planner's rules
forbid. One bug was Graphene's, and it is fixed: the planner now reads a tool call written as text (take 3).
