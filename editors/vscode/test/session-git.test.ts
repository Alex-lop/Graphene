// What git knows that tool calls do not (src/sessions/git.ts), on a repository made for the test.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, unlinkSync, utimesSync, writeFileSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { note, porcelain, since, unexplained } from "../src/sessions/git.ts";

const has = (() => { try { execFileSync("git", ["--version"], { stdio: "pipe" }); return true; } catch { return false; } })();

test("git's short status is read as paths: a rename's new name, a deletion's own", () => {
  assert.deepEqual(porcelain(" M src/a.py\0?? new file.txt\0R  now.py\0was.py\0 D gone.py\0"), ["src/a.py", "new file.txt", "now.py", "gone.py"]);
  assert.deepEqual(porcelain(""), []);
});

test("of what git says changed, the files no write of the session's explains: from its folder, wherever that is in the repository", () => {
  assert.deepEqual(unexplained(["pkg/src/a.py", "pkg/gen/out.txt", "README.md"], ["src/a.py", "/repo/README.md"], "/repo", "/repo/pkg"), ["pkg/gen/out.txt"]);
  assert.deepEqual(unexplained(["a.py"], ["./a.py"], "/repo", "/repo"), []);
  assert.deepEqual(unexplained(["a.py"], ["/elsewhere/a.py"], "/repo", "/repo"), ["a.py"]); // a file of the same name outside it explains nothing
});

test("a folder is noted when a session is first seen and compared later: what changed since, and never what was already dirty and left alone", { skip: !has && "no git here" }, async () => {
  const repo = realpathSync(mkdtempSync(path.join(os.tmpdir(), "graphene-git-")));
  const git = (...a: string[]) => execFileSync("git", ["-c", "user.name=Scratch", "-c", "user.email=scratch@example.com", ...a], { cwd: repo, stdio: "pipe" });
  try {
    assert.equal(await note(repo), null); // no repository: nothing is noted, and nothing is said
    git("init", "-q");
    mkdirSync(path.join(repo, "pkg"));
    for (const f of ["a.py", "b.py", "c.py", "pkg/d.py"]) writeFileSync(path.join(repo, f), `${f}\n`);
    git("add", "-A");
    git("commit", "-qm", "first");
    writeFileSync(path.join(repo, "b.py"), "the person's own edit, before the session\n");
    writeFileSync(path.join(repo, "c.py"), "dirty before, and edited again during it\n");
    const was = (await note(repo))!;
    // a session in a folder inside the repository: the same top, and only what is under its folder (the two dirty
    // files beside it are not its folder's, and a repository that merely encloses a folder is never read whole)
    const inside = (await note(path.join(repo, "pkg")))!;
    assert.deepEqual([inside.top, inside.dir, [...inside.dirty.keys()]], [repo, "pkg", []]);
    assert.equal(was.top, repo);
    assert.equal(was.head.length, 40);
    assert.deepEqual([...was.dirty.keys()].sort(), ["b.py", "c.py"]);
    assert.deepEqual((await since(was))!.changed, []); // nothing happened yet
    // the session: one file by a tool call, one by a command, one committed, one new, one deleted, one dirty file touched again
    writeFileSync(path.join(repo, "a.py"), "edited by a tool call\n");
    writeFileSync(path.join(repo, "pkg", "d.py"), "rewritten by a formatter the agent ran\n");
    writeFileSync(path.join(repo, "c.py"), "something else now\n");
    writeFileSync(path.join(repo, "new.txt"), "made by a command\n");
    git("add", "pkg/d.py");
    git("commit", "-qm", "second");
    const now = (await since(was))!;
    assert.equal(now.commits, 1);
    assert.deepEqual(now.changed, ["a.py", "c.py", "new.txt", "pkg/d.py"]); // b.py was dirty before and was left alone: not the session's
    assert.deepEqual(unexplained(now.changed, ["a.py"], was.top, repo), ["c.py", "new.txt", "pkg/d.py"]);
    assert.deepEqual((await since(inside))!.changed, ["pkg/d.py"]); // from the folder inside: what changed under it, committed or not
    assert.equal((await since(inside))!.commits, 1); // the commit touched pkg/d.py
    // a commit elsewhere in the repository is not the folder's: nothing moved for it
    const here = (await note(path.join(repo, "pkg")))!;
    writeFileSync(path.join(repo, "elsewhere.txt"), "not under pkg\n");
    git("add", "elsewhere.txt");
    git("commit", "-qm", "elsewhere");
    assert.deepEqual([(await since(here))!.commits, (await since(here))!.changed], [0, []]);
    // and reading it took no lock and wrote nothing: the index is byte for byte what it was
    // (a clean file whose time changed is what makes git refresh its index: a plain `git status` does rewrite it)
    const index = () => readFileSync(path.join(repo, ".git", "index")).toString("base64");
    const touch = (ahead: number) => utimesSync(path.join(repo, "elsewhere.txt"), new Date(), new Date(Date.now() + ahead));
    touch(60_000);
    const before = index();
    await note(repo);
    assert.equal(index(), before);
    git("status");
    assert.notEqual(index(), before, "the plain status this test compares with did refresh the index");
    assert.equal(now.dropped, 0);
    unlinkSync(path.join(repo, "b.py")); // a deleted file cannot be hashed: its name is still noted
    const gone = (await note(repo))!;
    assert.ok(gone.dirty.has("b.py"));
    // and it does not keep the files beside it from being hashed: a dirty file a command rewrites is still seen to change
    assert.ok(gone.dirty.get("c.py"));
    writeFileSync(path.join(repo, "c.py"), "rewritten once more, by a command\n");
    assert.deepEqual((await since(gone))!.changed, ["c.py"]);
    // HEAD moved back: no commit on top of the noted one, and one it was on that it is not on now
    git("stash", "-u", "-q");
    const top = (await note(repo))!;
    git("reset", "-q", "--hard", "HEAD~1");
    assert.deepEqual([(await since(top))!.commits, (await since(top))!.dropped], [0, 1]);
    // a folder named by a link to it (/tmp for /private/tmp): a file its session wrote is still its own
    const link = `${repo}-link`;
    symlinkSync(repo, link);
    try { assert.deepEqual(unexplained(["a.py", "new.txt"], ["a.py", `${link}/new.txt`], top.top, link), []); } finally { unlinkSync(link); }
  } finally { rmSync(repo, { recursive: true, force: true }); }
});
