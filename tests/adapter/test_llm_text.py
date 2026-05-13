from __future__ import annotations

import json
import urllib.error
from typing import Any

from para_quest_notes.adapter.fake_llm import FakeLLM
from para_quest_notes.adapter.llm import OllamaClient


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


def test_fake_llm_generate_text_returns_prompt_specific_response() -> None:
    llm = FakeLLM()
    llm.add_text_response("generate_outcome@abc123", "plain text")

    response = llm.generate_text("prompt", prompt_id="generate_outcome@abc123")

    assert response.text == "plain text"
    assert llm.calls[0].format is None


def test_generate_text_omits_json_format(monkeypatch) -> None:
    payloads: list[dict[str, Any]] = []

    def fake_urlopen(req, timeout: int):
        payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeHTTPResponse({"response": "draft text"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OllamaClient(retries=1)

    response = client.generate_text("hello", prompt_id="generate_outcome@abc123")

    assert response.text == "draft text"
    assert response.prompt_id == "generate_outcome@abc123"
    assert "format" not in payloads[0]


def test_generate_text_retries_then_succeeds(monkeypatch) -> None:
    attempts = {"count": 0}

    def fake_urlopen(req, timeout: int):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.URLError("boom")
        return _FakeHTTPResponse({"response": "eventual text"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OllamaClient(retries=2, backoff_seconds=0)

    response = client.generate_text("hello")

    assert attempts["count"] == 2
    assert response.text == "eventual text"
