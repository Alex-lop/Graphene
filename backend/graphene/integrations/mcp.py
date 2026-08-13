from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp_types import INVALID_PARAMS

from ..hashing import sha256_hex
from ..lineage.service import (
    RuntimeHandle,
    ScopedApplicationService,
    ToolCallIdentity,
)

_T = TypeVar("_T")
_ARGUMENTS = {
    "search_repo": frozenset({"query"}),
    "read_file": frozenset({"path"}),
    "open_evidence": frozenset({"evidence_id"}),
    "write_file": frozenset({"path", "content"}),
    "run_fixed_test": frozenset(),
    "request_completion": frozenset(),
}


def create_mcp_server(
    service: ScopedApplicationService,
    handle: RuntimeHandle,
    *,
    agent_name: str = "graphene_mcp",
) -> MCPServer:
    """Expose the common scoped runtime through exactly six MCP tools."""

    async def reject_forged_arguments(ctx: Any, call_next: Any) -> Any:
        if ctx.method == "tools/call":
            params = ctx.params
            name = params.get("name") if isinstance(params, Mapping) else None
            arguments = params.get("arguments") if isinstance(params, Mapping) else None
            arguments = {} if arguments is None else arguments
            expected = _ARGUMENTS.get(name)
            if (
                expected is None
                or not isinstance(arguments, Mapping)
                or set(arguments) != expected
                or any(not isinstance(arguments[key], str) for key in expected)
            ):
                raise MCPError(INVALID_PARAMS, "Invalid tool request")
        return await call_next(ctx)

    server = MCPServer(
        name="graphene",
        description="Wrapper-authoritative Graphene runtime",
        version="2",
        middleware=(reject_forged_arguments,),
    )

    def identity(ctx: Context) -> ToolCallIdentity:
        request_digest = sha256_hex(
            "\0".join(
                (handle.run_id, handle.invocation_id, ctx.request_id)
            ).encode()
        )
        return ToolCallIdentity(
            session_id=handle.session_id,
            invocation_id=handle.invocation_id,
            model_id=handle.model_id,
            tool_call_id=f"mcp_call_{request_digest[:32]}",
            agent_name=agent_name,
            adapter_kind="mcp",
        )

    def execute(operation: Callable[[], _T]) -> _T:
        try:
            return operation()
        except Exception:
            raise RuntimeError("Graphene tool request failed") from None

    @server.tool(structured_output=True)
    async def search_repo(query: str, ctx: Context) -> dict[str, Any]:
        """Search scoped repository files for an exact text query."""
        result = execute(lambda: service.search_repo(handle, identity(ctx), query=query))
        return {
            "paths": list(result.paths),
            "matches": [
                {
                    "path": item.path,
                    "line_number": item.line_number,
                    "line": item.line,
                }
                for item in result.matches
            ],
            "truncated": result.truncated,
            "evidence_id": result.evidence_ref.id,
        }

    @server.tool(structured_output=True)
    async def read_file(path: str, ctx: Context) -> dict[str, Any]:
        """Read one UTF-8 file from the immutable runtime read scope."""
        result = execute(lambda: service.read_file(handle, identity(ctx), path=path))
        return {
            "path": result.path,
            "content": result.content,
            "content_sha256": result.content_sha256,
            "file_version_id": result.file_version_id,
            "byte_count": result.byte_count,
            "line_count": result.line_count,
        }

    @server.tool(structured_output=True)
    async def open_evidence(evidence_id: str, ctx: Context) -> dict[str, Any]:
        """Open one item from the immutable runtime evidence allowlist."""
        result = execute(
            lambda: service.open_evidence(
                handle,
                identity(ctx),
                evidence_id=evidence_id,
            )
        )
        return {
            "evidence_id": result.evidence_id,
            "content": result.content,
            "content_sha256": result.content_sha256,
        }

    @server.tool(structured_output=True)
    async def write_file(path: str, content: str, ctx: Context) -> dict[str, Any]:
        """Write one UTF-8 file inside the immutable runtime write scope."""
        result = execute(
            lambda: service.write_file(
                handle,
                identity(ctx),
                path=path,
                content=content,
            )
        )
        return {
            "path": result.path,
            "before_file_version_id": result.before_file_version_id,
            "after_file_version_id": result.after_file_version_id,
            "after_sha256": result.after_sha256,
            "added_lines": result.added_lines,
            "deleted_lines": result.deleted_lines,
            "state": result.state,
        }

    @server.tool(structured_output=True)
    async def run_fixed_test(ctx: Context) -> dict[str, Any]:
        """Run the one server-frozen fixture test profile."""
        result = execute(lambda: service.run_fixed_test(handle, identity(ctx)))
        return {
            "passed": result.passed,
            "bound_paths": list(result.bound_paths),
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "output": result.output,
            "output_sha256": result.output_sha256,
            "output_truncated": result.output_truncated,
            "duration_bucket": result.duration_bucket,
        }

    @server.tool(structured_output=True)
    async def request_completion(ctx: Context) -> dict[str, Any]:
        """Request terminal completion for authoritative policy review."""
        result = execute(lambda: service.request_completion(handle, identity(ctx)))
        return {
            "status": "denied",
            "reason_code": result.reason_code,
            "state": result.state,
        }

    # MCP 2.0's generated argument models ignore extras. The public middleware
    # enforces exact keys; this mirrors that contract in the advertised schemas.
    for tool in server._tool_manager.list_tools():
        tool.parameters["additionalProperties"] = False
    return server


__all__ = ["create_mcp_server"]
