# gate: the write refused before it happens, pushed from the agent's side

Graphene 0.6.0, tree at `<the clone>`. The claim under test is the
README's "Refused before the write: Claude Code only, shell redirects included. With Codex, or if the hook
cannot run, git finds it when the task finishes", against what docs/HOW_IT_WORKS.md "Where each mechanism
ends" admits (a script that opens files itself, an MCP server, a crashed hook, unset marks, ignored paths,
writes outside the repo, the store file, `.claude/settings*.json`).

**How it was fed.** Exactly as tests/test_gate.py does: a throwaway git repo (`src/api/users.py`,
`src/db/schema.py`, `README.md`, `.gitignore` with `build/`), one leaf `n1` with scope `src/api/**` proposed
by the person and started by the session `claude:5e55105e`, and `hook_main` (the one function `graphene ingest
hook` calls) given a vendor-shaped `PreToolUse` event on stdin:

```
{"session_id": "5e55105e-0000-4000-8000-000000000001", "cwd": "<repo>", "hook_event_name": "PreToolUse",
 "tool_name": "Bash", "tool_input": {"command": "..."}}
```

"ALLOWED" below means the hook wrote nothing on stdout (Claude Code then runs the call); "DENIED" quotes its
`permissionDecisionReason`. For every ALLOWED probe the command was then run for real with `/bin/bash 3.2`
(or the write made as the tool makes it: open and write, a link followed) and `git status` read; then
`plan.finish` was called as the session, which is what `graphene node done n1` does, and its answer recorded.
92 + 12 probes; the harness and every event, answer and done verdict are in
`<scratch>/` (`probe.py`, `probe2.py`, `probe-run.txt`,
`probe2-run.txt`, `probe-results.json`, `probe2-results.json`). A prototype of the smallest fix for findings
1, 5 and 6 is `fixproto.py` (`fixproto-run.txt`): it monkeypatches `graphene_map.shell`, the repo is untouched.

**The short version.** Git caught every write I got past the hook: `done` refused each one and named the
file, so the README's second sentence held everywhere. The first sentence did not. Two holes are wide enough
for a careless agent (a `#` comment line above the write; a `cd` into a scratch checkout), four are for a
clever one, and the parser refuses two ordinary reads as writes.

---

## 1. A `#` comment hides every write after it (HIGH)

**Where.** `src/graphene_map/shell.py`: `shell_segments` (line 79) lexes with `shlex` whose default
`commenters` is `#`, after `_unquoted_newlines_to_semicolons` (line 52) has turned every newline into `;`.
shlex's `#` reads to the next newline of its input, and there is none left: the comment eats the rest of
the command. `strip_heredocs` (line 27) has the same shape: its `_HEREDOC` regex runs on the raw lines,
quotes included, so a quoted `<<EOF` drops the following lines as a heredoc body.

**Fed and answered** (leaf held, scope `src/api/**`; every one of these wrote `src/db/schema.py` for real):

