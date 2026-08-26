from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from ..adk_planner import describe_output_schema
from .gemini import FileMutation, WorkerIntent


class DeterministicWorkerModel(BaseLlm):
    """Injected ADK model for overlap, fencing, and replay proofs."""

    _mutations: tuple[FileMutation, ...] = PrivateAttr()
    _arrived: asyncio.Event | None = PrivateAttr(default=None)
    _release: asyncio.Event | None = PrivateAttr(default=None)
    _calls: int = PrivateAttr(default=0)
    _prompt: str = PrivateAttr(default="")
    _instruction: str = PrivateAttr(default="")

    def bind(
        self,
        mutations: tuple[FileMutation, ...],
        *,
        arrived: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self._mutations = mutations
        self._arrived = arrived
        self._release = release

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def mutations(self) -> tuple[FileMutation, ...]:
        return self._mutations

    @property
    def prompt(self) -> str:
        return self._prompt

    @property
    def instruction(self) -> str:
        """The system instruction as sent, so a test can pin what the worker is told."""

        return self._instruction

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        assert stream is False
        assert llm_request.config.response_schema is None
        assert llm_request.config.response_json_schema is None
        assert llm_request.config.response_mime_type == "application/json"
        assert describe_output_schema(WorkerIntent) in (
            llm_request.config.system_instruction or ""
        )
        self._calls += 1
        self._instruction = llm_request.config.system_instruction or ""
        self._prompt = "".join(
            part.text or ""
            for content in llm_request.contents
            for part in content.parts or ()
        )
        if self._arrived is not None:
            self._arrived.set()
        if self._release is not None:
            await self._release.wait()
        intent = WorkerIntent(mutations=self._mutations)
        yield LlmResponse(
            model_version=self.model,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=intent.model_dump_json())],
            ),
        )


__all__ = ["DeterministicWorkerModel"]
