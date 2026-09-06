"""
SatAI — Deterministic mock VLM backend for tests.

Replaces `Controller.vlm` (and the tools' client). Routes on the *system
prompt signature* of each specialist tool, returning OpenAI-shaped
completion dicts — exactly what BaseTool.ask() consumes.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import PIL.Image


def _completion(text: str) -> Dict[str, Any]:
    return {"choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10}}


class MockVLM:
    """Offline stand-in for VLMClient with tool-signature routing."""

    mode = "mock"
    active_model = "mock-qwen2.5-vl"
    configured = True
    lora_adapter = None
    request_count = 0
    last_latency_ms = 12.5
    last_usage: Optional[Dict[str, Any]] = {"total_tokens": 20}

    async def query(self, messages: List[Dict[str, Any]],
                    images: Optional[List[str]] = None,
                    max_tokens: Optional[int] = None,
                    temperature: Optional[float] = None,
                    response_json: bool = False,
                    model: Optional[str] = None) -> Dict[str, Any]:
        self.request_count += 1
        system = str(messages[0].get("content", ""))
        user = str(messages[1].get("content", "")) if len(messages) > 1 else ""

        # sanity: images arrive as base64 in the (mock) call when provided
        if images:
            assert isinstance(images[0], str) and len(images[0]) > 100

        if "task router" in system:
            return _completion(self._classify(user))
        if "SatAI-Ground" in system:
            boxes = [{"label": "water body", "bbox": [120, 140, 640, 520],
                      "confidence": 0.91}]
            return _completion(json.dumps(boxes))
        if "SatAI-Count" in system:
            return _completion(
                "Counting row by row across the scene.\n"
                "ANSWER: 5\nCONFIDENCE: 88")
        if "SatAI-Change" in system:
            return _completion(
                "CHANGE SUMMARY: A new built-up cluster appeared in the "
                "north-east; vegetation decreased correspondingly.\n"
                "CHANGED AREAS: north-east quadrant, vegetation -> built-up, "
                "~8% of scene.\nDIRECTION: built-up increase, vegetation "
                "decrease.\nMAGNITUDE: moderate, ~8% of scene.\n"
                "CONFUSERS: seasonal illumination differences minimal.\n"
                "CONFIDENCE: 82")
        if "SatAI-Fusion" in system:
            return _completion(
                "OPTICAL OBSERVATIONS: dense urban fabric, roads visible.\n"
                "SAR OBSERVATIONS: bright radar doubles over built-up areas, "
                "dark smooth water.\nJOINT FINDINGS: built-up confirmed by "
                "doubles; calm water dark in both sensors.\nBUILT-UP AREAS: "
                "centre and east, high confidence.\nWATER-COVERED AREAS: "
                "river along west edge, high confidence.\nCAVEATS: speckle "
                "noise in SAR.\nCONFIDENCE: 79")
        if "scene-description engine" in system:
            return _completion(
                "SCENE OVERVIEW: peri-urban agricultural setting.\n"
                "LAND COVER: cropland ~55%, built-up ~20%, vegetation ~15%, "
                "water ~10%.\nMAJOR OBJECTS: road network, farm plots, canal.\n"
                "SPATIAL PATTERN: fields oriented north-south.\n"
                "SENSOR NOTES: optical multispectral, ~10 m GSD.\n"
                "CONFIDENCE: 90")
        if "specialising in satellite" in system:
            return _completion(
                "The scene is predominantly agricultural with scattered "
                "built-up patches and a water channel along the west.\n"
                "CONFIDENCE: 85")
        return _completion("mock ok")

    # -------------------------------------------------------------- router
    @staticmethod
    def _classify(user_prompt: str) -> str:
        """Mirrors the controller's rule set for the ambiguous remainder."""
        # only the "Query: ..." line matters — the prompt also embeds the
        # task list whose wording would otherwise match keywords
        query = ""
        for line in user_prompt.splitlines():
            if line.strip().lower().startswith("query:"):
                query = line.split(":", 1)[1].lower()
                break
        if "how many" in query or "count" in query:
            return "single_vqa_count"
        if "highlight" in query or "locate" in query:
            return "single_ground"
        if "describe" in query or "caption" in query:
            return "single_caption"
        if "chang" in query:
            return "bi_change"
        return "single_vqa"

    # -------------------------------------------------------------- probes
    async def health_check(self, force: bool = False) -> bool:
        return True

    async def close(self) -> None:
        return None