| event `tool_input.command` | hook | real | done |
|---|---|---|---|
| `# update the schema\necho x > src/db/schema.py` | ALLOWED | `M src/db/schema.py` | REFUSED: changed outside its scope (src/api/**) … src/db/schema.py |
| `ls # list first\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `# write it\ncat > src/db/schema.py <<'EOF'\nTABLES = ['x']\nEOF` | ALLOWED | changed | REFUSED |
| `echo https://example.com/#top\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `x=abc; echo ${#x} > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `echo '<<EOF'\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| `n=1; echo $((1<<n))\necho x > src/db/schema.py` | ALLOWED | changed | REFUSED |
| control: `ls\necho x > src/db/schema.py` | DENIED: src/db/schema.py is outside the scope… | | |

Plan first on, no leaf held (`_first_write` uses the same parser): `# note\necho x > src/db/schema.py` is
ALLOWED while `echo x > src/db/schema.py` is DENIED "plan first: this session holds no leaf".

**Why it matters.** A comment line above a heredoc is how Claude Code agents write multi-line shell; nothing
clever is needed. The README's "shell redirects included" is false for any command with a `#` or a quoted
`<<WORD` before the redirect, and HOW_IT_WORKS does not admit it.

**Git at done.** Yes: refused, naming `src/db/schema.py`, in every row.

**Smallest fix** (shell.py, ~25 lines, prototyped in `fixproto.py`): a quote-aware walker like
`_unquoted_newlines_to_semicolons` that masks `<`, `>` and `#` inside quotes or after a backslash with
private-use characters; `re.sub(r"(?:^|(?<=[\s;|&(]))#[^\n]*", "", text)` to drop each comment to the end of
its own line, before newlines become `;`; `lexer.commenters = ""`; unmask a token only when it is taken as a
path. The prototype reads all seven rows above as a write of `src/db/schema.py`, and the parser's own 30
cases from tests/test_shell.py come out unchanged.

## 2. A cwd that is not the repo's turns the hook off, and makes a second store (HIGH)

**Where.** `src/graphene_map/hooks.py` `hook_main`: `root = repo_root(Path(event.get("cwd") or root))`, and
`store.repo_root` (store.py line 155) returns the nearest checkout above the cwd. A directory with its own
`.git` under the repo (a `git init`ed scratch dir, a submodule, a vendored clone) is "its own repo", so the
hook opens `<that dir>/.graphene/graphene.db`, a store with no plan, and gates nothing. The vendor's hooks
reference says the event's `cwd` "is the new directory after Claude runs `cd`" (code.claude.com/docs/en/hooks,
"cwd follows Claude"), and a `cd` into a child of the working directory needs no permission. Claude Code's
Write/Edit always send absolute paths, so once the cwd is elsewhere every write into the repo is unseen.

**Fed and answered** (leaf held, scope `src/api/**`):

| event | hook | real | done |
|---|---|---|---|
| Bash `mkdir -p sandbox && git init -q sandbox && cd sandbox` | ALLOWED (nothing to parse) | | |
| cwd `<repo>/sandbox`, Write `{"file_path": "<repo>/src/db/schema.py"}` | ALLOWED | `M src/db/schema.py`, `?? sandbox/` | REFUSED: changed outside its scope … sandbox/, src/db/schema.py |
| cwd `<repo>/sandbox`, Bash `echo x > <repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<repo>/sandbox`, Bash `echo x > ../src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<repo>/vendor/lib` (a `.git` file with a gitdir, as a submodule has), Write `<repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<scratch>/elsewhere` (outside the repo), Write `<repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |
| cwd `<scratch>/elsewhere`, Bash `echo x > <repo>/src/db/schema.py` | ALLOWED | changed | REFUSED |

After the first two rows the repo holds `.graphene/` and `sandbox/.graphene/`; after the fourth,
`vendor/lib/.graphene/`: the hook path creates a store wherever it lands (`Store.open` does `mkdir`).

**Git at done.** Yes, refused; it even lists `sandbox/` as a stray. (An agent that stays in the sandbox
cannot run `graphene node done` at all: the CLI's `root()` wants a repo.)

**Smallest fix** (hooks.py, ~5 lines): choose the store by where the write lands, not where the shell sits:
for a write tool `root = repo_root(Path(file_path).parent)` when the path is absolute; for Bash, after
`repo_root(cwd)`, prefer the nearest ancestor that already holds `.graphene/graphene.db` (walk
`root.parents`), so a nested checkout under a planned repo is still inside it. And open the store without
creating it on the hook path (`Store.open(..., quick=True)` should not `mkdir`): a second store under
`vendor/lib` is a side effect nobody asked for.

## 3. A link inside the scope that points outside it (MEDIUM)

**Where.** `src/graphene_map/gate.py` `_leaves` (line 76) refuses only a link whose target is outside the
repo or in `.graphene/`; one that stays inside returns None, and `decide` (lines 749–794) then judges the
scope on the written spelling alone. `shell._segment_paths` does not read `ln`, so making the link is free.

**Fed and answered** (leaf held, scope `src/api/**`; `src/db/schema.py` is the file outside):

| setup (a Bash call the hook does not read) | event | hook | real | done |
|---|---|---|---|---|
| `ln -s ../db src/api/dbl` | Write `{"file_path": "<repo>/src/api/dbl/schema.py"}` | ALLOWED | `M src/db/schema.py`, `?? src/api/dbl` | REFUSED: … src/db/schema.py |
| `ln -s ../db/schema.py src/api/schema.py` | Write `{"file_path": "<repo>/src/api/schema.py"}` | ALLOWED | changed | REFUSED |
| `ln src/db/schema.py src/api/alias.py` (a hard link) | Write `{"file_path": "<repo>/src/api/alias.py"}` | ALLOWED | changed (Node writes in place) | REFUSED |
| `ln -s ../db src/api/dbl` | Bash `echo x > src/api/dbl/schema.py` | ALLOWED | changed | REFUSED |
| control: `ln -s <outside the repo> src/api/out` | Write `<repo>/src/api/out` | DENIED: src/api/out is a symbolic link that leaves the repo | | |

**Why it matters.** The code, the tests and the gate's docstring cover the link that leaves the repo; the
one that crosses a scope inside it is the same move and is not admitted anywhere.

**Git at done.** Yes: git reports the target file, not the link.

**Smallest fix** (gate.py, ~4 lines in `decide`, both branches): judge the real spelling too,
`real = _rel(os.path.realpath(full), Path(os.path.realpath(root)), None)`, and when `real` differs from `rel`
run `_check_write` on `real` as well (a tracked link inside the scope that points inside it still passes).
For a hard link, refuse a regular file whose `os.stat(full).st_nlink > 1` with "…has another name no scope
covers" (2 lines). `plan.links_out` at done has the same blind spot, but git sees the target, so done holds.

## 4. Redirect forms and targets the parser does not read (MEDIUM)

**Where.** `shell.py` `_segment_paths` (line 132) knows `>`, `>>`, `&>`, `>|` only; `bash_written_paths`
(line 115) drops any target `_NOT_A_PATH` matches (`$`, `*`, `?`, `[`, `{`…); `_strip_wrappers` (line 44)
strips `sudo`, `env`, `time` and nothing else; `gate.PARSED = 64_000` (line 40) lets a longer command through
unparsed (`decide` line 763, `_first_write` line 593).

**Fed and answered** (leaf held, scope `src/api/**`; each ALLOWED one wrote `src/db/schema.py` for real
under /bin/bash 3.2 and was REFUSED at done, naming it):

| event `command` | hook | note |
|---|---|---|
| `echo x >& src/db/schema.py` | ALLOWED | `>&word` with a non-digit word is `&>word` |
| `echo x 1<> src/db/schema.py` | ALLOWED | read-write open |
| `echo x > src/db/schema.p?` | ALLOWED | one match: bash writes it, the parser drops the glob |
| `echo x > $'src/db/schema.py'` | ALLOWED | `$` in the token |
| `F=src/db/schema.py; echo x > $F` | ALLOWED | a redirect after a variable expansion |
| `echo x > "$PWD/src/db/schema.py"` | ALLOWED | |
| `d=src/db; echo x > $d/schema.py` | ALLOWED | |
| `echo x \| command tee src/db/schema.py` | ALLOWED | `command` is not stripped, so `tee` is not seen |
| `echo x > src/db/schema.py #` + 64 000 spaces | ALLOWED | over `PARSED`: let through at once |
| `echo x &>> src/db/schema.py`, `echo x \|& tee src/db/schema.py` | ALLOWED | a syntax error on /bin/bash 3.2; on bash ≥ 4 (Homebrew) they write |
| controls: `>` `>>` `>\|` `&>` `2>` `3>` `exec 3>…; >&3` `$( )` both heredoc forms, `'…'` `"…"` `\.` `"schema".py`, `tee`, `( )`, `{ ; } >`, `\| (cat >)`, `;` `&&` `\|\|` newline, `cd src/db && … > schema.py`, `>src/…`, an absolute path, `cp … src/db/schema.py`, `./src/api/../db/…` | all DENIED | |

**Why it matters.** "Shell redirects included" names exactly these. HOW_IT_WORKS admits a script and an MCP
server, not a redirect spelled with a variable, a glob, `>&`, `<>` or `$'…'`, nor a long command.

**Smallest fix** (shell.py / gate.py, ~15 lines, plus one doc line): add `>&` (when the next token is not
digits or `-`), `&>>` and `<>` to the write operators; expand a glob target with `glob.glob` against the
parser's cwd and take its matches; resolve `$PWD`, `${PWD}`, `$(pwd)` and a same-command `NAME=value` word
(the ones `_strip_wrappers` already pops) inside targets; strip `command`, `builtin`, `exec`, `nohup`, `nice`
like `env`; measure `PARSED` after `strip_heredocs`, since a heredoc body is what makes an honest command
long. Say in "Where each mechanism ends" that a target still holding `$` or a glob is not read before the
write.

## 5. `cd` is followed wrongly: flags, `cd -`, `$PWD`, and a subshell's cd that never ends (MEDIUM)

**Where.** `shell.py` `bash_written_paths` lines 105–113: `cd -P dir` and `cd -- dir` are read as `cd ~`
(`tokens[1].startswith("-")`); `cd -` too; `cd $PWD/…` sets cwd to None and drops every relative path
after it; `(` and `)` do not scope the cwd; and shlex glues `);` into one token, so `(cd src/api); echo x
> …` is one `cd` segment with nothing read after it.

**Fed and answered** (leaf held, scope `src/api/**`; each ALLOWED one wrote `src/db/schema.py` and was
REFUSED at done):

| event `command` | hook | what the parser thought |
|---|---|---|
| `cd -P src/db && echo x > schema.py` | ALLOWED | `~/schema.py`, outside the repo |
| `cd -- src/db && echo x > schema.py` | ALLOWED | `~/schema.py` |
| `cd src/api && cd - >/dev/null && echo x > src/db/schema.py` | ALLOWED | `~/src/db/schema.py` |
| `cd $PWD/src/db && echo x > schema.py` | ALLOWED | nowhere: dropped |
| `(cd src/api); echo x > src/db/schema.py` | ALLOWED | one `cd` segment |
| `(cd src/api && pwd >/dev/null) && echo x > src/db/schema.py` | ALLOWED | `src/api/src/db/schema.py`, inside the scope |
| mirror: `(cd src && ls >/dev/null) && echo x > src/api/users.py` | DENIED: src/src/api/users.py is outside the scope | a false refusal of a write inside the scope |
| mirror: `pushd src/api >/dev/null && echo x > users.py` | DENIED: users.py is outside the scope | the same |
| controls: `cd src/db && echo x > schema.py` DENIED; `cd src/api && echo x > users.py` ALLOWED | | |

**Smallest fix** (shell.py, ~15 lines, prototyped): keep a stack of cwds pushed at `(` and popped at `)`;
split a glued punctuation token into its operators (`);` → `)` `;`); take the first non-flag word after
`cd`/`pushd` (`-` itself is the previous directory, kept from the last cd); a target beginning `$PWD` or
`$(pwd)` resolves against the cwd. In the prototype all eight rows read right and the suite's 30 cases are
unchanged.

## 6. Reads and in-scope moves the hook refuses as writes (MEDIUM)

**Where.** `shell.py` `_segment_paths` line 132: a token equal to `>` or `>>` is a redirect even when it
was quoted or escaped, because shlex has dropped the quotes. `plan.in_scope` / `_pattern` (plan.py 178–215):
`src/api` does not match `src/api/**` (the glob needs the slash), and `shell._relative` normpaths away the
trailing slash `cp`, `mv` and `rm` were given, so a directory inside the scope is "outside".

**Fed and answered** (leaf held, scope `src/api/**`):

| event `command` | hook |
|---|---|
| `grep -n '>' src/db/schema.py` (a read) | DENIED: src/db/schema.py is outside the scope of the node you hold (n1: src/api/**)… |
| `rg -n '>>' src` (a read) | DENIED: src is outside the scope… |
| `grep -rn '>' .` (a read) | DENIED: . is outside the scope… |
| `git grep -n '>' src/db` (a read) | DENIED: src/db is outside the scope… |
| `cp README.md src/api/` | DENIED: src/api is outside the scope of the node you hold (n1: src/api/**) |
| `mv src/api/users.py src/api/` | DENIED: src/api is outside… |
| `rm -rf src/api/` | DENIED: src/api is outside… |
| the same `cp README.md src/api/` with the scope spelled `src/api` | ALLOWED |
| controls: `awk -F '>' '{print $1}' src/api/users.py` ALLOWED; `echo '>' > src/api/users.py` ALLOWED; `sed -i '' … src/api/users.py` ALLOWED | |

**Why it matters.** An agent searching for `>` or `>>` (shell redirects, HTML, prompts) is told a file is
outside its scope, and is taught the gate is wrong; copying a file into its own directory is the most
ordinary shell move there is, and the refusal names the scope's own directory as outside the scope.

**Git at done.** Not applicable: a read changes nothing; a copy inside the scope passes done.

**Smallest fix**: finding 1's mask kept through `_segment_paths`, so a quoted or escaped `>` is text (the
prototype reads the four searches as writing nothing and still sees `echo '>' > src/api/users.py` as a
write); in gate's Bash branch, judge an existing directory as `rel + "/"` (`in_scope("src/api/",
["src/api/**"])` is True; one line in `decide`).

---

## Also seen, lower

- **Case past a negated glob.** Scope `src/**, !src/db/**`: Write `<repo>/src/DB/schema.py` and `echo x >
  src/DB/schema.py` are ALLOWED and write `src/db/schema.py` on this Mac's case-ignoring disk; done refuses.
  Fix: match `!` globs casefolded, as `plan.covers` already does for standing paths. Clever only.
- **The other direction, by design.** Write `<repo>/SRC/api/users.py` while holding `src/api/**` is DENIED
  although it is the same file here; `_stray` at done says "git's spelling counts", so this is the rule, not a
  bug. The NFD spelling of an NFC scope directory (`docs/café/menu.md` under `docs/café/**`) is refused
  the same way; exotic.
- **`bash -c 'echo x > src/db/schema.py'`** passes the hook (the string is one token): a script, close to
  what HOW_IT_WORKS admits; worth one more word there ("or a shell started with -c").
- **`sed --in-place`** passes the hook; GNU sed only (BSD sed on this Mac errors).
- **Plan first** (`_first_write`) shares the parser, so findings 1, 4 and 5 hold there too (shown for 1).

## What held

Every spelling of a Write/Edit/MultiEdit/NotebookEdit path I tried against the plain scope was refused:
absolute, `./x`, `sub/../x`, a trailing slash, a trailing space, a case variant, a Cyrillic look-alike, a
path through a symlink to the repo root from outside, a link that leaves the repo; and the same through a
link into `.graphene/`. The 28 redirect, quoting, heredoc, subshell, pipeline and separator controls in
finding 4's last row were all refused with the right path. `done` refused every write that got past the
hook and named the file, including the `sandbox/` checkout itself.
