"""Tests for adapter.fake_llm.

The real OllamaClient isn't tested here - it's network code, exercised
behind ``PQN_OLLAMA_INTEGRATION=1`` in a future opt-in suite. The adapter
contract is the FakeLLM/OllamaClient interface, and FakeLLM is what
workflows depend on in tests.
"""

from __future__ import annotations

import pytest

from para_quest_notes.adapter.errors import LLMError
from para_quest_notes.adapter.fake_llm import FakeLLM, RecordedCall
from para_quest_notes.adapter.llm import LLMResponse


def test_queue_returns_in_order() -> None:
    llm = FakeLLM()
    llm.queue('{"a": 1}')
    llm.queue('{"b": 2}')
    assert llm.generate("p1").text == '{"a": 1}'
    assert llm.generate("p2").text == '{"b": 2}'


def test_records_calls() -> None:
    llm = FakeLLM()
    llm.queue("x")
    llm.generate("hello", model="m1", temperature=0.7, options={"top_p": 0.9}, prompt_id="p@abc")
    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call.prompt == "hello"
    assert call.model == "m1"
    assert call.temperature == 0.7
    assert call.options == {"top_p": 0.9}
    assert call.prompt_id == "p@abc"


def test_no_responses_raises() -> None:
    llm = FakeLLM()
    with pytest.raises(LLMError):
        llm.generate("x")


def test_responder_callable_returning_str() -> None:
    def responder(call: RecordedCall) -> str:
        return f"echo:{call.prompt}"

    llm = FakeLLM(responder=responder)
    assert llm.generate("hi").text == "echo:hi"


def test_responder_callable_returning_response() -> None:
    def responder(call: RecordedCall) -> LLMResponse:
        return LLMResponse(text="full", model="custom", latency_ms=42)

    llm = FakeLLM(responder=responder)
    r = llm.generate("hi")
    assert r.model == "custom"
    assert r.latency_ms == 42


def test_prompt_id_propagates_when_queued_response_lacks_one() -> None:
    llm = FakeLLM()
    llm.queue("x")
    r = llm.generate("p", prompt_id="ingest@deadbeef")
    assert r.prompt_id == "ingest@deadbeef"
