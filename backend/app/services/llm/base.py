"""Base protocol and typed exceptions for LLM client abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class LLMError(Exception):
    """Base exception for all LLM errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class LLMTimeout(LLMError):
    """Raised when an LLM API request times out."""


class LLMRateLimit(LLMError):
    """Raised when an LLM API request is throttled or rate-limited."""


class LLMInvalidResponse(LLMError):
    """Raised when the LLM returns unparseable or schema-violating output."""


class LLMUnavailable(LLMError):
    """Raised when the LLM provider service is unreachable or returns 5xx."""


@dataclass(frozen=True)
class ToolCall:
    """Structure representing a single tool call proposed by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolCompletionResult:
    """Result of an LLM completion with tools: either tool calls or final text answer."""

    tool_calls: list[ToolCall] | None = None
    content: str | None = None


class LLMClient(ABC):
    """Abstract interface defining JSON and tool completion capabilities for LLM providers."""

    @abstractmethod
    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Send a prompt to the LLM and return a parsed JSON dictionary.

        Args:
            system_prompt: System context and behavioral guidelines.
            user_prompt: User request content.
            schema: Optional Pydantic model for schema guidance / validation.

        Returns:
            Parsed JSON dictionary.

        Raises:
            LLMTimeout: If the request exceeds the timeout threshold.
            LLMRateLimit: If rate limited by the provider.
            LLMInvalidResponse: If response is not valid JSON.
            LLMUnavailable: If provider service is down or returns 5xx.
        """

    @abstractmethod
    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ToolCompletionResult:
        """Send conversation message history and available tools to the LLM.

        Args:
            messages: List of conversation messages (role, content, tool_calls, tool_call_id, etc.).
            tools: Tool definitions conforming to OpenAI tool schemas.

        Returns:
            ToolCompletionResult with either tool_calls or final answer content.

        Raises:
            LLMTimeout: If the request exceeds the timeout threshold.
            LLMRateLimit: If rate limited by the provider.
            LLMInvalidResponse: If response is unparseable or violates schema.
            LLMUnavailable: If provider service is down or returns 5xx.
        """
