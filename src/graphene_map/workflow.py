"""A workflow: a graph saved to `workflows/<name>.md`, run again on new input with no planner call.

    workflow: fix-issue
    input: issue
    input: suite = uv run pytest -q
    goal: fix issue {{issue}}

    - the fix for issue {{issue}}  [fix-{{issue}}]
        scope: src/**
        check: uv run pytest tests/test_{{issue}}.py -q
    - the whole suite  [suite-{{issue}}]
        run: {{suite}}
        needs: fix-{{issue}}

The file is the plan's text (plan_text.py) under a header: `workflow: NAME` is its first line that is not
blank or a `#` note, and NAME is the file's stem; `input: NAME` at the left edge declares a hole the person
fills, `input: NAME = DEFAULT` one with a default. `{{NAME}}` on any other line is replaced by the input's
value, exactly as given. The header's lines are left empty when the text is read, so a refusal names the
line the person sees in the file.

`graphene workflow NAME -i name=value` fills the holes and proposes the steps as `graphene ask` leaves a
planner's: suggested, until the person accepts them. Nothing is planned: the file is the plan, so the same
inputs give the same steps every time. `graphene workflow NAME --save` writes the plan as it stands to
such a file, each `-i name=literal` a hole wherever the literal was.

A step with `run:` is a command step: no agent takes it, and `graphene run` runs its command by itself
(run.py). One whose command leaves this machine (``leaves``: a push, a pull request) is never run by a
run: it waits for the person's `graphene node done`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import board as B
from . import plan as P
from . import plan_text as T

DIR = "workflows"  # at the repository's root
LAST = "workflow:last"  # plan_meta: the name and the inputs of the last workflow proposed, as JSON
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_WORKFLOW = re.compile(r"workflow\s*:(.*)")
_INPUT = re.compile(r"input\s*:(.*)")
_GOAL = re.compile(r"goal\s*:(.*)")
_HOLE = re.compile(r"\{\{(.*?)\}\}")
_STEP = re.compile(r"^(\s*)[-*+•?](?=\s)")  # a step's mark, as plan_text reads one
# ponytail: the line is what the command's own text says: `git push`, whatever options of git's own stand
# between the two words (`git -C dir push`), and `gh pr`. A script that pushes, an alias, `gh release`, `curl`
# or `npm publish` is not seen, and every screen that shows the line says so; name them here if a workflow
# ever needs them.
_LEAVES = re.compile(r"(?<![\w-])(?:git(?:\s+-\S+(?:\s+[^-\s]\S*)?)*\s+push|gh\s+pr)(?![\w-])")


def leaves(command: str | None) -> bool:
    """Whether a command leaves this machine: `git push` (git's own options may stand between the two
    words: `git -C dir push`) or `gh pr` anywhere in it, as words of their own. Nothing else is known to.
    The one place that knows where the line is: `graphene run` never runs such a step, the graph draws it
    past the line, and the person's `graphene node done` is what approves it."""
    return bool(_LEAVES.search(command or ""))


@dataclass
class Workflow:
    """One file of `workflows/`, read: its inputs in the order declared (None: no default), its goal as
    written, holes and all, and its lines, the header's left empty so every other line keeps its number."""

    name: str
    inputs: dict[str, str | None]
    goal: str | None
    lines: list[str]


def _one_line(what: str, value: str) -> str:
    """A value as it goes into the plan's text: one line. A line break would add lines to the plan (a
    second step, another key), so it is refused, by any character the text is split on."""
    value = value.strip()
    if value and value.splitlines() != [value]:
        raise P.Refused(
            f"{what} has a line break in it, and a value is one line of text (a second line would be read "
            "as another line of the plan). Write it on one line"
        )
    return value


def parse(text: str, stem: str) -> Workflow:
    """A workflow's text, read as the file `workflows/STEM.md`. Refused, by its line, when its first line
    is not `workflow: STEM`, when an `input:` line names no input or one named already, and when a hole
    names an input the file does not declare. The plan's text itself is read once its holes are filled."""
    lines = text.lstrip("﻿").splitlines()
    name, inputs, goal = None, {}, []
    for no, raw in enumerate(lines, 1):
        body = raw.strip()
        if not body or body.startswith("#"):
            continue
        if name is None:
            said = _WORKFLOW.fullmatch(body)
            if not said:
                raise P.Refused(
                    f"line {no}: this is not a workflow: its first line is `workflow: {stem}`, then an "
                    f"`input: NAME` line for each hole, then the plan's text ({body[:40]!r} is here)"
                )
            name = said[1].strip()
            if name != stem:
                raise P.Refused(
                    f"line {no}: workflow: {name}, and the file is {stem}.md. A workflow is named by its "
                    f"file: write `workflow: {stem}`, or rename the file"
                )
            lines[no - 1] = ""
        elif raw[:1] not in " \t" and (said := _INPUT.fullmatch(body)):
            key, _, default = said[1].partition("=")
            key = key.strip()
            if not NAME.fullmatch(key):
                raise P.Refused(
                    f"line {no}: input: {key!r} is not a name: a letter, then letters, digits, '-' and '_'. "
                    "Write `input: NAME`, or `input: NAME = DEFAULT`"
                )
            if key in inputs:
                raise P.Refused(f"line {no}: input: {key} is declared above already; delete one of the two")
            inputs[key] = default.strip() or None
            lines[no - 1] = ""
        elif raw[:1] not in " \t" and (said := _GOAL.fullmatch(body)):
            goal.append(said[1].strip())
    if name is None:
        raise P.Refused(f"line 1: this is not a workflow: its first line is `workflow: {stem}`")
    for no, raw in enumerate(lines, 1):
        for hole in () if raw.lstrip().startswith("#") else _HOLE.findall(raw):
            if hole.strip() not in inputs:
                raise P.Refused(
                    f"line {no}: {{{{{hole}}}}} is a hole no input declares. Add `input: {hole.strip()}` "
                    "under the workflow: line, or take the braces off"
                )
    return Workflow(name, inputs, " ".join(goal) or None, lines)


