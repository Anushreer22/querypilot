"""Fake LLM client for deterministic testing and offline development."""

from typing import Any

from pydantic import BaseModel

from app.services.llm.base import LLMClient, LLMInvalidResponse


class FakeLLM(LLMClient):
    """Scriptable test double for LLM operations."""

    def __init__(
        self,
        responses: list[dict[str, Any] | Exception] | None = None,
        default_response: dict[str, Any] | None = None,
    ) -> None:
        self.responses: list[dict[str, Any] | Exception] = list(responses or [])
        self.default_response: dict[str, Any] = default_response or {
            "sql": "SELECT id, name FROM users LIMIT 10",
            "explanation": "Default fake response",
            "assumptions": [],
            "needs_clarification": False,
            "clarification_question": None,
        }
        self.calls: list[dict[str, Any]] = []

    def enqueue(self, item: dict[str, Any] | Exception) -> None:
        """Add a scripted response or exception to the front of the queue."""
        self.responses.append(item)

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Record the call and return the next scripted response or raise scripted error."""
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema": schema,
        })

        if self.responses:
            next_resp = self.responses.pop(0)
            if isinstance(next_resp, Exception):
                raise next_resp
            if not isinstance(next_resp, dict):
                raise LLMInvalidResponse(f"Fake response must be dict, got {type(next_resp).__name__}")
            return next_resp

        return dict(self.default_response)

