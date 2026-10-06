"""Load and validate MCP server configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """The MCP configuration file is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """The settings needed to open one MCP transport."""

    name: str
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    timeout_seconds: float = 60.0

    @property
    def transport(self) -> Literal["stdio", "http"]:
        return "stdio" if self.command is not None else "http"


@dataclass(frozen=True, slots=True)
class MCPConfig:
    """Validated configuration for every MCP server used by the application."""

    servers: tuple[ServerConfig, ...]
    workspace_root: Path


def load_mcp_config(
    path: str | Path, *, workspace_root: str | Path | None = None
) -> MCPConfig:
    """Load a conventional ``mcpServers`` JSON object.

    The ``${workspaceRoot}`` placeholder is expanded in stdio arguments,
    environment values, and working directories. An empty server object is valid
    while integrations are added by later issues.
    """

    config_path = Path(path).resolve()
    root = (
        Path(workspace_root).resolve()
        if workspace_root is not None
        else config_path.parent.parent
    )

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Invalid JSON in {config_path} at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except OSError as exc:
        raise ConfigurationError(
            f"Could not read configuration file {config_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigurationError("The configuration root must be a JSON object")
    raw_servers = raw.get("mcpServers")
    if not isinstance(raw_servers, dict):
        raise ConfigurationError("'mcpServers' must be a JSON object")

    servers = tuple(
        _parse_server(name, value, workspace_root=root)
        for name, value in raw_servers.items()
    )
    return MCPConfig(servers=servers, workspace_root=root)


def _parse_server(name: object, raw: object, *, workspace_root: Path) -> ServerConfig:
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError("Every MCP server must have a non-empty name")
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Server {name!r} must be a JSON object")

    command = _optional_string(raw.get("command"), name=name, field_name="command")
    url = _optional_string(raw.get("url"), name=name, field_name="url")
    if (command is None) == (url is None):
        raise ConfigurationError(
            f"Server {name!r} must define exactly one of 'command' or 'url'"
        )

    raw_args = raw.get("args", [])
    if not isinstance(raw_args, list) or not all(
        isinstance(value, str) for value in raw_args
    ):
        raise ConfigurationError(f"Server {name!r} field 'args' must be a string list")
    if url is not None and raw_args:
        raise ConfigurationError(f"HTTP server {name!r} cannot define 'args'")

    raw_env = raw.get("env", {})
    if not isinstance(raw_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in raw_env.items()
    ):
        raise ConfigurationError(f"Server {name!r} field 'env' must map strings to strings")

    timeout = raw.get("timeoutSeconds", 60.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigurationError(
            f"Server {name!r} field 'timeoutSeconds' must be a positive number"
        )

    workspace_text = str(workspace_root)

    def expand(value: str) -> str:
        return value.replace("${workspaceRoot}", workspace_text)

    raw_cwd = _optional_string(raw.get("cwd"), name=name, field_name="cwd")
    cwd = workspace_root
    if raw_cwd:
        configured_cwd = Path(expand(raw_cwd))
        if not configured_cwd.is_absolute():
            configured_cwd = workspace_root / configured_cwd
        cwd = configured_cwd.resolve()

    if url is not None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError(f"Server {name!r} has an invalid HTTP URL")

    return ServerConfig(
        name=name,
        command=command,
        args=tuple(expand(value) for value in raw_args),
        url=url,
        env={key: expand(value) for key, value in raw_env.items()},
        cwd=cwd,
        timeout_seconds=float(timeout),
    )


def _optional_string(value: object, *, name: str, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"Server {name!r} field {field_name!r} must be a non-empty string"
        )
    return value
