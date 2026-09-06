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
    "spectral_index":   ["spectral_index"],
    "compound":         [],   # resolved dynamically by query decomposition
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
    "spectral_index": "Spectral index (NDVI/NDWI/NDBI)",
    "compound": "Compound analysis",
}

# ---------------------------------------------------------------------------
# MODEL REGISTRY (PS wording: "select the most suitable model or tool from the
# predefined registry") — per-task routing between the cloud flagship and the
# locally-served RS-adapted weights.
# ---------------------------------------------------------------------------
MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "rs_landcover": {
        "scope": ("single_caption", "bi_change", "bi_change_vqa", "cross_modal"),
        "local": "lora",        # BigEarthNet-adapted weights shine here
        "cloud": "flagship",
        "rationale": "RS-domain tasks favour the RS-adapted weights when the "
                     "air-gapped LoRA server is available; flagship otherwise",
    },
    "general": {
        "scope": ("single_vqa", "single_vqa_count", "single_ground",
                  "spectral_index", "compound"),
        "local": "base",         # generic capability, adapter not required
        "cloud": "flagship",
        "rationale": "general visual reasoning uses the strongest available "
                     "base model",
    },
}


def select_model(task_type: str, vlm_mode: str,
                 lora_served: bool = False) -> tuple[str, str]:
    """Returns (model_id_hint, reason) from the model registry.
    `model_id_hint` is 'lora' | 'base' | 'flagship' — the VLM client resolves
    the hint to a concrete served model name."""
    for profile in MODEL_REGISTRY.values():
        if task_type in profile["scope"]:
            if vlm_mode == "local":
                hint = profile["local"]
                if hint == "lora" and not lora_served:
                    return "base", (profile["rationale"] +
                                    " (adapter not served — base weights used)")
                return hint, profile["rationale"]
            return profile["cloud"], profile["rationale"]
    return "flagship", "default registry entry"


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
            return []               # resolved by the controller's query decomposition
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
