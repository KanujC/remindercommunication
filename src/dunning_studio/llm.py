"""LLMClient protocol + Anthropic and mock implementations. Only module with side-effecting
network calls besides pipeline.py/run_eval.py callers."""

import os
from typing import Protocol

import httpx

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class LLMClient(Protocol):
    def complete(self, system: str, user: str, temperature: float) -> str: ...


class AnthropicLLMClient:
    """Default implementation, calling the Anthropic Messages API directly over httpx.
    Model via DUNNING_MODEL, key via ANTHROPIC_API_KEY. Never logs or persists the key."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("DUNNING_MODEL", "claude-sonnet-5")

    def complete(self, system: str, user: str, temperature: float) -> str:
        api_key = os.environ["ANTHROPIC_API_KEY"]
        response = httpx.post(
            _ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 1024,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        content = response.json()["content"]
        return "".join(block["text"] for block in content if block["type"] == "text")


class MockLLMClient:
    """Deterministic stub for tests and offline demos. Never hits the network.

    Accepts an optional list of canned responses (returned in order, then repeats the last),
    or a callable that inspects (system, user, temperature) and returns text.
    """

    def __init__(self, responses: list[str] | None = None, fn=None) -> None:
        self._responses = responses or []
        self._fn = fn
        self._call_count = 0

    def complete(self, system: str, user: str, temperature: float) -> str:
        self._call_count += 1
        if self._fn is not None:
            return self._fn(system, user, temperature)
        if not self._responses:
            raise RuntimeError("MockLLMClient has no responses or fn configured")
        idx = min(self._call_count - 1, len(self._responses) - 1)
        return self._responses[idx]

    @property
    def call_count(self) -> int:
        return self._call_count
