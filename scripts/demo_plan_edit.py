#!/usr/bin/env python3
"""Apply the rehearsal's plan edit to an exported plan, deterministically.

On film Alex edits the exported plan by hand — that is the point of the beat.
Rehearsals need the same beat to run the same way three times in a row, so
this makes the one edit the rehearsal script uses::

    uv run --frozen graphene plan export MISSION_ID --output plan.yaml
    uv run --frozen python scripts/demo_plan_edit.py plan.yaml
    uv run --frozen graphene plan revise plan.yaml

The edit: give one worker read access to the file another worker owns, so the
two renderers can agree on a shape. It is a scope expansion, which is exactly
what `plan diff` is supposed to make impossible to miss, and it stays inside
the project policy — `plan lint` is what proves that, not this script.

This is a rehearsal tool. It is not part of the `graphene` surface and nothing
in the product imports it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from graphene.orchestration.plan_yaml import (  # noqa: E402
    PlanDocumentError,
    plan_from_yaml,
    plan_to_yaml,
)


def widen_one_read_scope(document: str) -> tuple[str, str, tuple[str, ...]]:
    """Return the edited document, the node edited, and the paths it gained."""
    plan = plan_from_yaml(document)
    work = [task for task in plan.tasks if task.kind.value == "work"]
    if len(work) < 2:
        raise SystemExit("the plan has fewer than two work nodes to relate")
    # Deterministic but not brittle: take the first ordered pair, in plan
    # order, where the reader would actually gain something. A live planner
    # does not promise any particular pairing, and a rehearsal that dies
    # because the first pair happened to overlap is a rehearsal of nothing.
    pair = next(
        (
            (reader, writer, gained)
            for reader in work
            for writer in work
            if reader.task_id != writer.task_id
            for gained in (
                tuple(
                    path
                    for path in writer.write_paths
                    if path not in reader.read_paths
                ),
            )
            if gained
        ),
        None,
    )
    if pair is None:
        raise SystemExit("every work node already reads what the others write")
    reader, writer, gained = pair
    tasks = []
    for task in plan.tasks:
        value = task.model_dump(mode="json")
        if task.task_id == reader.task_id:
            value["read_paths"] = sorted({*task.read_paths, *gained})
            value["contract"] = (
                f"{task.contract} Match the shape of {writer.task_id}'s output."
            )[:1024]
        tasks.append(value)
    edited = plan.__class__.model_validate({**plan.model_dump(mode="json"), "tasks": tasks})
    return plan_to_yaml(edited), reader.task_id, gained


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="the exported plan YAML to edit in place")
    arguments = parser.parse_args()
    try:
        document, task_id, gained = widen_one_read_scope(arguments.plan.read_text())
    except PlanDocumentError as error:
        print(f"the exported plan could not be read: {error}", file=sys.stderr)
        return 1
    arguments.plan.write_text(document)
    print(f"edited {task_id}: read scope gained {', '.join(gained)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
