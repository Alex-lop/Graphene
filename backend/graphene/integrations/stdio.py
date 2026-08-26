from __future__ import annotations

import argparse
import os
import signal
import sys
from collections.abc import Sequence

from ..bootstrap import bootstrap_local_run
from ..context.consumer import resume_fresh_consumer
from ..lineage.observation import wait_until_observed
from ..lineage.recovery import recover_interrupted_run
from ..core_models import EvidenceKind, SourceKind, SourceReference, TaskId
from .mcp import create_mcp_server
from .mission_mcp import create_mission_mcp_server

_PROFILES = (
    "platform-maintainer@1",
    "auth-maintainer@1",
    "billing-observer@1",
)
_ARGUMENT_ERROR = "GRAPHENE_MCP_ARGUMENT_ERROR\n"
_CONFIG_ERROR = "GRAPHENE_MCP_CONFIG_ERROR\n"
_STARTUP_ERROR = "GRAPHENE_MCP_STARTUP_ERROR\n"
_READY = "GRAPHENE_MCP_STDIO_READY\n"
_RUNTIME_ERROR = "GRAPHENE_MCP_RUNTIME_ERROR\n"
_INTERRUPTED = "GRAPHENE_MCP_INTERRUPTED\n"


class _InvalidArguments(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _InvalidArguments from None


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="graphene-mcp", allow_abbrev=False)
    # No mode flag at all serves the mission control plane (plan_goal,
    # get_digest, approve_plan, mission_status, why, mission_summary and the
    # `goal` prompt) over the CLI's own state root. --task/--run keep the
    # legacy protocol tour exactly as before.
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--task",
        choices=tuple(item.value for item in TaskId),
    )
    mode.add_argument("--run")
    parser.add_argument("--profile", choices=_PROFILES)
    return parser


def _diagnostic(message: str) -> None:
    sys.stderr.write(message)
    sys.stderr.flush()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        if (arguments.task is None) != (arguments.profile is None):
            raise _InvalidArguments
    except _InvalidArguments:
        _diagnostic(_ARGUMENT_ERROR)
        return 2
    if arguments.task is None and arguments.run is None:
        return _serve_missions()

    database = os.environ.get("GRAPHENE_LINEAGE_DB")
    if not database:
        _diagnostic(_CONFIG_ERROR)
        return 2
    try:
        runtime = (
            resume_fresh_consumer(database, arguments.run)
            if arguments.run is not None
            else bootstrap_local_run(
                database,
                task_id=arguments.task,
                profile_id=arguments.profile,
            )
        )
        server = create_mcp_server(
            runtime.service,
            runtime.handle,
            after_commit=lambda seq: wait_until_observed(
                runtime.database_path,
                runtime.run_id,
                seq,
            ),
        )
    except Exception:  # noqa: BLE001 - never leak startup lineage/config details
        _diagnostic(_STARTUP_ERROR)
        return 1

    # A shell that starts a job in the background sets SIGINT to SIG_IGN for the
    # child, and SIG_IGN survives exec — so relying on Python's default handler
    # means this server silently ignores Ctrl-C whenever it was launched from a
    # background job, a service manager, or a CI step that backgrounds its work.
    # Claim the signal explicitly, whatever we inherited.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    _diagnostic(_READY)
    exit_code = 0
    exit_diagnostic: str | None = None
    try:
        server.run("stdio")
    except KeyboardInterrupt:
        exit_code = 130
        exit_diagnostic = _INTERRUPTED
    except Exception:  # noqa: BLE001 - never leak protocol/runtime failures
        exit_code = 1
        exit_diagnostic = _RUNTIME_ERROR
    try:
        recover_interrupted_run(
            runtime.store,
            run_id=runtime.run_id,
            checkout_path=runtime.checkout_root,
            record_source=lambda record: _recovery_source(runtime, record),
        )
    except Exception:  # noqa: BLE001 - never leak recovery/store failures
        _diagnostic(_RUNTIME_ERROR)
        return 1
    if exit_diagnostic is not None:
        _diagnostic(exit_diagnostic)
    return exit_code


def _serve_missions() -> int:
    """`graphene-mcp` with no mode flag: the /graphene loop over stdio."""

    try:
        server = create_mission_mcp_server()
    except Exception:  # noqa: BLE001 - never leak startup details
        _diagnostic(_STARTUP_ERROR)
        return 1
    signal.signal(signal.SIGINT, signal.default_int_handler)
    _diagnostic(_READY)
    try:
        server.run("stdio")
    except KeyboardInterrupt:
        _diagnostic(_INTERRUPTED)
        return 130
    except Exception:  # noqa: BLE001 - never leak protocol/runtime failures
        _diagnostic(_RUNTIME_ERROR)
        return 1
    return 0


def _recovery_source(runtime, record) -> SourceReference:
    reference = runtime.artifacts(EvidenceKind.OPERATOR_REQUEST, record)
    return SourceReference(
        kind=SourceKind.LIFECYCLE_REQUEST,
        id=reference.id,
        sha256=reference.sha256,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
