# The messages, before and after

Each message item of the directive, in a fresh repository of its own, run with `graphene` at
`2c86399` (before) and on this branch (after): `harness/items.sh <graphene> <dir>`. An agent is a
shell with Claude Code's marks; the person is one without them. `<repo>` stands for the path.

## 1. parent: places or is refused

before

```
$ graphene plan propose -   # an agent
goal (proposed): calc does subtraction
proposed wire: wire it in
proposed keep: add is kept
proposed sub: sub is added
3 proposed. The person sees them now (`graphene watch`, `graphene plan`) and accepts or prunes them; nobody can start them before that. Tell them the tree is ready, and stop
  (the plan of <repo>/parent)

$ graphene plan --text   # the person
goal: calc does subtraction
# proposed with the tree: accepting any of it accepts this

? wire it in  [wire]
    # 0/1 done
  ? add is kept  [keep]
      # proposed by claude:agent-se
      scope: calc.py
      check: python3 -m unittest -q
? sub is added  [sub]
    # proposed by claude:agent-se
    parent: wire
    scope: calc.py, tests/test_calc.py
    check: python3 -m unittest -q
```

after

```
$ graphene plan propose -   # an agent
goal (proposed): calc does subtraction
proposed wire: wire it in
proposed keep: add is kept
proposed sub: sub is added
3 proposed: nobody can start them until the person accepts, in `graphene watch`. Tell them the tree is ready, and stop
  (the plan of <repo>/parent)

$ graphene plan --text   # the person
goal: calc does subtraction
# proposed with the tree: accepting any of it accepts this

? wire it in  [wire]
    # proposed by a Claude Code session (agent-se)
  ? add is kept  [keep]
      # proposed by a Claude Code session (agent-se)
      scope: calc.py
      check: python3 -m unittest -q
  ? sub is added  [sub]
      # proposed by a Claude Code session (agent-se)
      scope: calc.py, tests/test_calc.py
      check: python3 -m unittest -q
```

## 2. the check's own leftovers (a Python repo with no .gitignore)

before

```
$ printf 'def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n' > calc.py; python3 -m unittest -q 2>&1 | tail -1; git status --short
OK
 M calc.py
?? __pycache__/
?? tests/__pycache__/

$ graphene node done sub   # an agent
sub is not done: changed outside its scope (calc.py, tests/test_calc.py): __pycache__/calc.cpython-313.pyc, tests/__pycache__/__init__.cpython-313.pyc, tests/__pycache__/test_calc.cpython-313.pyc. Put those back as they were (`git checkout <base> -- <path>`, or delete a new file), or say why the scope is wrong: `graphene node release sub --why '…'`. Only the person widens a scope, and only they decide a build leftover belongs in .gitignore
```

after

```
$ printf 'def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n' > calc.py; python3 -m unittest -q 2>&1 | tail -1; git status --short
OK
 M calc.py
?? __pycache__/
?? tests/__pycache__/

$ graphene node done sub   # an agent
sub is done (check passed, nothing outside its scope)
next: mul (mul is added) is ready: `graphene node start mul` takes it, with its contract as it stands now
  (the plan of <repo>/leftovers)
```

## 3. a person's commit is not a loose change

before

```
$ printf '__pycache__/\n' > .gitignore && git add .gitignore && git commit -qm 'ignore caches' && git log --oneline | head -1
0168dd2 ignore caches

$ graphene node start mul   # an agent
mul cannot start: .gitignore changed while no node owned it. Put it back, or tell the person: `graphene plan ack` is theirs to run if the change is theirs
```

after

```
$ printf '__pycache__/\n' > .gitignore && git add .gitignore && git commit -qm 'ignore caches' && git log --oneline | head -1
d8f36d8 ignore caches

$ graphene node start mul   # an agent
mul (revision 1): mul is added
  goal:   mul is added
  scope:  calc.py, tests/test_calc.py   (a write anywhere else is refused, and blocks `done`)
  needs:  sub   (it cannot start until they are done)
  done:   `python3 -m unittest -q` passes
  finish: graphene node done mul   (runs the check and asks git what changed)
  stuck:  graphene node release mul --why '<what is in the way>' [--wants <paths it needs>]   (hands it back; say why)
  (the plan of <repo>/commit)
```

## 4. a refusal, said the first time and the second

before

```
$ graphene node done sub   # an agent
sub is not done: changed outside its scope (calc.py, tests/test_calc.py): NOTES.txt. Put those back as they were (`git checkout <base> -- <path>`, or delete a new file), or say why the scope is wrong: `graphene node release sub --why '…'`. Only the person widens a scope, and only they decide a build leftover belongs in .gitignore

$ graphene node done sub   # an agent
sub is not done: changed outside its scope (calc.py, tests/test_calc.py): NOTES.txt. Put those back as they were (`git checkout <base> -- <path>`, or delete a new file), or say why the scope is wrong: `graphene node release sub --why '…'`. Only the person widens a scope, and only they decide a build leftover belongs in .gitignore
```

