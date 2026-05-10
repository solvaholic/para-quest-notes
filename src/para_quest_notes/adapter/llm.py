"""Minimal Ollama client.

stdlib ``urllib`` over the Ollama HTTP API
(https://github.com/ollama/ollama/blob/main/docs/api.md).

We use the non-streaming ``/api/generate`` endpoint and pass
``format="json"`` so the model is instructed to emit JSON. The caller is
responsible for ``json.loads`` and schema validation - this layer just
returns the raw and parsed strings plus metadata for the trace logger.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from para_quest_notes.adapter.errors import LLMError

DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_S = 0.5


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: int
    raw: dict[str, Any] = field(default_factory=dict)
    prompt_id: str | None = None


class OllamaClient:
    """Thin synchronous Ollama wrapper.

    Interface mirrored by ``FakeLLM`` for tests - keep them in sync.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "granite4.1:30b",
        timeout_seconds: int = 120,
        retries: int = DEFAULT_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_S,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds

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
        chosen_model = model or self.default_model
        opts: dict[str, Any] = {"temperature": temperature}
        if options:
            opts.update(options)

        body: dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt,
            "stream": False,
            "options": opts,
        }
        if format:
            body["format"] = format

        url = f"{self.base_url}/api/generate"
        data = json.dumps(body).encode("utf-8")
        last_exc: Exception | None = None

        for attempt in range(1, self.retries + 1):
            start = time.perf_counter()
            try:
                req = urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                latency_ms = int((time.perf_counter() - start) * 1000)
                text = payload.get("response", "")
                return LLMResponse(
                    text=text,
                    model=chosen_model,
                    latency_ms=latency_ms,
                    raw=payload,
                    prompt_id=prompt_id,
                )
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff_seconds * attempt)

        raise LLMError(
            f"ollama generate failed after {self.retries} attempts: {last_exc!r}"
        ) from last_exc
