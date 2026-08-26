"""Canonical YAML for the mission plan — the one editable projection.

`plan export` writes it, the user edits it, `plan revise` reads it back. A
later browser editor is meant to be a projection of this same codec and of
`validate_plan`, not a second dialect with its own rules.

Nothing here grants authority. This module turns an immutable `Plan` into text
a person can read and change, and turns edited text back into a `Plan` — or
refuses it. Whether the resulting plan is legal is `validate_plan`'s job, and
whether it may run is the approval's.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import ValidationError

from .mission_models import Plan

# A plan is bounded by its own model (256 tasks, bounded text); this is the
# outer guard so a hostile document cannot be expanded before Pydantic ever
# sees it.
MAX_DOCUMENT_BYTES = 1_048_576

HEADER = """\
# Graphene mission plan — canonical export.
#
# Edit the work itself: add or remove a task, change `dependencies`, widen or
# narrow `read_paths` / `write_paths`, change `acceptance_checks`, retitle a
# `contract`, move `priority` or `attempt_limit`.
#
# Then: graphene plan revise THIS_FILE
#
# The revision becomes an immutable revision N+1 with a new digest, and it
# needs its own approval before anything runs. Unknown fields are refused, and
# so is anything the project policy does not allow. `revision` and
# `previous_revision` are set by `revise`; leave them alone.
"""


class PlanDocumentError(ValueError):
    """The document is not a plan this store would accept."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys and YAML aliases.

    PyYAML's default is last-key-wins, which would silently drop half of an
    edit; and an alias in a contract document is a way to make the text and
    the meaning disagree.
    """


def _no_duplicate_keys(loader: _StrictLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise PlanDocumentError(f"duplicate key {key!r} in the plan document")
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


def _no_alias(_loader: _StrictLoader, node: yaml.Node) -> None:
    raise PlanDocumentError("the plan document may not use YAML anchors or aliases")


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)
for _alias_tag in ("tag:yaml.org,2002:value", "tag:yaml.org,2002:merge"):
    _StrictLoader.add_constructor(_alias_tag, _no_alias)


def plan_to_yaml(plan: Plan, *, header: bool = True) -> str:
    """Render a plan as canonical YAML.

    Keys are sorted and flow style is off, so the same plan always produces
    the same bytes and two revisions diff line by line.
    """
    body = yaml.safe_dump(
        plan.model_dump(mode="json"),
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return (HEADER + body) if header else body


def plan_from_yaml(text: str) -> Plan:
    """Compile edited YAML back into a plan, or refuse it with one reason."""
    if len(text.encode()) > MAX_DOCUMENT_BYTES:
        raise PlanDocumentError("the plan document is too large")
    try:
        document = yaml.load(text, Loader=_StrictLoader)
    except PlanDocumentError:
        raise
    except yaml.YAMLError as error:
        raise PlanDocumentError(f"the plan document is not valid YAML: {error}") from (
            error
        )
    if not isinstance(document, dict):
        raise PlanDocumentError("the plan document must be a mapping")
    try:
        return Plan.model_validate(document)
    except ValidationError as error:
        raise PlanDocumentError(_first_reason(error)) from error


def _first_reason(error: ValidationError) -> str:
    """One readable line, not a Pydantic dump."""
    first = error.errors()[0]
    location = ".".join(str(item) for item in first["loc"]) or "plan"
    if first["type"] == "extra_forbidden":
        return f"unknown field {location}"
    return f"{location}: {first['msg']}"


__all__ = [
    "HEADER",
    "MAX_DOCUMENT_BYTES",
    "PlanDocumentError",
    "plan_from_yaml",
    "plan_to_yaml",
]