def read(root: Path, name: str) -> Workflow:
    """`workflows/NAME.md` of the repository at ``root``, read (``parse``); refused when there is none."""
    path = root / DIR / f"{name}.md"
    if not NAME.fullmatch(name) or not path.is_file():
        have = ", ".join(sorted(p.stem for p in (root / DIR).glob("*.md"))) or "none yet"
        raise P.Refused(
            f"no workflow named {name}: {DIR}/{name}.md is not there (here: {have}). `graphene workflow` "
            f"lists them; `graphene workflow {name} --save` writes one from the plan"
        )
    try:
        return parse(path.read_text(encoding="utf-8"), name)
    except (OSError, UnicodeError) as no:
        raise P.Refused(f"cannot read {DIR}/{name}.md: {getattr(no, 'strerror', None) or no}") from None
    except P.Refused as no:
        raise P.Refused(f"{DIR}/{name}.md, {no}") from None


def listed(root: Path) -> list[dict]:
    """Every file of `workflows/`, by name: its file, its goal as written, and its inputs with their
    defaults. One that cannot be read as a workflow is listed too, with why (``error``) and no inputs."""
    out = []
    for path in sorted((root / DIR).glob("*.md")):
        one = {"name": path.stem, "file": f"{DIR}/{path.name}", "goal": None, "inputs": [], "error": None}
        if not NAME.fullmatch(path.stem):  # no `graphene workflow NAME` could name it: say so, offer no run
            one["error"] = "a workflow's name is a letter, then letters, digits, - and _: rename the file"
            out.append(one)
            continue
        try:
            flow = parse(path.read_text(encoding="utf-8"), path.stem)
            one["goal"] = flow.goal
            one["inputs"] = [{"name": k, "default": v} for k, v in flow.inputs.items()]
        except (OSError, UnicodeError) as no:
            one["error"] = f"cannot be read: {getattr(no, 'strerror', None) or no}"
        except P.Refused as no:
            one["error"] = str(no)
        out.append(one)
    return out


def fill(flow: Workflow, given: dict[str, str]) -> tuple[str, dict[str, str]]:
    """The plan's text of a workflow with every hole filled, and the value each input got: the one
    ``given``, else its default. Refused when an input is given that the file does not declare, when one
    is left with no value, and when a value has a line break in it."""
    unknown = [k for k in given if k not in flow.inputs]
    if unknown:
        raise P.Refused(
            f"{flow.name} has no input named {', '.join(unknown)}: its inputs are "
            f"{', '.join(flow.inputs) or 'none'}. Give one of those, or declare it in {DIR}/{flow.name}.md "
            f"with `input: {unknown[0]}`"
        )
    values = {k: _one_line(f"-i {k}", given.get(k, default) or "") for k, default in flow.inputs.items()}
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise P.Refused(
            f"{flow.name} needs {' and '.join(missing)}: give {' '.join(f'-i {k}=VALUE' for k in missing)} "
            f"(or a default in {DIR}/{flow.name}.md, `input: {missing[0]} = DEFAULT`)"
        )
    filled = [
        raw if raw.lstrip().startswith("#") else _HOLE.sub(lambda hole: values[hole[1].strip()], raw)
        for raw in flow.lines
    ]
    return "\n".join(filled) + "\n", values


def propose(store, flow: Workflow, given: dict[str, str], who: P.Caller, files: list[str]) -> T.Said:
    """Fill the workflow's holes and propose its steps, with no planner: each is a proposal, as `graphene
    ask` leaves a planner's, whoever runs it, and the goal is the one the file names. Kept for `graphene
    plan undo`, as one act. Refused, with nothing proposed, when the filled text cannot be read, when the
    plan refuses a step, and when these inputs give an id the plan already has: such a line would add
    nothing (plan_text.py reads it as the place new lines hang from), and a run of a workflow must never
    add nothing without saying so. The inputs are remembered (``LAST``) for whoever saves it next."""
    text, values = fill(flow, given)
    text = "\n".join(_STEP.sub(r"\1?", line) for line in text.splitlines()) + "\n"
    where = f"{DIR}/{flow.name}.md"
    try:
        steps = T.parse(B.split(text)[0])[1]
    except P.Refused as no:
        raise P.Refused(f"{where}, {no}") from None
    if not steps:
        raise P.Refused(f"{where} has no step in it, so nothing was proposed: a step is a '- ' line")
    have = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    there = [ln.id for ln in steps if ln.id in have]
    if there:
        raise P.Refused(
            f"the plan already has {', '.join(there)}: these inputs give the ids of steps that are there, "
            "so nothing was proposed. Give an input another value (the ids are made from the holes), or "
            f"drop those steps first (`graphene node drop {there[0]}`)"
        )
    with P.undoable(store, who, f"workflow {flow.name}"):
        if wrong := T.faults(store, text, who, files):
            raise P.Refused("\n".join(f"{where}, {line}" for line in wrong))
        said = T.apply(store, text, who, None, files=files)
        store.set_meta(LAST, json.dumps({"name": flow.name, "inputs": values}))
    return said


def last(store) -> dict | None:
    """The name and the inputs of the last workflow proposed here, or None."""
    try:
        said = json.loads(store.meta(LAST) or "null")
    except ValueError:
        return None
    return said if isinstance(said, dict) else None
