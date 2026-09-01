"""
SatAI — Base Tool
All specialist tools inherit from this.
"""
import time
import logging
from typing import Any

logger = logging.getLogger("satai.tools")


class BaseTool:
    """Base class for all specialist tools in the agentic registry."""

    tool_id: str = "base"
    description: str = "Base tool — override in subclass"
    required_inputs: list[str] = []

    async def execute(self, **kwargs) -> dict:
        """Run the tool. Must return dict with at least 'text' and 'confidence'."""
        raise NotImplementedError(f"{self.tool_id}: execute() not implemented")

    def _wrap(self, result: dict, start: float) -> dict:
        """Wrap result with tool metadata and timing."""
        elapsed_ms = (time.time() - start) * 1000
        return {
            "tool_id": self.tool_id,
            "execution_time_ms": round(elapsed_ms, 2),
            "text": result.get("text", ""),
            "confidence": result.get("confidence", 0.5),
            "bounding_boxes": result.get("bounding_boxes"),
            "change_mask": result.get("change_mask"),
            "metadata": result.get("metadata"),
        }
