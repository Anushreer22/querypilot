"""Factory for selecting and instantiating LLM client providers."""

from app.core.config import settings
from app.services.llm.base import LLMClient
from app.services.llm.fake import FakeLLM
from app.services.llm.openai import OpenAILLMClient

_client_override: LLMClient | None = None


def set_llm_client(client: LLMClient | None) -> None:
    """Override the active LLM client (e.g. for unit test fixtures)."""
    global _client_override
    _client_override = client


def get_llm_client() -> LLMClient:
    """Obtain the configured LLM client instance based on settings."""
    if _client_override is not None:
        return _client_override

    provider = (settings.llm_provider or "openai").lower().strip()
    if provider == "fake":
        return FakeLLM()

    return OpenAILLMClient()
