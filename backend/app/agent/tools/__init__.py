"""Agent tools package and default registry initialization."""

from app.agent.tools.analyze_query_plan import analyze_query_plan_tool
from app.agent.tools.base import Tool, ToolRegistry
from app.agent.tools.execute_query import execute_readonly_query_tool
from app.agent.tools.explain_query import explain_query_tool
from app.agent.tools.inspect_schema import inspect_schema_tool
from app.agent.tools.query_history import get_query_history_tool
from app.agent.tools.validate_sql import validate_sql_tool


def get_default_tool_registry() -> ToolRegistry:
    """Instantiate and populate the standard agent tool registry."""
    registry = ToolRegistry()
    registry.register(inspect_schema_tool)
    registry.register(validate_sql_tool)
    registry.register(execute_readonly_query_tool)
    registry.register(explain_query_tool)
    registry.register(get_query_history_tool)
    registry.register(analyze_query_plan_tool)
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "analyze_query_plan_tool",
    "execute_readonly_query_tool",
    "explain_query_tool",
    "get_default_tool_registry",
    "get_query_history_tool",
    "inspect_schema_tool",
    "validate_sql_tool",
]

