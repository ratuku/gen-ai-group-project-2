"""Adapters for local and cloud model providers."""

from .ollama import OllamaProvider, OllamaProviderError

__all__ = ["OllamaProvider", "OllamaProviderError"]
