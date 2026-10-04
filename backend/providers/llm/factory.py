"""Build the model provider from settings. A new provider is one file and one branch here."""

from typing import Any

from core.ports import ModelProvider


def build(settings: Any) -> ModelProvider:
    provider = settings.JUTANT_LLM_PROVIDER
    if provider == "ollama":
        from providers.llm.ollama import OllamaProvider

        return OllamaProvider(
            base_url=settings.JUTANT_LLM_BASE_URL,
            model=settings.JUTANT_LLM_MODEL,
            embed_model=settings.JUTANT_EMBED_MODEL,
            num_ctx=settings.JUTANT_LLM_NUM_CTX,
            temperature=settings.JUTANT_LLM_TEMPERATURE,
            timeout_s=settings.JUTANT_LLM_TIMEOUT_S,
        )
    raise ValueError(f"Unknown JUTANT_LLM_PROVIDER: {provider}")
