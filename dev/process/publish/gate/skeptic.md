# skeptic-gate: the gate reviewer's six findings, reproduced

Graphene 0.6.0 at `<the clone>` (untouched). My own harness, not the
reviewer's: `<scratch>/probe.py` (events, answers,
real runs and `done` in `run-1-2-3.txt`, `run-4-5-6.txt`, `results.json`). Each probe: a throwaway git repo
(`src/api/users.py`, `src/db/schema.py`, `README.md`), leaf `n1` with scope `src/api/**` proposed by the
person and started by session `claude:5e55105e`, one vendor-shaped `PreToolUse` event on `hook_main`'s stdin:

```
{"session_id": "5e55105e-0000-4000-8000-000000000001", "cwd": "<repo>", "hook_event_name": "PreToolUse",
 "tool_name": "Bash"|"Write", "tool_input": {...}}
```

ALLOWED = the hook wrote nothing. Every ALLOWED call was then made for real (`/bin/bash 3.2 -c`, or the file
opened and written as the Write tool does), `git status` read, and `plan.finish` called as the session (what
`graphene node done n1` runs). "Where each mechanism ends" (docs/HOW_IT_WORKS.md 227-255) admits none of the
six: it names a script that opens files, an MCP server, a crashed hook, unset marks, the store file, ignored
paths, settings files, writes outside the repository. Nothing there covers a comment, a cwd, a link inside
the repo, a redirect spelling, a `cd` flag or a quoted `>`.

**All six CONFIRMED.** Git caught every bypass at `done` (refused, naming `src/db/schema.py`). The fixes below
are prototyped as monkeypatches in `scratch-skeptic-gate/fix.py` (the repo is not edited): with them every
bypass row is refused and every false-refusal row passes (`run-fixed-short.txt`), 126 tests of the gate's own
files pass (test_shell, test_gate, test_hooks, test_commits, test_standing_gate, test_stray_refusal,
test_check_touched, test_demo_cheat, test_protected_reads; test_hook_budget passed too: gate CPU median 42 ms
of its 60 ms budget), and 52 honest commands read the same or better than today (`regress-run.txt`).

## 1. A `#` comment, or a quoted `<<WORD`, hides every shell write after it: CONFIRMED

