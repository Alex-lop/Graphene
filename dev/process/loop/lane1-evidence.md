# Lane 1: the loops closed

A loop is closed when a leaf that came back on a landed leaf's fault reopens the owner with `r`, the owner lands a
fix as a new commit on top of what landed, and the leaf that came back runs after it and lands. Every run below
was driven by `loop_take.py`, which presses on each leaf that came back the key a person in `graphene watch`
would: `r` when it is offered, else `w`. Paths of the scratch directory are written `<S>`.

## The scripted loop, at $0

`scripted-loop.sh`, on build `f7a9697`: a reader leaf whose executor lands `FIELDS = ["sku", "nam", "price"]`, and
a tests leaf that waits on it. The transcript, cut to the moves:

```
$ graphene run --parallel 2
red first: 2 checks at 94ea2a8 in 1 s
reader is done
tests handed back by the executor: the reader's field names are wrong (nam, not name); the fault is in reader.py
  widen tests's scope to __pycache__/reader.cpython-313.pyc: `graphene node widen tests`
  a sibling leaf for __pycache__/reader.cpython-313.pyc (its check: true); tests waits on it: `graphene node sibling tests`
  reopen reader with this reason; tests waits on it: `graphene node reopen reader --note 'came back from tests: the reader'"'"'s field names are wrong (nam, not name); the fault is in reader.py' --for tests`
run: 1 done, 1 came back (tests) · agents <1 min, no meter · you 0 acts, 0 min

$ loop_take.py
tests: pressed r (reopen reader with this reason; tests waits on it) -> exit 0: reader is open again; whoever takes it next is shown your note

$ graphene run --parallel 2
reader: its check passes at the base commit f116a79: it proves nothing; `graphene node set reader --check '…'` or e in watch
red first: 2 checks at f116a79 in 0 s
reader is done
tests is done
run: 2 done · agents <1 min, no meter · you 0 acts, 0 min

$ graphene node show reader
  attempt 1 · scripted-1.executor.sh · 1 s · no meter · exit 0
    its last lines:
      reader: the note says: came back from tests: the reader's field names are wrong (nam, not name); the fault is in reader.py
  what people did to it:
    2026-10-09T04:53:18.512Z  reopened  alexlopez (no terminal)  came back from tests: … (reopened after landing; the fix is a new commit)

$ git log --graph --oneline
*   4935e83 the reader (reader)
*   f116a79 the reader (reader)
* 94ea2a8 init
```

The first run of it, on build `f4f465f`, left the tests leaf alone after `r`: it already waited on the reader, so
no need changed, and it still read as "came back". Fixed at `f7a9697`: `r` is the person's answer to the hand-back,
as `w` and `b` are, and the leaf is waiting after it. The `__pycache__` offers are the scripted repo's: it has no
`.gitignore`.

## Nemotron, run 2 (natural): the loop closed

`loop-run.sh 2 nemotron 1`, build `f7a9697`: Ultra planned two leaves, `xml-feed` (the reader and the wiring) and
`xml-test` (an integration test, waiting on it); Nano did the leaves in Token Factory Sandboxes, Super on a retry.
The planner $0.16; the executors $0.23 in all; 958 s of wall time; recorded as `loop-nemotron-2.jsonl`.

