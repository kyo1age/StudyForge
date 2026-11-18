from functools import lru_cache
from ...config import settings
from .gemini_provider import GeminiProvider, configuration_error
from .mock import MockLlmProvider
from .openai_provider import OpenAiLlmProvider

@lru_cache(maxsize=1)
def get_llm():
    if settings.LLM_PROVIDER == "gemini" and configuration_error() is None:
        return GeminiProvider()
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return OpenAiLlmProvider()
    return MockLlmProvider()
