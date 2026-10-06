from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_assistant.config import ConfigurationError, load_mcp_config


def test_loads_stdio_and_http_servers_and_expands_workspace(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "local": {
                        "command": "server-command",
                        "args": ["--root", "${workspaceRoot}"],
                        "env": {"PROJECT_ROOT": "${workspaceRoot}"},
                        "cwd": "services/local-mcp",
                    },
                    "remote": {
                        "url": "https://example.com/mcp",
                        "timeoutSeconds": 15,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_mcp_config(config_path)
    local, remote = config.servers

    assert config.workspace_root == tmp_path
    assert local.transport == "stdio"
    assert local.args[-1] == str(tmp_path)
    assert local.env["PROJECT_ROOT"] == str(tmp_path)
    assert local.cwd == tmp_path / "services" / "local-mcp"
    assert remote.transport == "http"
    assert remote.url == "https://example.com/mcp"
    assert remote.timeout_seconds == 15


def test_empty_server_object_is_valid_during_incremental_setup(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text('{"mcpServers": {}}', encoding="utf-8")

    assert load_mcp_config(config_path, workspace_root=tmp_path).servers == ()


@pytest.mark.parametrize(
    "server",
    [
        {},
        {"command": "local", "url": "https://example.com/mcp"},
        {"url": "not-a-url"},
        {"command": "local", "args": "not-a-list"},
        {"url": "https://example.com/mcp", "args": ["not-allowed"]},
        {"url": "https://example.com/mcp", "timeoutSeconds": 0},
    ],
)
def test_rejects_invalid_server_config(tmp_path: Path, server: dict[str, object]) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"broken": server}}), encoding="utf-8"
    )

    with pytest.raises(ConfigurationError):
        load_mcp_config(config_path, workspace_root=tmp_path)
