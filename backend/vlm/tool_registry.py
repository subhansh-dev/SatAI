"""
SatAI — Tool Registry
Manages specialist tools and selects the right ones per task.
"""
from typing import Protocol, Optional

class Tool(Protocol):
    tool_id: str
    description: str
    required_inputs: list[str]
    async def execute(self, **kwargs) -> dict: ...


# Task -> (tool_ids) mapping
TASK_TOOLS: dict[str, list[str]] = {
    "single_vqa":       ["vqa"],
    "single_caption":   ["caption"],
    "single_ground":    ["ground"],
    "bi_change":        ["change_desc"],
    "bi_change_vqa":    ["change_desc", "vqa"],
    "cross_modal":      ["sar_fusion"],
    "env_analysis":     ["env_scan"],
    "compound":         ["vqa", "change_desc", "env_scan"],
}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id)

    def list_tools(self) -> list[dict]:
        return [
            {"id": t.tool_id, "description": t.description, "inputs": t.required_inputs}
            for t in self._tools.values()
        ]

    def select(self, task_type: str) -> list[str]:
        return TASK_TOOLS.get(task_type, ["vqa"])

    @property
    def tool_ids(self) -> list[str]:
        return list(self._tools.keys())


# Singleton — import and use everywhere
registry = ToolRegistry()
