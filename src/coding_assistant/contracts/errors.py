"""Stable exception hierarchy for failures that cross component boundaries."""

from __future__ import annotations

from typing import Any


class CodingAssistantError(Exception):
    """Base class for application-level errors exposed by public contracts."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ConfigurationError(CodingAssistantError):
    """Configuration or caller-supplied input is invalid."""


class ProviderError(CodingAssistantError):
    """A model provider could not complete a request."""


class MCPError(CodingAssistantError):
    """Base class for MCP transport and protocol failures."""


class MCPConnectionError(MCPError):
    """An MCP server connection could not be established or was lost."""


class MCPDiscoveryError(MCPError):
    """Tools could not be discovered from a connected MCP server."""


class MCPProtocolError(MCPError):
    """An MCP request or response violated the protocol contract."""


class RetrievalError(CodingAssistantError):
    """Document ingestion, indexing, embedding, or retrieval failed."""
