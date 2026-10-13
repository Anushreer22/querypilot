"""Base protocol and typed exceptions for LLM client abstractions."""

from abc import ABC, abstractmethod
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


class LLMClient(ABC):
    """Abstract interface defining JSON completion capabilities for LLM providers."""

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

