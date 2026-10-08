# Nemotron takes, 8 October

`dev/proof/nemotron.sh` as last night ran it: Ultra plans (`nemotron --steps 60`); Nano, then Super on a retry, do
the leaves in Token Factory Sandboxes (`--placement sandbox --prepare 'pip install -q pytest'`); the scripted prune
takes `cli/main.py` out of every scope; the script widens a leaf that came back and runs again, up to three times.
Every take recorded, every row on the ledger under `takes`. Feeds asks nemotron.sh's paragraph; report asks
`dev/test/tasks/report/paragraph.md`.

A clean take, as the directive has it: every leaf landed, or came back for a reason the person would accept.

| take | task | build | the plan (Ultra) | what happened |
|---|---|---|---|---|
| 1 | feeds | `4490656` | 4 leaves, 3 board items, $0.34 | 3 landed. `wire-xml-feed` came back for `cli/main.py`, the path the take prunes; widened, it landed. `test-xmlfeed-e2e` came back: the reader returns the normalized field names and normalize expects the supplier's, a fault in `xmlfeed-reader`'s file. Super stepped in on a retry. Executors $0.12. **Clean.** |
| 2 | report | `ea8ae71` | 3 leaves, $0.10 | 2 landed. `text-regress`, scoped to `tests/test_report.py`, asked for `app/report.py`, which `json-fmt` had already changed and landed: Nano misread its leaf. Executors $0.007. Not clean. |
| 3 | feeds | `674754d` | 2 leaves, 3 board items, $0.55 | `xmlfeed` came back for `cli/main.py`, the pruned path; widened, it landed. `test-xmlfeed` came back: `xmlfeed` does not skip a price of 0, a fault in `xmlfeed`'s file. Executors $0.15. **Clean.** |
| 4 | report | `674754d` | no proposal | The second answer still had two leaves writing `app/report.py`. |
| 5 | feeds | `674754d` | no proposal | A `then:` line named `validate/rules`, a path, as a node: the board came before the nodes it names, which `674b32c` fixes. |
| 6 | report | `674754d` | 2 leaves, $0.10 | Both landed on their first attempt: Nano in Sandboxes, 16 calls, $0.0048, 203 seconds in all. **Clean, end to end.** |

**Kept:** take 6, as `tests/recordings/timeline-nemotron-take-6.jsonl`. It replays with no key and no network, and the
leak check counts no key, no project and no home path. Ultra planned it (19 calls, $0.0972); Nano did both leaves.

**Three takes in six ran clean; take 6 landed every leaf.** Last night none of 19 did. Two takes stopped at the
planner, both on the build before the nodes came first in the answer.
