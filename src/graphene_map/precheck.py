"""Red first: every check of the plan run before `R`, at the commit the work starts from.

A check tells a leaf is done only if it fails now and passes after the work. One that passes already,
or cannot run at all, says "done" of nothing. `graphene plan precheck [ids]` runs each check once (an
identical command once), says which it is from the exit code and the output, and asks Nano only about
a red whose reason those do not say.

A proposed leaf's check was written by a planner and not yet accepted by the person, so it runs only
in a fork of a sandbox checkpoint (ConTree, or Docker with GRAPHENE_SANDBOX=docker), never on this
machine; with no sandbox it is not run. An accepted leaf's check runs here, as `node done` runs it.

Each verdict is a `precheck` row on the leaf with the rev and commit it was run at: an edit or a new
commit makes it stale, and it is run again. Nano's reading is billed in a `usage` row on the plan,
saying who answered. `GRAPHENE_SHAPE=precheck` runs it as soon as a planner's proposal lands.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from . import plan as P
from . import tokenfactory as tf

FLAG = "precheck"
PROMPT_VERSION = "precheck-1"
SAID = {"passes": "passes already", "cannot-run": "cannot run", "not-run": "not run",
        "red-right-reason": "red, for the right reason", "red": "red", "environment": "red: the environment",
        "typo": "red: a typo", "other": "red: another reason"}  # fmt: skip
QUIET = ("red-right-reason", "red")  # the verdicts a check should have before the work: no mark
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdict", "why"], "properties": {
    "verdict": {"type": "string", "enum": ["red-right-reason", "environment", "typo", "other"]},
    "why": {"type": "string"}}}  # fmt: skip
_MISSING = re.compile(r"No module named '?([\w.]+)")


def verdict(code: int | None, out: str, command: str, scopes: list[str]) -> str | None:
    """What the exit code and the output say without a model, or None when only reading can say why it
    is red. A module no live scope may create is missing from the environment; one a scope creates is
    the work not done yet, which is the red a check should have."""
    if code is None:
        return "not-run"
    if code == 0:
        return "passes"
    if code in (126, 127) or "command not found" in out or code in (4, 5) and "pytest" in command:
        return "cannot-run"
    for name in _MISSING.findall(out):
        stem = name.replace(".", "/")
        if not any(P.in_scope(p, scopes) for p in (f"{stem}.py", f"{stem}/__init__.py")):
            return "cannot-run"
    return None


def current(store, node: P.Node, base: str | None) -> dict | None:
    """The leaf's last verdict, while it is about this rev, this check and this commit."""
    rows = [r["detail"] for r in store.node_log(node.id, ("precheck",))]
    last = rows[-1] if rows else None
    fresh = last and (last["rev"], last["check"], last["base"]) == (node.rev, node.check, base)
    return last if fresh and last["verdict"] != "not-run" else None


def _prepare(exe: str) -> str | None:
    """The executor setting's ``--prepare X`` or ``--prepare=X``, else None."""
    try:
        words = shlex.split(exe)
    except ValueError:  # unbalanced quotes: `init` refuses those, an older store may hold one
        return None
    for i, word in enumerate(words):
        if word.startswith("--prepare="):
            return word.split("=", 1)[1]
        if word == "--prepare" and i + 1 < len(words):
            return words[i + 1]
    return None


def _here(command: str, root: Path) -> tuple[int | None, str]:
    """An accepted check, run as `node done` runs it: in a clean worktree, without the key."""
    began = time.monotonic()
    env = {k: v for k, v in os.environ.items() if k != tf.KEY} | {"GRAPHENE_AS": "agent:check"}
    try:
        with P._clean_tree(root, (), began) as tree:
            code, out, err = P._ended(command, tree, env, began)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {P.CHECK_TIMEOUT:g} s"
    except (P.Refused, OSError) as no:
        return None, f"could not be run: {no}"
    return code, out + err


