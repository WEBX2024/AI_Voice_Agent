"""
Tool registry and base interface.

Tools are callable functions that the LLM agent can invoke
during a conversation (e.g., calendar lookup, contact search).

Each tool is registered with a name, description, and callable.
The agent uses the tool selection prompt to decide when to invoke tools.
"""

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for agent tools.

    Tools are registered with a name, description, and function.
    The registry can be queried by the agent to discover available tools.
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, description: str, func: Callable):
        """Register a tool."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "func": func,
        }
        logger.info("Registered tool: %s", name)

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def execute(self, name: str, **kwargs) -> Any:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(name)
        if not tool:
            logger.warning("Tool not found: %s", name)
            return {"error": f"Tool '{name}' not found"}

        try:
            result = tool["func"](**kwargs)
            logger.info("Tool %s executed successfully", name)
            return result
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            return {"error": str(e)}

    def list_tools(self) -> list[dict[str, str]]:
        """List all registered tools (name + description)."""
        return [
            {"name": t["name"], "description": t["description"]}
            for t in self._tools.values()
        ]

    def describe_for_prompt(self) -> str:
        """Generate a text description of all tools for the system prompt."""
        if not self._tools:
            return "No tools are currently available."

        lines = ["Available tools:"]
        for tool in self._tools.values():
            lines.append(f"- **{tool['name']}**: {tool['description']}")
        return "\n".join(lines)
