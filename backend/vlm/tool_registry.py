"""
SatAI — Specialist Tool Registry
Maps task types -> ordered tool pipelines. Each tool declares its
`allowed_params`; the controller may only configure those parameters
(PS: "Configure only permitted parameters and execute the workflow").
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class Tool(Protocol):
    tool_id: str
    description: str
    required_images: int
    allowed_params: List[str]
    ps_requirement: str
    async def execute(self, **kwargs) -> Dict[str, Any]: ...


TASK_TOOLS: Dict[str, List[str]] = {
    "single_vqa":       ["vqa"],
    "single_vqa_count": ["numeric"],
    "single_caption":   ["caption"],
    "single_ground":    ["ground"],
    "bi_change":        ["change_desc"],
    "bi_change_vqa":    ["change_desc"],
    "cross_modal":      ["sar_fusion", "ground"],
    "compound":         [],   # resolved dynamically by image count
}

# Human-readable task names (used in trace + frontend)
TASK_LABELS: Dict[str, str] = {
    "single_vqa": "Single-image VQA",
    "single_vqa_count": "Single-image VQA (quantitative)",
    "single_caption": "Scene captioning",
    "single_ground": "Region grounding",
    "bi_change": "Change description",
    "bi_change_vqa": "Change-based VQA",
    "cross_modal": "Optical + SAR fusion",
    "compound": "Compound analysis",
}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id)

    def tool_ids(self) -> List[str]:
        return list(self._tools.keys())

    def select(self, task_type: str, num_images: int = 1) -> List[str]:
        if task_type == "compound":
            if num_images >= 2:
                return ["change_desc", "vqa", "caption"]
            return ["caption", "vqa"]
        return TASK_TOOLS.get(task_type, ["vqa"])

    def list_tools(self) -> List[Dict[str, Any]]:
        return [{
            "id": t.tool_id,
            "description": t.description,
            "required_images": t.required_images,
            "allowed_params": t.allowed_params,
            "ps_requirement": t.ps_requirement,
        } for t in self._tools.values()]


registry = ToolRegistry()