def _forks(root: Path, prepare: str | None):
    """(a runner that forks one checkpoint of the checkout per check, the box), or (None, why not)."""
    from . import sandbox as S

    name = os.environ.get("GRAPHENE_SANDBOX") or "contree"
    if name != "docker" and not S.configured():
        return None, "needs a sandbox (ConTree's credentials, or GRAPHENE_SANDBOX=docker)"
    tar = None
    try:
        tar = S.pack(root)
        box = S.Capped(S.choose(name))
        image, code, out = box.start(tar, S.base(prepare), 1800)
    except Exception as no:  # an SDK, a network, a docker that is not running
        return None, f"the sandbox could not be made: {no}"
    finally:
        if tar is not None:
            tar.unlink(missing_ok=True)
    if code:
        return None, f"the sandbox could not be made (exit {code}): {out.strip()[-200:]}"

    def fork(command: str) -> tuple[int | None, str]:
        try:
            code, out = S.check_in_fork(name, image, root, command, P.CHECK_TIMEOUT)
        except Exception as no:
            return None, f"could not be run in the sandbox: {no}"
        return (None, out) if code == 124 and "ran out of time" in out else (code, out)

    fork.where = f"a {'Docker' if name == 'docker' else 'ConTree'} fork"
    return fork, box


def _nano() -> str:
    """Nano's id, as the live list has it (the smallest Nemotron listed); asked twice at most."""
    listed = tf.resolve([], "executor", tf.models(tries=2))[0]
    if not listed:
        raise tf.Unreachable("Token Factory lists no Nemotron model")
    return listed[0]


def _read(store, node: P.Node, tail: str, model: str) -> tuple[str, str]:
    """Nano's reading of a red tail: (verdict, why). One call, billed on the plan's log."""
    prompt = (f"A coding agent will be given this work: {node.title}\n{node.goal}\n\nThe check that will say "
              f"it is done was run before any work, and failed:\n$ {node.check}\n{tail}\n\nIs it red because "
              "the work is not done yet (red-right-reason), because the environment cannot run it "
              "(environment), because the command or a path in it is misspelt (typo), or something else "
              "(other)? Answer with the verdict and why, in one sentence.")  # fmt: skip
    fmt = {"type": "json_schema", "json_schema": {"name": "precheck", "strict": True, "schema": SCHEMA}}
    said = tf.chat(model, [{"role": "user", "content": prompt}], tag=f"precheck:{node.id}",
                   response_format=fmt, reasoning_effort="low", temperature=0, max_tokens=2048)  # fmt: skip
    usage = said["usage"]
    store.log_node("*", P._now(), "usage", "precheck:nemotron", None, None, {
        "model": model, "calls": 1, "prompt_tokens": usage.get("prompt_tokens") or 0,
        "completion_tokens": usage.get("completion_tokens") or 0, "dollars": round(said["dollars"], 6),
        "prompt": PROMPT_VERSION, "endpoint": tf.endpoint()})  # fmt: skip
    try:
        answer = json.loads(said["message"].get("content") or "")
        if answer["verdict"] in SCHEMA["properties"]["verdict"]["enum"]:
            return answer["verdict"], " ".join(str(answer["why"]).split())[:300]
    except (ValueError, KeyError, TypeError):
        pass
    return "red", "not read: Nano's answer was not the verdict asked for"


def _runs(nodes: list[P.Node], root: Path, fork, prepare: str | None) -> dict:
    """Each distinct check run once: {(check, proposed): (exit or None, output, where)}. A proposed
    leaf's in a sandbox fork (the checkpoint is made for the first one), an accepted leaf's here."""
    ran, box = {}, None
    try:
        for node in nodes:
            key = (node.check, node.state == P.PROPOSED)
            if key in ran:
                continue
            if key[1] and fork is None:
                fork, box = _forks(root, prepare)
                if fork is None:  # every proposed check is then not run, and says why
                    fork, box = (lambda c, why=box: (None, why)), None
            runner = fork if key[1] else (lambda c: _here(c, root))
            try:
                code, text = runner(node.check)
            except Exception as no:  # one check that breaks its runner is its own line, not the command's
                code, text = None, f"could not be run: {' '.join(str(no).split())[:200]}"
            ran[key] = (code, text, getattr(runner, "where", "a sandbox fork") if key[1] else "here")
    finally:
        if box is not None and hasattr(box, "forget"):
            box.forget()
    return ran