after

```
$ graphene node done sub   # an agent
sub is not done: changed outside its scope (calc.py, tests/test_calc.py), which only the person widens
  NOTES.txt
  put it back (git checkout 246a878e25 -- <path>, or delete a new file), or say why: graphene node release sub --why '…'

$ graphene node done sub   # an agent
sub is not done: changed outside its scope (calc.py, tests/test_calc.py)
  NOTES.txt
  put it back, or say why: graphene node release sub --why '…'
```

## 5. start and done on a leaf that waits on a running one

before

```
(a second agent) mul waits on sub (running)

(a second agent) mul is open, not running; `graphene node start mul` takes it
```

after

```
(a second agent) mul waits on sub (running)

(a second agent) mul is not running: it waits on sub (running)
```

## 6. next: after a hand-back, with nothing else ready

before

```
$ graphene node release sub --why the spec is ambiguous about floats   # an agent
sub handed back: the spec is ambiguous about floats
  (the plan of <repo>/next)
next: nothing is ready for you: sub is back with the person, who reads why you handed it back; mul waits on sub (open); docs waits on mul (open); log waits on mul (open). You can stop: the rest waits for a person, and `graphene plan` shows them that
```

after

```
$ graphene node release sub --why the spec is ambiguous about floats   # an agent
sub handed back: the spec is ambiguous about floats
next: nothing is ready for you, so you can stop (graphene plan says what each leaf waits on)
  (the plan of <repo>/next)
```

## 7. reopen with no note

before

```
$ graphene node reopen sub   # the person
Usage: graphene node reopen [OPTIONS] {node_id}
Try 'graphene node reopen --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Missing option '--note'.                                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
```

after

```
$ graphene node reopen sub   # the person
graphene node reopen sub needs --note: what is wrong
```

## 8. which repository, on every write

before

```
$ graphene plan goal calc does subtraction   # the person
  (the plan of <repo>/where)
the plan: calc does subtraction

$ graphene node add sub is added --id sub --scope calc.py --check true   # the person
sub  open  sub is added
  (the plan of <repo>/where)

$ graphene node set sub --check python3 -m unittest -q   # the person
  (the plan of <repo>/where)
sub is now revision 2:
  check: 'true' -> 'python3 -m unittest -q'

$ graphene node drop sub   # the person
  (the plan of <repo>/where)
sub dropped (`graphene plan undo` puts it back)

$ graphene plan undo   # the person
undid: node drop sub
  (the plan of <repo>/where)
```

after

```
$ graphene plan goal calc does subtraction   # the person
the plan: calc does subtraction
  (the plan of <repo>/where)

$ graphene node add sub is added --id sub --scope calc.py --check true   # the person
○ sub is added  sub  ready
  (the plan of <repo>/where)

$ graphene node set sub --check python3 -m unittest -q   # the person
sub is now revision 2:
  check: true → python3 -m unittest -q
  (the plan of <repo>/where)

$ graphene node drop sub   # the person
sub dropped (`graphene plan undo` puts it back)
  (the plan of <repo>/where)

$ graphene plan undo   # the person
undid: node drop sub
  (the plan of <repo>/where)
```

## 9. graphene, with no plan

before

```
$ graphene    # the person
no plan here yet. `graphene node add '<what>' --scope '<paths>' --check '<command>'` starts one, or ask your agent to propose one; `graphene plan --help` has the rest.
```

after

```
$ graphene    # the person
nothing is planned here yet. Say what you want to your agent, in a paragraph: it proposes the tree, and you prune it in `graphene watch`. Or `graphene ask '<what you want>'`
```

## 10. graphene plan: the row grammar

before

```
$ graphene plan   # the person
the plan: 3 leaves, 0 done, 0 running
  sub   open      sub is added  agent  calc.py, tests/test_calc.py  ·  ready
  mul   waiting   mul is added  agent  calc.py, tests/test_calc.py  ·  waits on sub
  docs  waiting   docs say so   agent  README.md                    ·  waits on mul
```

after

```
$ graphene plan   # the person
the plan: 3 leaves, 0 done, 0 running
  ○ sub is added  sub   ready    · calc.py, tests/test_calc.py
  ◌ mul is added  mul   waiting  · calc.py, tests/test_calc.py · waits on sub (ready)
  ◌ docs say so   docs  waiting  · README.md · waits on mul (waiting)
```

## 11. a missing option or argument

before

```
$ graphene node show   # the person
Usage: graphene node show [OPTIONS] {node_id}
Try 'graphene node show --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Missing argument 'node_id'.                                                  │
╰──────────────────────────────────────────────────────────────────────────────╯

$ graphene node release sub   # the person
Usage: graphene node release [OPTIONS] {node_id}
Try 'graphene node release --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Missing option '--why'.                                                      │
╰──────────────────────────────────────────────────────────────────────────────╯
```

after

```
$ graphene node show   # the person
graphene node show needs <node_id>

$ graphene node release sub   # the person
sub is open, not running
```
