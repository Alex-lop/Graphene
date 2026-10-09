# Lane 3, round 1: 40 asks on lane 3's build before its review

`asks.sh`: `graphene ask` with `nemotron --steps 60` (Ultra), twenty times on feeds (nemotron.sh's paragraph) and twenty on report (`dev/test/tasks/report/paragraph.md`), each in a fresh repo, one after another. An ask is one start with at most three answers: the second and third after Graphene's send-backs, every fault listed. Rows by `ask_row.py`, the table by `asks_table.py`.

Build `7b6d2f6`. **30 proposals in 40 asks** (feeds 12 of 20, report 18 of 20); 82 strict answers, 12 of them stalled to the token limit; $10.23.

| task | ask | proposal | leaves | board | answers | stalled | $ | s | what Graphene said |
|---|---|---|---|---|---|---|---|---|---|
| feeds | 1 | yes | 2 | 1 | 3 |  | 0.42 | 161 | after a send-back: line 10 [xmlfeed]: xmlfeed: its check runs tests/test_xmlfeed.py, which xmlfeed-test write |
| feeds | 2 | yes | 4 | 3 | 1 |  | 0.10 | 67 |  |
| feeds | 3 | yes | 3 | 3 | 2 |  | 0.62 | 186 | after a send-back: line 34 [leaf-wiring]: leaf-wiring and leaf-normalize both write normalize/fields.py. A pa |
| feeds | 4 | yes | 4 | 2 | 1 |  | 0.13 | 86 |  |
| feeds | 5 | no |  |  | 3 |  | 0.38 | 117 | line 28 [skip-zero-price]: skip-zero-price and leaf-validate both write validate/rules.py. A path has one leaf |
| feeds | 6 | yes | 3 | 2 | 2 |  | 0.16 | 112 | after a send-back: line 15: 'question' is a new leaf with no scope and no check |
| feeds | 7 | yes | 2 | 1 | 3 |  | 0.70 | 155 | after a send-back: line 10 [xml-feed]: xml-feed: its check runs tests/test_xmlfeed.py, which xml-test writes  |
| feeds | 8 | no |  |  | 3 |  | 0.34 | 185 | line 22: then: scope xml-test + tests/test_xmlfeed.py names xml-test, which is not a node in the plan |
| feeds | 9 | yes | 4 | 3 | 1 |  | 0.44 | 143 |  |
| feeds | 10 | no |  |  | 3 |  | 0.35 | 140 | line 21: option: is a question's; a risk has a default: at most |
| feeds | 11 | yes | 4 | 3 | 3 | 1 | 0.50 | 144 | after a send-back: line 26: 'question: source-name [src-name]' is a new leaf with no scope and no check |
| feeds | 12 | yes | 4 | 3 | 3 |  | 0.34 | 142 | after a send-back: line 22 [xmlfeed]: xmlfeed: its check runs samples/northwind.xml, which test-xml writes af |
| feeds | 13 | no |  |  | 3 | 3 | 0.44 | 258 | its answers stalled to the token limit: no JSON to read |
| feeds | 14 | no |  |  | 3 |  | 0.34 | 139 | line 5: about: xmlfeed-leaf, which is not a node in the plan |
| feeds | 15 | no |  |  | 3 |  | 0.53 | 155 | line 26 [xmlfeed]: xmlfeed: its check runs tests/test_xmlfeed.py, which tests writes after it. Give xmlfeed a  |
| feeds | 16 | no |  |  | 5 | 4 | 0.73 | 275 | line 28 [xmlfeed-leaf]: xmlfeed-leaf and contract-leaf both write cli/main.py, config/defaults.py. A path has  |
| feeds | 17 | no |  |  | 3 | 1 | 0.44 | 194 | line 17: option: is a question's; a risk has a default: at most |
| feeds | 18 | yes | 1 | 1 | 2 | 1 | 0.08 | 40 |  |
| feeds | 19 | yes | 3 | 3 | 1 |  | 0.28 | 86 |  |
| feeds | 20 | yes | 3 | 3 | 2 | 1 | 0.78 | 220 |  |
| report | 1 | yes | 2 |  | 1 |  | 0.07 | 51 |  |
| report | 2 | yes | 4 |  | 3 | 1 | 0.25 | 132 | after a send-back: line 2 [1]: 1 and 4 both write app/report.py. A path has one leaf that writes it: give it  |
| report | 3 | no |  |  | 3 |  | 0.24 | 138 | line 6 [add-json-tests]: add-json-tests and run-all-tests both write tests/test_report_json.py. A path has one |
| report | 4 | yes | 3 |  | 2 |  | 0.24 | 87 | after a send-back: line 6 [add-json-test]: add-json-test and run-all both write tests/test_report_json.py. A  |
| report | 5 | yes | 3 |  | 1 |  | 0.08 | 41 |  |
| report | 6 | yes | 2 | 3 | 2 |  | 0.11 | 55 | after a send-back: line 22: 'question' is a new leaf with no scope and no check |
| report | 7 | yes | 3 |  | 1 |  | 0.04 | 17 |  |
| report | 8 | no |  |  | 3 |  | 0.11 | 61 | line 24 [verify]: verify: a leaf needs a scope (the paths it may touch), e.g. --scope 'src/api/**'; or give it |
| report | 9 | yes | 1 | 2 | 3 |  | 0.07 | 37 | after a send-back: line 14: 'question: json-style' is a new leaf with no scope and no check |
| report | 10 | yes | 3 |  | 1 |  | 0.08 | 38 |  |
| report | 11 | yes | 3 |  | 1 |  | 0.17 | 68 |  |
| report | 12 | yes | 3 |  | 1 |  | 0.06 | 32 |  |
| report | 13 | yes | 3 |  | 2 |  | 0.10 | 53 | after a send-back: line 11 [regress-text]: regress-text: a leaf needs a scope (the paths it may touch), e.g.  |
| report | 14 | yes | 2 |  | 1 |  | 0.09 | 49 |  |
| report | 15 | yes | 3 |  | 1 |  | 0.09 | 51 |  |
| report | 16 | yes | 2 |  | 1 |  | 0.07 | 36 |  |
| report | 17 | yes | 3 |  | 1 |  | 0.07 | 37 |  |
| report | 18 | yes | 3 |  | 1 |  | 0.06 | 28 |  |
| report | 19 | yes | 3 | 2 | 2 |  | 0.09 | 62 | after a send-back: line 14: 'question: json-style' is a new leaf with no scope and no check |
| report | 20 | yes | 2 |  | 1 |  | 0.08 | 45 |  |
