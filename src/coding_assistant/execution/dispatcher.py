"""Validate and dispatch model-requested MCP tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError,
    ValidationError,
)
from jsonschema.validators import validator_for  # type: ignore[import-untyped]

from coding_assistant.contracts import MCPClient, Payload


class _Validator(Protocol):
    def validate(self, instance: object) -> None:
        """Raise ``ValidationError`` when the instance violates the schema."""


class _ValidatorType(Protocol):
    def __call__(self, schema: Mapping[str, object]) -> _Validator:
        """Compile a schema into a validator instance."""

    def check_schema(self, schema: Mapping[str, object]) -> None:
        """Raise ``SchemaError`` when the schema is invalid."""


class ToolDispatcher:
    """Bind one discovered tool snapshot to validated MCP invocation."""

    def __init__(self, mcp_client: MCPClient) -> None:
        self._mcp_client = mcp_client
        self._validators: dict[str, _Validator] = {}

    async def discover(self) -> tuple[Payload, ...]:
        """Discover tools and atomically replace the validation registry."""

        tools = tuple(await self._mcp_client.list_tools())
        validators: dict[str, _Validator] = {}

        for index, tool in enumerate(tools):
            if not isinstance(tool, Mapping):
                raise ValueError(
                    f"Discovered tool at index {index} must be an object"
                )

            name = tool.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"Discovered tool at index {index} requires a non-empty string name"
                )
            if name in validators:
                raise ValueError(f"Discovered duplicate tool name {name!r}")

            schema_value = tool.get("input_schema")
            if not isinstance(schema_value, Mapping):
                raise ValueError(
                    f"Discovered tool {name!r} requires an object input_schema"
                )
            schema = dict(schema_value)
            validator_type = cast(_ValidatorType, validator_for(schema))
            try:
                validator_type.check_schema(schema)
            except SchemaError as error:
                raise ValueError(
                    f"Discovered tool {name!r} has an invalid input_schema: "
                    f"{error.message}"
                ) from error
            validators[name] = validator_type(schema)

        self._validators = validators
        return tools

    async def execute(self, name: str, arguments: Payload) -> Payload:
        """Validate one request and return its result or a model-visible error."""

        validator = self._validators.get(name)
        if validator is None:
            available = ", ".join(sorted(self._validators)) or "(none)"
            return _error_result(
                name,
                "unknown_tool",
                f"Unknown tool {name!r}; discovered tools: {available}",
            )

        try:
            validator.validate(arguments)
        except ValidationError as error:
            location = error.json_path
            return _error_result(
                name,
                "invalid_arguments",
                f"Invalid arguments for tool {name!r} at {location}: {error.message}",
            )

        try:
            return await self._mcp_client.call_tool(name, arguments)
        except Exception as error:
            detail = str(error) or type(error).__name__
            return _error_result(
                name,
                "tool_invocation_failed",
                f"Tool {name!r} failed: {detail}",
            )


def _error_result(name: str, code: str, message: str) -> Payload:
    return {
        "type": "tool_result",
        "name": name,
        "is_error": True,
        "error_code": code,
        "content": [{"type": "text", "text": message}],
    }
