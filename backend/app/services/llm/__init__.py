"""LLM client abstraction package."""

from app.services.llm.base import (
    LLMClient,
    LLMError,
    LLMInvalidResponse,
    LLMRateLimit,
    LLMTimeout,
    LLMUnavailable,
)
from app.services.llm.factory import get_llm_client, set_llm_client
from app.services.llm.fake import FakeLLM
from app.services.llm.openai import OpenAILLMClient

__all__ = [
    "FakeLLM",
    "LLMClient",
    "LLMError",
    "LLMInvalidResponse",
    "LLMRateLimit",
    "LLMTimeout",
    "LLMUnavailable",
    "OpenAILLMClient",
    "get_llm_client",
    "set_llm_client",
]
