# The copied index: a check's clean tree can miss a same-second, same-size edit

Found by the harness's dry run of X5 on 907a7d0 (the broken leaf landed under `uv run pytest`, where the worktree's
own package was imported), and reproduced outside Graphene on 10 October 2026 with Apple Git-146 (2.39.3), macOS.

`plan._clean_tree` copies the worktree's index file and runs `git add -A` on the copy. Git decides whether a tracked
file changed by its stat data (seconds-resolution mtime and ctime, size, inode) unless the entry is "racily clean":
its mtime at or after the index file's own timestamp, in which case the content is read. The copy's timestamp is
the time of the copy, so no entry is racy, and an edit made in the second the file was written out, keeping its
size and inode, reads as the committed file. Dating the copy at epoch+1 makes every entry racy and the content is
read; a zero date disables git's racy check (`istate->timestamp.sec &&` in `is_racy_timestamp`); `git update-index
--really-refresh` on the copy did not help here.

```python
import os, shutil, subprocess, time, pathlib
repo = pathlib.Path(".").resolve()
def git(*a, index=None):
    env = {**os.environ, **({"GIT_INDEX_FILE": str(index)} if index else {})}
    return subprocess.run(["git", *a], cwd=repo, env=env, capture_output=True, text=True).stdout.strip()
git("init", "-q"); git("config", "user.email", "x@x"); git("config", "user.name", "x")
f = repo / "f.py"
for trial in range(4):
    f.write_text(f"x = a * b  # {trial}\n"); git("add", "f.py"); git("commit", "-q", "-m", "c"); t_commit = time.time()
    f.write_text(f"x = a / b  # {trial}\n"); t_edit = time.time()          # same size, same inode, same second
    same = int(t_commit) == int(t_edit)
    copy = repo / ".git" / "index.copy"
    def tree_with(prep):
        shutil.copyfile(repo / ".git" / "index", copy); os.utime(copy, (t_edit + 10, t_edit + 10))
        prep()
        git("add", "-A", index=copy); return git("cat-file", "-p", git("write-tree", index=copy) + ":f.py", index=copy)
    stale = tree_with(lambda: None)
    one = tree_with(lambda: os.utime(copy, (1, 1)))
    refreshed = tree_with(lambda: git("update-index", "-q", "--really-refresh", index=copy))
    print(f"trial {trial}: same second={same} | copy: {stale!r} | utime(1): {one!r} | really-refresh: {refreshed!r}")
    time.sleep(1.1)
```

```
trial 0: same second=True | copy: 'x = a * b  # 0' | utime(1): 'x = a / b  # 0' | really-refresh: 'x = a * b  # 0'
trial 1: same second=True | copy: 'x = a * b  # 1' | utime(1): 'x = a / b  # 1' | really-refresh: 'x = a * b  # 1'
trial 2: same second=True | copy: 'x = a * b  # 2' | utime(1): 'x = a / b  # 2' | really-refresh: 'x = a * b  # 2'
trial 3: same second=True | copy: 'x = a * b  # 3' | utime(1): 'x = a / b  # 3' | really-refresh: 'x = a * b  # 3'
```

In Graphene's flow the worktree is checked out at T0 and its index written then; an executor's first edit often lands
in the same second (a fake executor does; a model's first edit arrives later, so the model runs seen so far were not
hit). A `done` in that second reads the content (racy against a copy made in the same second) and fails the check;
one a second or more later trusts the stat data and passes, as the executor's own `done` did in X5's run on 907a7d0.
