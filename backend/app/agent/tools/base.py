"""Base classes and registry for database agent tools."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass
class Tool:
    """Definition and execution binding for an agent tool."""

    name: str
    description: str
    args_schema: type[BaseModel]
    handler: Callable[[Any], Awaitable[dict[str, Any]]]

    def to_openai_schema(self) -> dict[str, Any]:
        """Format tool schema for OpenAI chat completions API."""
        schema = self.args_schema.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


class ToolRegistry:
    """Registry managing available agent tools and validating arguments."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def to_openai_schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI-compatible tool specifications for all registered tools."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
        """Validate arguments and safely execute the named tool handler.

        Never raises an uncaught exception to the caller.
        """
        tool = self._tools.get(name)
        if not tool:
            available = ", ".join(sorted(self._tools.keys()))
            return {
                "ok": False,
                "error": f"Unknown tool '{name}'. Available tools: {available}",
            }

        try:
            parsed_args = tool.args_schema.model_validate(raw_args)
        except ValidationError as e:
            return {
                "ok": False,
                "error": f"Invalid arguments for tool '{name}': {e.errors()}",
            }

        try:
            return await tool.handler(parsed_args)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"Tool execution failed internally: {exc}",
            }
