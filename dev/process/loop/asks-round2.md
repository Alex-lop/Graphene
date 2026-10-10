# Lane 3, round 2: 40 asks on the final build

`asks.sh` as in round 1 (`asks-round1.md`), on the merged branch's build, after lane 3's review: every fault at once, sent back at most twice, mechanical faults repaired, a risk with options read as a question.

Build `ed97b4e`. **35 proposals in 40 asks** (feeds 17 of 20, report 18 of 20); 62 strict answers, 2 of them stalled to the token limit; $8.20.

| task | ask | proposal | leaves | board | answers | stalled | $ | s | what Graphene said |
|---|---|---|---|---|---|---|---|---|---|
| feeds | 1 | yes | 2 | 2 | 2 |  | 0.50 | 181 | after a send-back: line 13: then: 'drop xml-wiring: validate/rules.py' is not read; an effect is scope NODE + |
| feeds | 2 | yes | 5 |  | 1 |  | 0.26 | 163 |  |
| feeds | 3 | yes | 3 |  | 1 |  | 0.13 | 95 |  |
| feeds | 4 | yes | 4 | 3 | 2 |  | 0.52 | 168 | after a send-back: line 18: 'question: source-name' is a new leaf with no scope and no check |
| feeds | 5 | yes | 3 | 3 | 1 |  | 0.26 | 164 |  |
| feeds | 6 | yes | 4 | 3 | 1 |  | 0.48 | 163 |  |
| feeds | 7 | no |  |  | 3 | 1 | 0.43 | 219 | line 11: about: xmlfeed, which is not a node in the plan |
| feeds | 8 | yes | 3 | 2 | 2 |  | 0.64 | 130 | after a send-back: line 18 [xml-reader]: xml-reader: its check runs tests/test_xmlfeed.py, which test-xmlfeed |
| feeds | 9 | no |  |  | 3 |  | 0.06 | 26 | line 6 [xml-wiring]: xml-wiring and zero-price-skip both write normalize/fields.py. A path has one leaf that w |
| feeds | 10 | yes | 6 |  | 1 |  | 0.25 | 134 |  |
| feeds | 11 | yes | 6 |  | 3 | 1 | 0.44 | 196 | after a send-back: the text has no node in it, so nothing was applied |
| feeds | 12 | yes | 1 |  | 1 |  | 0.25 | 128 |  |
| feeds | 13 | yes | 1 |  | 3 |  | 0.34 | 136 | after a send-back: line 20 [q-xml-structure]: q-xml-structure and q-summary-line both write samples/, samples |
| feeds | 14 | yes | 3 |  | 1 |  | 0.26 | 127 |  |
| feeds | 15 | yes | 3 |  | 1 |  | 0.05 | 21 |  |
| feeds | 16 | no |  |  | 3 |  | 0.35 | 141 | line 29: 'question: what the words leave open and the repository cannot settle [q-xml-structure]' is a new lea |
| feeds | 17 | yes | 4 |  | 1 |  | 0.26 | 134 |  |
| feeds | 18 | yes | 5 | 3 | 1 |  | 0.26 | 134 |  |
| feeds | 19 | yes | 6 |  | 2 |  | 0.30 | 132 | after a send-back: line 6 [normalize-xml]: normalize-xml and price-zero-skip both write normalize/fields.py.  |
| feeds | 20 | yes | 3 |  | 1 |  | 0.14 | 74 |  |
| report | 1 | yes | 2 |  | 1 |  | 0.08 | 61 |  |
| report | 2 | yes | 2 |  | 1 |  | 0.05 | 36 |  |
| report | 3 | yes | 3 |  | 1 |  | 0.09 | 43 |  |
| report | 4 | yes | 3 |  | 2 |  | 0.22 | 85 | after a send-back: line 6 [json-tests]: json-tests and all-tests both write tests/test_report_json.py. A path |
| report | 5 | yes | 3 | 2 | 2 |  | 0.09 | 48 | after a send-back: line 13: 'question: what JSON types for units and revenue' is a new leaf with no scope and |
| report | 6 | yes | 3 |  | 1 |  | 0.11 | 64 |  |
| report | 7 | yes | 3 |  | 1 |  | 0.08 | 43 |  |
| report | 8 | yes | 3 |  | 1 |  | 0.20 | 79 |  |
| report | 9 | no |  |  | 3 |  | 0.10 | 48 | line 11: about: text-regression, which is not a node in the plan |
| report | 10 | yes | 2 |  | 1 |  | 0.07 | 36 |  |
| report | 11 | no |  |  | 3 |  | 0.11 | 54 | line 27: [regression-text] is on line 21 too. An [id] at the end of a line names one node: take it off the cop |
| report | 12 | yes | 3 |  | 2 |  | 0.07 | 36 | after a send-back: the text has no node in it, so nothing was applied |
| report | 13 | yes | 3 |  | 1 |  | 0.22 | 68 |  |
| report | 14 | yes | 3 |  | 1 |  | 0.08 | 44 |  |
| report | 15 | yes | 2 |  | 1 |  | 0.09 | 48 |  |
| report | 16 | yes | 3 |  | 2 |  | 0.06 | 31 | after a send-back: line 2 [rpt-json]: rpt-json and smoke both write app/report.py. A path has one leaf that w |
| report | 17 | yes | 2 |  | 1 |  | 0.06 | 39 |  |
| report | 18 | yes | 2 |  | 1 |  | 0.06 | 40 |  |
| report | 19 | yes | 3 |  | 1 |  | 0.08 | 47 |  |
| report | 20 | yes | 3 |  | 1 |  | 0.10 | 58 |  |
