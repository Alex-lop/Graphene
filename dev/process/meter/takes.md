# Nemotron takes for the video, 7 October

## Round 1, 01:00 to 01:40

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

## Round 2, 02:00 to 03:00

The same configuration with `--prepare 'pip install -q pytest'` on the executor, on a wheel with the planner's
text tool calls read. From take 13, `nemotron.sh` widens and runs again up to three times, as a person pressing
`w` again would; before, it stopped after one round.

| take | task | what happened |
|---|---|---|
| 9 | feeds | a 7-leaf tree ($0.71); price-zero landed; xml-reader came back: its check runs the test file xml-tests writes |
| 10 | report | no proposal, twice: a `needs:` naming no node, then prose under the plan |
| 11 | feeds | a 4-leaf tree on the second try ($0.58); xml-feed and validation came back for their test folders, were widened, and landed; wiring came back for `cli/main.py`, the path the take prunes on purpose |
| 12 | report | a 3-leaf tree ($0.30); json-fmt came back: its check needs the test file test-json writes |
| 13 | feeds | no proposal, twice: a `then:` naming a file, then a heading |
| 14 | feeds | no proposal, twice: a cycle in its needs, then markdown |
| 15 | feeds | no proposal, twice: 60 calls and no answer ($0.62), then a `then:` it could not read |
| 16 | report | no proposal, twice: JSON instead of the plan's text, then a `---` |
| 17 | feeds | a 3-leaf tree ($0.35); validate-zero-price came back, was widened, and landed; xmlfeed needs a file normalize-xml writes |
| 19 | feeds | no proposal, twice: markdown headings |
| 21 | feeds | no proposal, twice: an answer cut off, then a heading |

(18, 20 and 22 never ran: the loop that started them passed two take numbers as one.)

**Kept: take 11**, as `tests/recordings/meter-nemotron-take-11.jsonl`, in place of take 6. It replays with no
key and no network, and the leak check counts no key, no project and no home path in it. Ultra planned it.
Nano did both leaves that landed, in Sandboxes; on wiring's second attempt Graphene stepped up to Super. Its
meter strip climbs as it runs (Nano's xml-feed: 38 turns, $0.01). It ends where a person would press `w`:
wiring asks for `cli/main.py`. No take ran clean to the end.

**Why:** Ultra planned a readable tree in 7 of 19 takes. The other twelve broke the plan's format or never
answered. Every tree stopped where one leaf needed a file another leaf writes, mostly a test file its check
runs, which the planner's rules forbid and nothing checks. Graphene's own bugs found on the way are fixed: the
planner reads a tool call written as text (take 3), and a replay draws the meter strip (round 2).
