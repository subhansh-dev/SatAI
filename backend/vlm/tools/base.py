"""
SatAI — Base Tool
All specialist tools inherit from this. The base class owns:
- the VLM calling convention (system prompt + RS-expert user prompt + images)
- a structured confidence protocol: the model must end its answer with a final
  line  `CONFIDENCE: <0-100>`  which is parsed out and reported honestly.
  (The old build returned hardcoded constants — fabricated confidence.)
- timing + parameter recording for the auditable execution trace
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from ..vlm_client import VLMClient, VLMError

logger = logging.getLogger("satai.tools")

# accepts "CONFIDENCE: 85", "CONFIDENCE: 0.85", "CONFIDENCE = 92%"
_CONF_RE = re.compile(r"CONFIDENCE\s*[:=]\s*([0-9]{1,3}(?:\.[0-9]+)?)", re.IGNORECASE)


class BaseTool:
    tool_id: str = "base"
    description: str = "Base tool — override in subclass"
    required_images: int = 1                 # 1 | 2 (exact), "1+" = one or more
    allowed_params: List[str] = []           # controller may only pass these
    ps_requirement: str = ""                 # maps tool -> PS SIH26167 deliverable

    def __init__(self, vlm: VLMClient):
        self.vlm = vlm

    # ------------------------------------------------------------------ api
    async def execute(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    # ------------------------------------------------------------------ vlm
    async def ask(self, system: str, user: str, images: List[str],
                  max_tokens: int = 768, temperature: float = 0.1,
                  response_json: bool = False,
                  model: Optional[str] = None) -> Tuple[str, float, Dict[str, Any]]:
        """
        One VLM round-trip. Returns (text_without_confidence, confidence, meta).
        Confidence protocol: model appends `CONFIDENCE: NN` as the final line.
        `model` = optional registry hint (lora | base | flagship) or concrete id.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        data = await self.vlm.query(messages=messages, images=images,
                                    max_tokens=max_tokens, temperature=temperature,
                                    response_json=response_json, model=model)
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not isinstance(raw, str):
            raw = str(raw)

        confidence, self_reported = self._extract_confidence(raw)
        text = _CONF_RE.sub("", raw).strip()
        meta = {
            "model": self.vlm.active_model,
            "vlm_latency_ms": self.vlm.last_latency_ms,
            "self_reported_confidence": self_reported,
            "usage": self.vlm.last_usage,
        }
        return text, confidence, meta

    @staticmethod
    def _extract_confidence(raw: str) -> Tuple[float, bool]:
        matches = _CONF_RE.findall(raw)
        if matches:
            try:
                val = float(matches[-1])
                if val > 1.0:            # 0-100 scale
                    val /= 100.0
                # values in (0,1] were already fractions ("CONFIDENCE: 0.85")
                return max(0.0, min(val, 1.0)), True
            except ValueError:
                pass
        return 0.6, False   # neutral fallback, flagged as not self-reported

    # ------------------------------------------------------------------ wrap
    def wrap(self, result: Dict[str, Any], start: float,
             params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        elapsed = (time.time() - start) * 1000
        return {
            "tool_id": self.tool_id,
            "text": result.get("text", ""),
            "bounding_boxes": result.get("bounding_boxes"),
            "change_stats": result.get("change_stats"),
            "confidence": float(result.get("confidence", 0.0)),
            "confidence_source": result.get("confidence_source",
                                            "model_self_report"),
            "parameters_used": params or {},
            "execution_time_ms": round(elapsed, 2),
            "model": result.get("model", self.vlm.active_model),
            "metadata": result.get("metadata"),
        }
