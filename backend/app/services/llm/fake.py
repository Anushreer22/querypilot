from typing import Any

from pydantic import BaseModel

from app.services.llm.base import (
    LLMClient,
    LLMInvalidResponse,
    ToolCall,
    ToolCompletionResult,
)


class FakeLLM(LLMClient):
    """Scriptable test double for LLM operations."""

    def __init__(
        self,
        responses: list[dict[str, Any] | Exception] | None = None,
        default_response: dict[str, Any] | None = None,
        tool_responses: list[ToolCompletionResult | Exception] | None = None,
        default_tool_response: ToolCompletionResult | None = None,
    ) -> None:
        self.responses: list[dict[str, Any] | Exception] = list(responses or [])
        self.default_response: dict[str, Any] = default_response or {
            "sql": "SELECT id, name FROM users LIMIT 10",
            "explanation": "Default fake response",
            "assumptions": [],
            "needs_clarification": False,
            "clarification_question": None,
        }
        self.calls: list[dict[str, Any]] = []

        self.tool_responses: list[ToolCompletionResult | Exception] = list(tool_responses or [])
        self.default_tool_response = default_tool_response or ToolCompletionResult(
            content="Default fake agent answer."
        )
        self.tool_calls_history: list[dict[str, Any]] = []

    def enqueue(self, item: dict[str, Any] | Exception) -> None:
        """Add a scripted response or exception to the front of the queue."""
        self.responses.append(item)

    def enqueue_tool_response(self, item: ToolCompletionResult | Exception) -> None:
        """Add a scripted tool completion response or exception to the queue."""
        self.tool_responses.append(item)

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Record the call and return the next scripted response or raise scripted error."""
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema": schema,
        })

        if self.responses:
            next_resp = self.responses.pop(0)
            if isinstance(next_resp, Exception):
                raise next_resp
            if not isinstance(next_resp, dict):
                raise LLMInvalidResponse(f"Fake response must be dict, got {type(next_resp).__name__}")
            return next_resp

        return dict(self.default_response)

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ToolCompletionResult:
        """Record the tool call and return scripted ToolCompletionResult or raise scripted error."""
        self.tool_calls_history.append({
            "messages": messages,
            "tools": tools,
        })

        if self.tool_responses:
            next_resp = self.tool_responses.pop(0)
            if isinstance(next_resp, Exception):
                raise next_resp
            if not isinstance(next_resp, ToolCompletionResult):
                raise LLMInvalidResponse(
                    f"Fake tool response must be ToolCompletionResult, got {type(next_resp).__name__}"
                )
            return next_resp

        # Dynamic fallback for live manual verification and offline testing
        last_msg = messages[-1] if messages else {}
        last_role = last_msg.get("role", "")
        last_content = str(last_msg.get("content", ""))

        if last_role == "user":
            lower_content = last_content.lower()
            if "drop table" in lower_content or "delete" in lower_content or "ignore" in lower_content:
                return ToolCompletionResult(
                    content="I cannot execute destructive statements such as DROP TABLE. QueryPilot is restricted to read-only queries."
                )
            if "how did the store perform" in lower_content or "ambiguous" in lower_content:
                return ToolCompletionResult(
                    content="Could you please clarify whether you mean total revenue, total order volume, or average order value?"
                )
            if "product" in lower_content or "expensive" in lower_content:
                return ToolCompletionResult(
                    tool_calls=[
                        ToolCall(id="call_inspect", name="inspect_schema", arguments={"table": "products"})
                    ]
                )
            return ToolCompletionResult(
                tool_calls=[
                    ToolCall(id="call_inspect", name="inspect_schema", arguments={"table": "users"})
                ]
            )

        if last_role == "tool":
            if 'name="inspect_schema"' in last_content:
                conv_text = str(messages).lower()
                if "expensive" in conv_text or "product" in conv_text:
                    return ToolCompletionResult(
                        tool_calls=[
                            ToolCall(
                                id="call_exec",
                                name="execute_readonly_query",
                                arguments={"sql": "SELECT id, name, price, stock FROM products ORDER BY price DESC LIMIT 5"},
                            )
                        ]
                    )
                return ToolCompletionResult(
                    tool_calls=[
                        ToolCall(
                            id="call_exec",
                            name="execute_readonly_query",
                            arguments={"sql": "SELECT id, name, email FROM users ORDER BY id ASC LIMIT 5"},
                        )
                    ]
                )
            if 'name="execute_readonly_query"' in last_content:
                return ToolCompletionResult(
                    content="Assumptions: All merchandise items are in active stock.\nBased on the query results, the top 5 most expensive products and their stock quantities were retrieved successfully from the database."
                )

        return self.default_tool_response