1. `xml-feed` came back wanting `normalize/__init__.py` (the function it had to export lived there): `w`, and it landed on Super's attempt.
2. `xml-test` came back wanting `validate/rules.py` (price 0 not skipped: nobody's file): `w`, and it ran again.
3. `xml-test` came back on the landed leaf's fault: `normalize/fields.py` returns `price` where the rules and the test expect `price_cents`. The offers:

```
xml-test handed back by the executor: The normalize function in normalize/fields.py returns a dict with key 'price' (containing cents) but the validation rules and tests expect key 'price_cents'. …
  reopen xml-feed with this reason; xml-test waits on it: `graphene node reopen xml-feed --note 'came back from xml-test: The normalize function in normalize/fields.py returns a dict with key '"'"'price'"'"' …' --for xml-test`
run: 1 came back (xml-test) · agents 3 min, $0.0604 at list price · you 0 acts, 0 min

$ loop_take.py (round 3)
xml-test: pressed r (reopen xml-feed with this reason; xml-test waits on it) -> exit 0: xml-feed is open again; …

$ graphene run --parallel 4
red first: 2 checks at fd4b63a in 0 s
xml-feed started: XML reader + normalization wiring
xml-feed attempt 1: the executor ended (exit 0)
xml-feed is done
xml-test started: XML feed integration test
xml-test attempt 1: the executor ended (exit 0)
xml-test is done
run: 2 done · agents 4 min, $0.0228 at list price · you 0 acts, 0 min
```

Nano fixed the reader on its first attempt after the reopen (20 turns, $0.0077), reading the note as the first
line of its prompt; the test leaf then passed. **One owner reopened, one attempt, $0.0228 for the closing round.**
The feeds checks after it: accept 12 of 20, held-out 11 of 12.

## Claude Code, run 3 (planted): the loop closed

Three feeds runs on Claude Code (`claude 1`, `2`, `3`: 2, 2 and 3 leaves, every leaf landed, each leaf owning
its own tests, $0.30 to $0.44 a run) came back on nothing, so the fault was planted, as the directive allows:
`plant-run.sh 3 claude`, build `fa0ddc7`. Sonnet planned four nodes and did the two leaves ($0.31, both landed).
**At 01:13:42 the person committed a fault into the landed `normalize/fields.py`: the xml map's key for `sku`
misspelt (`"code"` → `"xcode"`), so XML records normalize to nothing.** Then one end-to-end tests leaf was
proposed and accepted (`e2e-xml`, scope `tests/test_e2e_xml.py`), and the run started:

```
red first: 1 checks at 34c444d in 0 s
e2e-xml handed back by the executor: normalize/fields.py FIELD_MAPS["xml"] maps sku to "xcode" but samples/prices.xml uses attribute "code" (commit 34c444d), so every record normalizes to None and load emits nothing; …
  widen e2e-xml's scope to normalize/fields.py: `graphene node widen e2e-xml`
  a sibling leaf for normalize/fields.py (its check: true); e2e-xml waits on it: `graphene node sibling e2e-xml`
  reopen xml-source with this reason; e2e-xml waits on it: `graphene node reopen xml-source --note 'came back from e2e-xml: …' --for e2e-xml`
run: 1 came back (e2e-xml) · agents <1 min, $0.1371 at list price · you 0 acts, 0 min

$ loop_take.py (round 1)
e2e-xml: pressed r (reopen xml-source with this reason; e2e-xml waits on it) -> exit 0: xml-source is open again; …

$ graphene run --parallel 4
red first: 2 checks at 34c444d in 0 s
xml-source started: Wire the XML feed into load
xml-source attempt 1: the executor ended (exit 0)
xml-source is done
e2e-xml started: the XML feed end to end
e2e-xml attempt 1: the executor ended (exit 0)
e2e-xml is done
run: 2 done · agents <1 min, $0.2380 at list price · you 0 acts, 0 min
```

`xml-source`'s second attempt (4 turns, $0.11) said: "I changed the `sku` key in `FIELD_MAPS["xml"]` from
`"xcode"` to `"code"`". `node show e2e-xml`: `edited … reopened xml-source for it; needs: [] -> ['xml-source']
(revision 2)`. **One owner reopened, one attempt, $0.238 for the closing round**; the whole run $0.78 with
the planner. Accept 18 of 20 after it. Recorded as `loop-claude-3.jsonl`.

## The count

| | loops closed | owners reopened | attempts per owner | $ per closing round |
|---|---|---|---|---|
| scripted | 1 | 1 | 1 | 0 |
| Nemotron, live, natural | 1 | 1 | 1 | 0.0228 |
| Claude Code, live, planted | 1 | 1 | 1 | 0.238 |

**Two loops closed live, one of them on a fault nobody planted. Before tonight: none.** What else the runs
showed: `r` is offered whenever a wanted path has a done owner, so a leaf that came back for a scope too narrow
onto a landed leaf's file offers `r` beside `w` and `b` (`planted-1`, `xml-reader`); the person reads the reason.
Ultra planned a tree with a tests leaf in 1 of 3 runs (run 3 planned one `explore` leaf and no work); Sonnet gave
every leaf its own test in 3 of 3, which is the rule the planners were taught last night, and is why the loop
needed a plant on Claude Code.
