# The numbers to beat

Written at 00:30 on 8 October, before any change, from the meter night's records:
`dev/process/meter/statements-practice.md`, `takes.md` and `auto-evidence.md`. Nothing here was run again.

## 1. Hand-backs over another leaf's file

A hand-back counts when a leaf came back because its check ran a file in another leaf's scope, or it
needed to write one. Last night 10 trees ran: 3 statements practice runs and the 7 Nemotron takes that
produced a tree. **8 of the 10 stopped on such a file. That is 8 hand-backs, 6 of them over a test file.**

| run | leaf | the file | how |
|---|---|---|---|
| statements 1 | `ledger` | `api/export.py`, `export-usd`'s | needed to write it |
| statements 2 | `half-even`, second time | `tests/test_statement.py`, another leaf's | needed to write it |
| statements 3 | `statement-sections` | `tests.test_dunning`, `reports-per-currency`'s | its check ran it |
| take 4 | the first leaf | a test file the other leaf writes | its check ran it |
| take 8 | the first leaf | the test file another leaf writes | needed it |
| take 9 | `xml-reader` | the test file `xml-tests` writes | its check ran it |
| take 12 | `json-fmt` | the test file `test-json` writes | its check needed it |
| take 17 | `xmlfeed` | a file `normalize-xml` writes | needed it |

Five more came back over test files outside their scope. Their records do not say whose the files were:
`verify` in statements 1 (`tests/test_cli.py`), `half-even`'s first time in statements 2 (four test files),
and `xml-feed` and `validation` in take 11 (their test folders). `validate-zero-price` in take 17 came back
for a reason the record does not give. None of these is counted above.

Two are not this cause. Take 6's test leaf came back because the Sandbox's Python had no pytest. Take 11's
`wiring` came back for `cli/main.py`, which the take prunes on purpose. The directive lists take 6 with
the others; its record says pytest.

**Leaves that never ran.** Statements 2 stopped at 3 of 7 leaves landed: `half-even` came back twice and
the 3 after it never started. Statements 3 left `no-mixing` and `e2e` unstarted. Statements 1's record
does not say.

## 2. The Nemotron planner's proposal rate

From `takes.md`. A take asks Ultra at most twice. "No proposal, twice" is 0 of 2.

**7 proposals in 34 asks (21%). By take, 7 of 19.**

- A tree at the first ask: takes 6, 9, 12 and 17. A tree at the second: takes 4, 8 and 11. The records
  of 9, 12 and 17 do not say "second try", so they count as one ask each.
- No proposal, twice: takes 1, 2, 3, 5, 7, 10, 13, 14, 15, 16, 19 and 21. That is 12 takes. The directive
  says 11; the record says 12.
- Why the 27 failed asks failed, where the record says: the plan's format broke in about 21 (markdown
  headings, JSON instead of the text, `<tool_call>` as text, a question with no words, a `needs:` naming
  no node, a cycle, a `then:` naming a file, prose under the plan, a `---`, an answer cut off). Ultra read
  until its step limit and never answered in 3 (take 1 twice, take 15 once). The first failed ask of
  takes 4, 8 and 11 is not described.

## 3. `auto` on the feeds paragraph

From `auto-evidence.md`, rounds C to E, the rule as it shipped. **A tree 1 time in 3.** Twice Sonnet
proposed one leaf of 8 paths with no board item, and `auto` took it at once. In rounds A and B, under the
first rule, the paragraph was one leaf too, in a sub-goal of its own: 1 tree in 5 proposals in all.

## What tonight compares against these

1. Lane 1: three statements practice runs and two feeds runs, counted the same way.
2. Lane 2: ten asks on feeds and ten on report, Ultra, counted the same way; then the takes.
3. Lane 3: the feeds paragraph under `on`, three asks: how many reach the person in `watch` before any work.
