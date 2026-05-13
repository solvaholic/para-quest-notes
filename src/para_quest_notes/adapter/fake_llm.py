"""Test double for ``OllamaClient``.

Mirrors the ``OllamaClient`` text and JSON call shapes so workflows (and
any future dev-only tooling) can swap one for the other.

Two ways to use it:

* Queue canned responses with ``queue(text, ...)``.
* Provide a callable via ``responder=fn`` that takes the call kwargs and
  returns the response text (or a full ``LLMResponse``).
"""

from __future__ import annotations

from collections import defaultdict, deque
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
    _text_by_prompt_id: dict[str, deque[LLMResponse]] = field(
        default_factory=lambda: defaultdict(deque)
    )
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

    def add_text_response(
        self,
        prompt_id: str,
        response: str,
        *,
        model: str | None = None,
        latency_ms: int = 0,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self._text_by_prompt_id[prompt_id].append(
            LLMResponse(
                text=response,
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
        call = self._record_call(
            prompt,
            model=model,
            format=format,
            temperature=temperature,
            options=options,
            prompt_id=prompt_id,
        )
        return self._respond(call, prompt_id=prompt_id)

    def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        options: dict[str, Any] | None = None,
        prompt_id: str | None = None,
    ) -> LLMResponse:
        call = self._record_call(
            prompt,
            model=model,
            format=None,
            temperature=temperature,
            options=options,
            prompt_id=prompt_id,
        )
        return self._respond(call, prompt_id=prompt_id, prefer_prompt_id=True)

    def _record_call(
        self,
        prompt: str,
        *,
        model: str | None,
        format: str | None,
        temperature: float,
        options: dict[str, Any] | None,
        prompt_id: str | None,
    ) -> RecordedCall:
        call = RecordedCall(
            prompt=prompt,
            model=model or self.default_model,
            format=format,
            temperature=temperature,
            options=dict(options or {}),
            prompt_id=prompt_id,
        )
        self.calls.append(call)
        return call

    def _respond(
        self,
        call: RecordedCall,
        *,
        prompt_id: str | None,
        prefer_prompt_id: bool = False,
    ) -> LLMResponse:
        if self.responder is not None:
            result = self.responder(call)
            if isinstance(result, LLMResponse):
                return result
            return LLMResponse(text=result, model=call.model, latency_ms=0, prompt_id=prompt_id)

        if prefer_prompt_id and prompt_id is not None:
            queued = self._text_by_prompt_id.get(prompt_id)
            if queued:
                response = queued.popleft()
                if not queued:
                    self._text_by_prompt_id.pop(prompt_id, None)
                return self._with_prompt_id(response, prompt_id)

        if not self._queue:
            raise LLMError("FakeLLM has no queued responses and no responder set")

        response = self._queue.popleft()
        return self._with_prompt_id(response, prompt_id)

    def _with_prompt_id(self, response: LLMResponse, prompt_id: str | None) -> LLMResponse:
        if response.prompt_id is None and prompt_id is not None:
            return LLMResponse(
                text=response.text,
                model=response.model,
                latency_ms=response.latency_ms,
                raw=response.raw,
                prompt_id=prompt_id,
            )
        return response
