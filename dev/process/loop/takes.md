# Nemotron takes, 9 October

`dev/proof/nemotron.sh` as the last two nights ran it: Ultra plans (`nemotron --steps 60`); Nano, then Super on a
retry, do the leaves in Token Factory Sandboxes (`--placement sandbox --prepare 'pip install -q pytest'`); the
scripted prune takes `cli/main.py` out of every scope; the script widens a leaf that came back and runs again, up
to three times. Every take recorded, every row on the ledger under `takes`. Takes 1 to 4 ran on lane 3's build
before its review (`7b6d2f6`); takes 5 and 6 on the final build (`ed97b4e`): every fault at once, sent back at
most twice, mechanical faults repaired, a risk with options read as a question.

A clean take, as the directive has it: every leaf landed, or came back for a reason the person would accept.

| take | task | the plan (Ultra) | what happened |
|---|---|---|---|
| 1 | feeds | 3 leaves, $0.17 | `xml-reader` came back twice: for the test file it had to write and did not own (widened), then for `normalize/fields.py`, which `normalize-config` owned (not offered). 0 of 3 landed. Not clean. |
| 2 | report | 3 leaves, $0.11 | All three landed on Nano's first attempts: 22 calls, $0.009, 542 s. **Clean, end to end.** |
| 3 | feeds | no proposal | Three answers, each with the same fault: an `option:` under a `risk:`. The validator sent it back twice with every fault listed; Ultra wrote it again. $0.17. |
| 4 | report | 3 leaves, $0.09 | `impl` and `test-json` landed; `test-text` came back saying the implementation was missing, which had landed. Nano misread its leaf. Not clean. |

| 5 | feeds | 7 leaves, $0.26 | The largest tree of the night, with an end-to-end test leaf. `xml-reader` and `ingest-registry` landed; `normalize-map` came back for `config/defaults.py`, which `config-enable` owned and had not run yet (not offered: a path has one leaf that writes it). The run's line said `width 2 of 3`. Not clean. |
| 6 | report | no proposal | Three answers, each with a board question written as a node (`'json-format' is a new leaf with no scope and no check`): sent back twice with every fault listed; Ultra wrote it again. $0.08. |

**Kept:** take 2, as `tests/recordings/loop-nemotron-take-2.jsonl`: Ultra planned three leaves, Nano landed all three
in Sandboxes on first attempts, $0.11 with the planner, 542 s. It replays with no key and no network, and the leak
check counts no key, no project and no home path. Last night's take 6 (2 of 2, 203 s) stays the shipped Nemotron
demo unless Alex prefers take 2, which lands one leaf more: the brief asks.

**One take in six ran clean, end to end; two stopped at the planner on a fault Ultra wrote three times.** Last
night: three of six clean. The difference is the trees: tonight's Ultra put up five and seven leaves where last
night's put up two or three, and Nano stops where a leaf needs a file another leaf owns.
