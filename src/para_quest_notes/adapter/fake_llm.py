"""Test double for ``OllamaClient``.

Mirrors ``OllamaClient.generate`` so tests (and any future workflow that
wants a deterministic LLM in dev) can swap one for the other.

Two ways to use it:

* Queue canned responses with ``queue(text, ...)``.
* Provide a callable via ``responder=fn`` that takes the call kwargs and
  returns the response text (or a full ``LLMResponse``).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from para_quest_notes.adapter.errors import LLMError
from para_quest_notes.adapter.llm import LLMResponse


@dataclass
class RecordedCall:
    prompt: str
    model: str
    format: str | None
    temperature: float
    options: dict[str, Any]
    prompt_id: str | None


Responder = Callable[["RecordedCall"], "str | LLMResponse"]


@dataclass
class FakeLLM:
    default_model: str = "fake-model"
    _queue: deque[LLMResponse] = field(default_factory=deque)
    responder: Responder | None = None
    calls: list[RecordedCall] = field(default_factory=list)

    def queue(
        self,
        text: str,
        *,
        model: str | None = None,
        latency_ms: int = 0,
        raw: dict[str, Any] | None = None,
        prompt_id: str | None = None,
    ) -> None:
        self._queue.append(
            LLMResponse(
                text=text,
                model=model or self.default_model,
                latency_ms=latency_ms,
                raw=raw or {},
                prompt_id=prompt_id,
            )
        )

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        format: str | None = "json",
        temperature: float = 0.0,
        options: dict[str, Any] | None = None,
        prompt_id: str | None = None,
    ) -> LLMResponse:
        call = RecordedCall(
            prompt=prompt,
            model=model or self.default_model,
            format=format,
            temperature=temperature,
            options=dict(options or {}),
            prompt_id=prompt_id,
        )
        self.calls.append(call)

        if self.responder is not None:
            result = self.responder(call)
            if isinstance(result, LLMResponse):
                return result
            return LLMResponse(text=result, model=call.model, latency_ms=0, prompt_id=prompt_id)

        if not self._queue:
            raise LLMError("FakeLLM has no queued responses and no responder set")

        response = self._queue.popleft()
        if response.prompt_id is None and prompt_id is not None:
            response = LLMResponse(
                text=response.text,
                model=response.model,
                latency_ms=response.latency_ms,
                raw=response.raw,
                prompt_id=prompt_id,
            )
        return response
