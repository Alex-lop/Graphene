# Nemotron takes, 9 October

`dev/proof/nemotron.sh` as the last two nights ran it: Ultra plans (`nemotron --steps 60`); Nano, then Super on a
retry, do the leaves in Token Factory Sandboxes (`--placement sandbox --prepare 'pip install -q pytest'`); the
scripted prune takes `cli/main.py` out of every scope; the script widens a leaf that came back and runs again, up
to three times. Every take recorded, every row on the ledger under `takes`. Takes 1 to 4 ran on lane 3's build
before its review (`7b6d2f6`): every fault at once, sent back at most twice, mechanical faults repaired.

A clean take, as the directive has it: every leaf landed, or came back for a reason the person would accept.

| take | task | the plan (Ultra) | what happened |
|---|---|---|---|
| 1 | feeds | 3 leaves, $0.17 | `xml-reader` came back twice: for the test file it had to write and did not own (widened), then for `normalize/fields.py`, which `normalize-config` owned (not offered). 0 of 3 landed. Not clean. |
| 2 | report | 3 leaves, $0.11 | All three landed on Nano's first attempts: 22 calls, $0.009, 542 s. **Clean, end to end.** |
| 3 | feeds | no proposal | Three answers, each with the same fault: an `option:` under a `risk:`. The validator sent it back twice with every fault listed; Ultra wrote it again. $0.17. |
| 4 | report | 3 leaves, $0.09 | `impl` and `test-json` landed; `test-text` came back saying the implementation was missing, which had landed. Nano misread its leaf. Not clean. |

(takes 5 and 6 on the final build follow)