def run(store, root: Path, ids=(), fork=None, prepare: str | None = None,
        again: bool = False) -> list[tuple[P.Node, dict]]:  # fmt: skip
    """Every check of the proposed and open leaves (or of ``ids``) at the checkout as git sees it now,
    each verdict a row. ``fork`` runs a proposed leaf's check in a sandbox; None makes one when needed."""
    everything = [n for n in P.nodes(store) if n.state not in P.GONE]
    todo = [P.get(store, i) for i in ids] or [n for n in everything if n.state in (P.PROPOSED, P.OPEN)]
    for n in todo:
        if n.state not in (P.PROPOSED, P.OPEN):
            raise P.Refused(f"{n.id} is {n.state}: a check is run first only before its work starts")
    base, read, out = P.head(root), {}, []
    if prepare is None:  # the sandbox the repo's executor would make
        prepare = _prepare(store.meta("executor") or "")
    todo = [n for n in todo if n.check]
    kept = {} if again else {n.id: current(store, n, base) for n in todo}
    ran = _runs([n for n in todo if not kept.get(n.id)], root, fork, prepare)
    scopes, model = [g for n in everything for g in n.scope if g != "**"], None
    for node in todo:
        if kept.get(node.id):
            out.append((node, {**kept[node.id], "kept": True}))  # shown as kept, never logged again
            continue
        key = (node.check, node.state == P.PROPOSED)
        code, text, where = ran[key]
        found, why, by = verdict(code, text, node.check, scopes), _gist(text), None
        if found == "passes":
            why = "it exits 0 before any work is done"
        elif found is None and key in read:
            found, why, by = read[key]
        elif found is None:
            try:
                if isinstance(model, tf.Unreachable):  # the list is asked once a run
                    raise model
                model = model or _nano()
                found, why = _read(store, node, text[-P.TAIL :], model)
                by = f"{model.rsplit('/', 1)[-1]}, {tf.endpoint()}"
            except Exception as no:  # an endpoint or a reply that breaks the reading: this red, unread
                model = model or no if isinstance(no, tf.Unreachable) else model
                found, why = "red", f"not read: {' '.join(str(no).split())}"
            read[key] = (found, why, by)
        detail = {"rev": node.rev, "check": node.check, "base": base, "verdict": found, "why": why,
                  "exit": code, "where": where, "by": by}  # fmt: skip
        store.log_node(node.id, P._now(), "precheck", "graphene:precheck", None, None, detail)
        out.append((node, detail))
    return out


def _gist(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:200] if lines else "no output"


def said(rows: list[tuple[P.Node, dict]]) -> list[str]:
    """One line a leaf, then what to do about the marked ones."""
    base = next((d["base"] for _, d in rows if d.get("base")), None)
    kept = sum(1 for _, d in rows if d.get("kept"))
    again = f" ({kept} kept from the last run at this commit; --again runs them again)" if kept else ""
    lines = [f"each check before any work, at {base[:7]}{again}:"] if base else []
    for node, d in rows:
        mark = " " if d["verdict"] in QUIET else "!"
        where = f" · {d['where']}" if d.get("where") not in (None, "here") else ""
        by = f" (read by {d['by']})" if d.get("by") else ""
        lines.append(f"{mark} {node.id:<16} {SAID[d['verdict']]:<26} {d['why']}{by}{where}")
    if any(d["verdict"] not in QUIET for _, d in rows):
        lines.append("! a check that passes now, or is red for another reason, cannot tell the work is done: "
                     "`graphene node set <id> --check '…'`")  # fmt: skip
    return lines


def shaped() -> bool:
    return FLAG in os.environ.get("GRAPHENE_SHAPE", "").replace(" ", "").split(",")


def after_proposal(store, root: Path, say=print) -> None:
    """`graphene ask` with GRAPHENE_SHAPE=precheck: the proposal's checks, run first as it lands."""
    if not shaped():
        return
    try:
        lines = said(run(store, root))
    except Exception as no:  # the proposal has landed: nothing here may turn that into a failed ask
        lines = [f"! the checks were not run first: {' '.join(str(no).split())[:200]}"]
    for line in lines:
        say(line)


def register(plan_cli, root, open_store, fail) -> None:
    import typer

    @plan_cli.command("precheck")
    def precheck_(
        ids: list[str] = typer.Argument(None, help="Leaves to check (default: every proposed and open one)."),
        prepare: str = typer.Option(
            None, "--prepare", help="Run once in the sandbox first (`pip install -e .`)."
        ),
        again: bool = typer.Option(False, "--again", help="Run a check again though its verdict is current."),
    ) -> None:
        """Red first: run each leaf's check before any work, and say which pass already or cannot run.
        A proposed leaf's check runs only in a sandbox fork, never here."""
        with open_store(root()) as store:
            try:
                P._person_only(P.caller(), "running the plan's checks first")
                rows = run(store, root(), ids or (), prepare=prepare, again=again)
            except P.Refused as no:
                fail(str(no), 1)
        for line in said(rows) or ["no leaf with a check is proposed or open"]:
            typer.echo(line)
