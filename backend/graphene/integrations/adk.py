from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import google.adk
from google.adk.agents.callback_context import CallbackContext
from google.adk.events import Event as AdkEvent
from google.adk.models import LlmRequest, LlmResponse
from google.adk.runners import Runner
from google.adk.tools import ToolContext
from google.genai import types

from ..lineage.service import (
    RuntimeHandle,
    RuntimeIdentityError,
    ScopedApplicationService,
    ToolCallIdentity,
)

ADK_VERSION = "2.5.0"


@dataclass(frozen=True, slots=True)
class AdkRuntimeAdapter:
    """Bind real ADK callback identities to the common scoped service."""

    service: ScopedApplicationService
    handle: RuntimeHandle
    agent_name: str

    def __post_init__(self) -> None:
        if google.adk.__version__ != ADK_VERSION:
            raise RuntimeError(
                f"Google ADK {ADK_VERSION} is required; found {google.adk.__version__}"
            )

    async def before_model_callback(
        self,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        del llm_request
        self._validate_context(callback_context)
        self.service.ensure_invocation_started(
            self.handle,
            session_id=callback_context.session.id,
            invocation_id=callback_context.invocation_id,
            model_id=self.handle.model_id,
            adk_version=ADK_VERSION,
        )
        return None

    def tools(self) -> tuple[Any, ...]:
        service = self.service
        handle = self.handle
        identity = self._tool_identity

        async def search_repo(query: str, tool_context: ToolContext) -> dict[str, Any]:
            """Search scoped repository files for an exact text query."""
            result = service.search_repo(handle, identity(tool_context), query=query)
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

        async def read_file(path: str, tool_context: ToolContext) -> dict[str, Any]:
            """Read one UTF-8 file from the immutable runtime read scope."""
            result = service.read_file(handle, identity(tool_context), path=path)
            return {
                "path": result.path,
                "content": result.content,
                "content_sha256": result.content_sha256,
                "file_version_id": result.file_version_id,
                "byte_count": result.byte_count,
                "line_count": result.line_count,
            }

        async def open_evidence(
            evidence_id: str,
            tool_context: ToolContext,
        ) -> dict[str, Any]:
            """Open one item from the immutable runtime evidence allowlist."""
            result = service.open_evidence(
                handle,
                identity(tool_context),
                evidence_id=evidence_id,
            )
            return {
                "evidence_id": result.evidence_id,
                "content": result.content,
                "content_sha256": result.content_sha256,
            }

        async def write_file(
            path: str,
            content: str,
            tool_context: ToolContext,
        ) -> dict[str, Any]:
            """Write one UTF-8 file inside the immutable runtime write scope."""
            result = service.write_file(
                handle,
                identity(tool_context),
                path=path,
                content=content,
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

        async def run_fixed_test(tool_context: ToolContext) -> dict[str, Any]:
            """Run the one server-frozen fixture test profile."""
            result = service.run_fixed_test(handle, identity(tool_context))
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

        async def request_completion(tool_context: ToolContext) -> dict[str, Any]:
            """Request terminal completion for authoritative policy review."""
            result = service.request_completion(handle, identity(tool_context))
            tool_context.actions.skip_summarization = True
            return {
                "status": "denied",
                "reason_code": result.reason_code,
                "state": result.state,
            }

        return (
            search_repo,
            read_file,
            open_evidence,
            write_file,
            run_fixed_test,
            request_completion,
        )

    async def run_async(
        self,
        runner: Runner,
        *,
        user_id: str,
        new_message: types.Content,
    ) -> AsyncIterator[AdkEvent]:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=self.handle.session_id,
            invocation_id=self.handle.invocation_id,
            new_message=new_message,
        ):
            yield event

    def _validate_context(self, context: CallbackContext | ToolContext) -> None:
        if (
            context.session.id != self.handle.session_id
            or context.invocation_id != self.handle.invocation_id
            or context.agent_name != self.agent_name
        ):
            raise RuntimeIdentityError("ADK callback identity mismatch")

    def _tool_identity(self, tool_context: ToolContext) -> ToolCallIdentity:
        self._validate_context(tool_context)
        if not tool_context.function_call_id:
            raise RuntimeIdentityError("ADK function call identity is missing")
        return ToolCallIdentity(
            session_id=tool_context.session.id,
            invocation_id=tool_context.invocation_id,
            model_id=self.handle.model_id,
            tool_call_id=tool_context.function_call_id,
            agent_name=tool_context.agent_name,
            adapter_kind="adk",
        )


__all__ = ["ADK_VERSION", "AdkRuntimeAdapter"]