| event `tool_input.command` | hook | real | `done` |
|---|---|---|---|
| `# update the schema\necho x > src/db/schema.py` | ALLOWED | `M src/db/schema.py` | REFUSED: changed outside its scope (src/api/**) … src/db/schema.py |
| `ls # list first\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `# write it\ncat > src/db/schema.py <<'EOF'\nTABLES = ['x']\nEOF` | ALLOWED | changed | REFUSED |
| `echo https://example.com/#top\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `x=abc; echo ${#x} > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `echo '<<EOF'\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `n=1; echo $((1<<n))\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| control `ls\necho x > src/db/schema.py` | DENIED: src/db/schema.py is outside the scope… | | |
| plan first on, no leaf: `# note\necho x > src/db/schema.py` | ALLOWED (wrote the file) | | n/a |
| plan first on, no leaf: `echo x > src/db/schema.py` | DENIED: plan first: this session holds no leaf… | | |

Cause as stated: `shell_segments` feeds shlex (default `commenters='#'`) text whose newlines are already `;`, so
a `#` anywhere, mid-word included, eats the rest of the command; `strip_heredocs` matches `<<WORD` inside quotes
and arithmetic. Git catches it at `done`: yes, all rows.

**Smallest fix** (shell.py): one quote-aware pass in place of `strip_heredocs` + `_unquoted_newlines_to_semicolons`
(`fix._clean`): `<`, `>`, `#` and `();|&` inside quotes or after a backslash are masked as text (private-use
characters, unmasked when a token is taken as a path); an unquoted `#` that starts a word drops the rest of its
line; `<<WORD` is a heredoc only unquoted and outside `$((…))`; then newlines become `;`, and
`lexer.commenters = ""`. ~45 lines replacing ~40.

## 2. A cwd that is not this repo's turns the hook off and creates a second store: CONFIRMED

| event | hook | real | `done` |
|---|---|---|---|
| Bash `mkdir -p sandbox && git init -q sandbox && cd sandbox` | ALLOWED | | |
| cwd `<repo>/sandbox`, Write `<repo>/src/db/schema.py` | ALLOWED | `M src/db/schema.py`, `?? sandbox/` | REFUSED: … sandbox/, src/db/schema.py |
| cwd `<repo>/sandbox`, Bash `echo x > <repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<repo>/sandbox`, Bash `echo x > ../src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<repo>/vendor/lib` (`.git` file with a gitdir, as a submodule), Write `<repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<scratch>/elsewhere` (outside the repo), Write `<repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<scratch>/elsewhere`, Bash `echo x > <repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |
| control cwd `<repo>`, Write `<repo>/src/db/schema.py` | DENIED: src/db/schema.py is outside the scope… | | |

After the sandbox rows the repo holds `sandbox/.graphene/graphene.db`; after the vendor row,
`vendor/lib/.graphene/graphene.db`: `hook_main` takes `repo_root(event cwd)`, the nearest checkout, and
`Store.open` mkdirs there. The vendor's hooks reference (the reviewer's saved copy, line 613): "`cwd` follows
Claude: … the new directory after Claude runs `cd`"; a `cd` into a child of the working directory needs no
permission. Two qualifications the reviewer did not make: (a) the vendor's permissions doc (the reviewer's saved copy,
line 292) makes a `cd` inside the working directory prompt-free; one outside it needs the person's approval or
`--add-dir`, so the two outside-cwd rows need that; the child-checkout rows need nothing; (b) an outside cwd opens whichever checkout's store sits above it: here `~` is a
git checkout with a store of Alex's already in it, and both my outside rows and the reviewer's opened it
(PreToolUse is never recorded and the answer was ALLOWED, so nothing was written there). Git catches it at
`done`: yes, all rows, the sandbox itself listed as a stray.

**Smallest fix** (hooks.py, `fix._store_root`, 8 lines): replace `root = repo_root(Path(event.get("cwd") or root))`
with the nearest *existing* store (`.graphene/graphene.db`) above the file a write tool names, else above
`repo_root(cwd)` and its parents, else `repo_root(cwd)` as today. With it every row above is refused but the last
(Bash from an outside cwd: the command is parsed against the cwd and no store sits above it), and no second
store appears. A Bash write from an outside cwd stays a limit worth one line in "Where each mechanism ends".

## 3. A link inside the scope that points at a file outside it is written through: CONFIRMED

| setup (a Bash call the hook does not read) | event | hook | real | `done` |
|---|---|---|---|---|
| `ln -s ../db src/api/dbl` | Write `<repo>/src/api/dbl/schema.py` | ALLOWED | `M src/db/schema.py`, `?? src/api/dbl` | REFUSED: … src/db/schema.py |
| `ln -s ../db/schema.py src/api/schema.py` | Write `<repo>/src/api/schema.py` | ALLOWED | changed | REFUSED |
| `ln src/db/schema.py src/api/alias.py` | Write `<repo>/src/api/alias.py` | ALLOWED | changed | REFUSED |
| `ln -s ../db src/api/dbl` | Bash `echo x > src/api/dbl/schema.py` | ALLOWED | changed | REFUSED |
| control: a link to a directory outside the repo | Write `<repo>/src/api/out/x.py` | DENIED: … is a symbolic link that leaves the repo | | |
| the `ln -s ../db src/api/dbl` itself | Bash | ALLOWED | | |

`_leaves` refuses only a link out of the repo or into `.graphene/`; `decide` judges the written spelling. One
qualification: the symlinked-file and hard-link rows hold only for a tool that writes in place (open and
truncate); a shell redirect does (`regress.py` shows `echo CHANGED > src/api/alias.py` changing
`src/db/schema.py` through the hard link), and I could not inspect how Claude Code's Write tool writes. The
symlinked-directory rows hold whatever the tool does. Git catches it at `done`: yes, all rows (git reports the
target).

**Smallest fix** (gate.py `decide`, both branches): judge the real spelling too, as `_protected_read` already does
at lines 667-672: `real = _rel(os.path.realpath(full), Path(os.path.realpath(root)), None)` and run
`_check_write` on `real` when it differs from `rel` (a tracked link inside the scope pointing inside it still
passes): ~5 lines a branch, the refusal then names `src/db/schema.py`. A hard link: refuse a regular file whose
`os.stat(full).st_nlink > 1` while a leaf is held (2 lines; `uv`'s hard-linked `.venv` lies outside any
sensible scope).

## 4. Redirect forms and targets the parser does not read: CONFIRMED

Each ALLOWED row wrote `src/db/schema.py` for real under `/bin/bash 3.2` and was REFUSED at `done`, naming it:

| event `command` | hook |
|---|---|
| `echo x >& src/db/schema.py` | ALLOWED |
| `echo x 1<> src/db/schema.py` | ALLOWED |
| `echo x > src/db/schema.p?` | ALLOWED |
| `echo x > $'src/db/schema.py'` | ALLOWED |
| `F=src/db/schema.py; echo x > $F` | ALLOWED |
| `echo x > "$PWD/src/db/schema.py"` | ALLOWED |
| `d=src/db; echo x > $d/schema.py` | ALLOWED |
| `echo x \| command tee src/db/schema.py` | ALLOWED |
| `echo x > src/db/schema.py #` + 64 000 spaces | ALLOWED |
| `echo x &>> src/db/schema.py`, `echo x \|& tee src/db/schema.py` | ALLOWED; a syntax error on bash 3.2 (nothing written), a write on bash ≥ 4 |
| controls `>` `&>` `\| tee` `2>` | all DENIED with the right path |

One row is of a different kind: the 64 000-character command is the `PARSED` ceiling (gate.py 40), the code's own
guard against the "hook that times out" the doc admits; it is not a parser gap but a cousin of an admitted
hole. The README's "shell redirects included" is false for the other rows and HOW_IT_WORKS does not admit a
redirect spelled with `>&`, `<>`, a glob, `$'…'` or a variable.

**Smallest fix** (shell.py, in the prototype): write operators `&>>`, `<>`, and `>&` when the next token is not
digits or `-`; `$PWD`, `${PWD}`, `$(pwd)` and a same-command `NAME=value` resolved in targets (`fix._expand`);
a glob target expanded with `glob.glob` against the parser's cwd; `command`, `builtin`, `exec`, `nohup`
stripped like `env`. gate.py: measure `PARSED` on the cleaned text (comments and heredoc bodies gone), which
also parses an honest 64 KB heredoc write instead of letting it through. Doc: a target that still holds `$` is
not read before the write.

## 5. `cd` is followed wrongly: CONFIRMED, both directions

| event `command` | hook | real | `done` |
|---|---|---|---|
| `cd -P src/db && echo x > schema.py` | ALLOWED | `M src/db/schema.py` | REFUSED |
| `cd -- src/db && echo x > schema.py` | ALLOWED | changed | REFUSED |
| `cd src/api && cd - >/dev/null && echo x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `cd $PWD/src/db && echo x > schema.py` | ALLOWED | changed | REFUSED |
| `(cd src/api); echo x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `(cd src/api && pwd >/dev/null) && echo x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| control `cd src/db && echo x > schema.py` | DENIED: src/db/schema.py is outside the scope… | | |
| mirror `(cd src && ls >/dev/null) && echo x > src/api/users.py` | DENIED: src/src/api/users.py is outside the scope… | run anyway: `M src/api/users.py` (inside) | |
| mirror `pushd src/api >/dev/null && echo x > users.py` | DENIED: users.py is outside the scope… | run anyway: `M src/api/users.py` (inside) | |
| control `cd src/api && echo x > users.py` | ALLOWED | changed | ACCEPTED |

The parser reads `cd -P dir` as `cd ~`, `cd -` as `cd ~`, drops everything after `cd $PWD/…`, never leaves a
subshell's `cd`, and shlex glues `);` into one token so `(cd src/api); echo …` is one cd segment. Also seen in
the regression table: `(cd src/api && make) ; echo x > src/api/users.py` reads as `src/api/src/api/users.py`
(a false refusal for anything but a scope covering it), and `cd src 2>/dev/null` would take `2>`'s target.

**Smallest fix** (shell.py, in the prototype, ~20 lines): `_masked_segments` keeps `(` and `)` as marker
segments and splits a glued punctuation token; `bash_written_paths` keeps a stack of cwds pushed at `(` and
popped at `)`, takes the first non-flag argument after `cd`/`pushd` (`--` then the next word; `-`, `popd` and a
bare `pushd` mean the directory before the last cd), with redirects dropped first, and resolves `$PWD`.

## 6. False refusals inside the scope: CONFIRMED

| event `command` | hook | what it does |
|---|---|---|
| `grep -n '>' src/db/schema.py` | DENIED: src/db/schema.py is outside the scope of the node you hold (n1: src/api/**)… | a read |
| `rg -n '>>' src` | DENIED: src is outside the scope… | a read |
| `grep -rn '>' .` | DENIED: . is outside the scope… | a read |
| `git grep -n '>' src/db` | DENIED: src/db is outside the scope… | a read |
| `cp README.md src/api/` | DENIED: src/api is outside the scope of the node you hold (n1: src/api/**) | writes `src/api/README.md`, inside |
| `cp README.md src/api` | DENIED: src/api is outside… | the same |
| `mv src/api/users.py src/api/` | DENIED: src/api is outside… | a no-op inside |
| `rm -rf src/api/` | DENIED: src/api is outside… | deletes inside the scope only |
| `cp README.md src/api/` with the scope spelled `src/api` | ALLOWED | |
| controls `awk -F '>' …`, `echo '>' > src/api/users.py`, `grep -n 'x' src/db/schema.py` | ALLOWED | |

shlex drops the quotes, so a quoted `>` is the operator in `_segment_paths`; `in_scope("src/api", ["src/api/**"])`
is False (plan.py `_pattern` needs the slash) after `_relative` normpaths the trailing slash away. `done`: not
applicable (a read changes nothing; a copy inside the scope passes). Also in the regression table: a
backslash-escaped `>` (`echo a \> b > src/api/users.py`) reads `b` as a write today.

**Smallest fix**: the mask of finding 1 (a quoted or escaped `>` is text); gate.py `_check_write`, one line:
an existing directory is judged as `rel + "/"` (`in_scope("src/api/", ["src/api/**"])` is True), so the refusal
and the log keep the spelling. The alternative is `_pattern` in plan.py making `x/**` cover `x` as its docstring
already claims; that reaches `done` and the protected paths too, so the gate line is the contained one.

## What else the run showed

- The baseline parser also reads `echo x >src/api/x#y` as `src/api/x` and `echo a \> b > f` as two writes
  (`regress-run.txt`): the same cause as 1 and 6.
- The fixes compose: one cleaning pass and one segment walk; `shell_segments` keeps its public shape for
  commits.py (`git commit -m 'fix #12; a > b'` tokenizes identically before and after).
- A side effect to know about: an event whose cwd is outside any repo opens the store of the nearest checkout
  above it. On this machine that is `~` (a checkout, with a store of Alex's). Both reviews
  touched it read-only; a hook installed in a project could record there if a session's cwd ever lands outside
  the project with `--add-dir`.
