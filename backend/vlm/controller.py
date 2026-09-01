"""
SatAI — Agentic Controller
Interprets queries, classifies tasks, selects tools, executes, and returns
an auditable execution summary.
"""
import logging
import time
import json
from typing import Optional
from .vlm_client import VLMClient
from .tool_registry import registry
from .schemas import (
    VLMQuery, VLMResponse, ExecutionTrace, TaskType,
    InputMode, ToolOutput,
)
from .tools.vqa_tool import VQATool
from .tools.caption_tool import CaptionTool
from .tools.ground_tool import GroundTool
from .tools.change_tool import ChangeDescTool
from .tools.sar_fusion_tool import SARFusionTool
from .tools.env_tool import EnvScanTool

logger = logging.getLogger("satai.controller")


class Controller:
    def __init__(self):
        self.vlm = VLMClient()
        self._register_tools()

    def _register_tools(self):
        """Register all specialist tools."""
        registry.register(VQATool(self.vlm))
        registry.register(CaptionTool(self.vlm))
        registry.register(GroundTool(self.vlm))
        registry.register(ChangeDescTool(self.vlm))
        registry.register(SARFusionTool(self.vlm))
        registry.register(EnvScanTool())

    async def classify_task(self, query: str, num_images: int, mode: str) -> str:
        """Use the VLM to classify which task type this query needs."""
        prompt = (
            "You are a task classifier for a satellite imagery analysis system. "
            "Given a user query and the number of input images, classify the task.\n\n"
            f"Query: {query}\n"
            f"Number of images: {num_images}\n"
            f"Mode override: {mode}\n\n"
            "Available task types:\n"
            "- single_vqa: question about one image\n"
            "- single_caption: describe/summarize one image\n"
            "- single_ground: locate/find objects in one image\n"
            "- bi_change: what changed between two images (no specific question)\n"
            "- bi_change_vqa: specific question about changes between two images\n"
            "- cross_modal: analyze optical+SAR pair together\n"
            "- env_analysis: environmental context about a location\n\n"
            "Return ONLY the task type string, nothing else."
        )

        resp = await self.vlm.query(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
        )
        raw = resp.get("choices", [{}])[0].get("message", {}).get("content", "single_vqa")
        task = raw.strip().lower().strip('"').strip("'")

        valid = {t.value for t in TaskType}
        if task not in valid:
            task = self._fallback_classify(num_images, mode)
            logger.warning(f"Classifier returned invalid task '{raw}', using fallback: {task}")
        return task

    def _fallback_classify(self, num_images: int, mode: str) -> str:
        """Rule-based fallback when classifier fails."""
        if mode == "crossmodal":
            return "cross_modal"
        if mode == "bitemporal":
            return "bi_change"
        if num_images >= 2:
            return "bi_change"
        return "single_vqa"

    async def execute(self, query: str, images: list[str],
                      mode: str = "auto", metadata: Optional[dict] = None) -> VLMResponse:
        """Main entry point: classify -> select tools -> execute -> assemble."""
        start_total = time.time()
        metadata = metadata or {}

        # 1. Classify task
        if mode != "auto":
            task_type = self._fallback_classify(len(images), mode)
        else:
            task_type = await self.classify_task(query, len(images), mode)
        logger.info(f"Task classified: {task_type}")

        # 2. Select tools
        tool_ids = registry.select(task_type)
        logger.info(f"Tools selected: {tool_ids}")

        # 3. Execute tools in sequence
        tool_outputs = []
        for tid in tool_ids:
            tool = registry.get(tid)
            if not tool:
                logger.warning(f"Tool '{tid}' not found in registry, skipping")
                continue

            logger.info(f"Executing tool: {tid}")
            t0 = time.time()

            kwargs = {"query": query, "images": images}
            if tid == "env_scan":
                lat = metadata.get("lat", 0)
                lon = metadata.get("lon", 0)
                kwargs.update({"lat": lat, "lon": lon})
            if tid == "ground":
                kwargs["output_format"] = metadata.get("output_format", "hbb")

            result = await tool.execute(**kwargs)
            tool_outputs.append(result)
            logger.info(f"Tool {tid} completed in {result.get('execution_time_ms', 0):.0f}ms")

        # 4. Assemble final response
        final_text = self._assemble_response(tool_outputs)
        avg_conf = (
            sum(o.get("confidence", 0) for o in tool_outputs) / max(len(tool_outputs), 1)
        )

        # 5. Build execution trace
        trace = ExecutionTrace(
            task_type=task_type,
            tools_invoked=[o.get("tool_id", "") for o in tool_outputs],
            tool_outputs=[ToolOutput(**{k: v for k, v in o.items() if k in ToolOutput.model_fields}) for o in tool_outputs],
            final_response=final_text,
            total_execution_time_ms=round((time.time() - start_total) * 1000, 2),
        )

        # 6. Check for GeoJSON output (grounding tool)
        geojson = None
        for o in tool_outputs:
            if o.get("bounding_boxes"):
                geojson = self._boxes_to_geojson(o["bounding_boxes"], metadata)
                break

        return VLMResponse(
            query_id=trace.query_id,
            response=final_text,
            confidence=round(avg_conf, 3),
            geojson=geojson,
            trace=trace,
        )

    def _assemble_response(self, outputs: list[dict]) -> str:
        """Combine tool outputs into a coherent final answer."""
        texts = [o.get("text", "") for o in outputs if o.get("text")]
        if not texts:
            return "No analysis could be performed. Please check your inputs."
        if len(texts) == 1:
            return texts[0]
        # Multi-tool: join with headers
        parts = []
        for i, o in enumerate(outputs):
            tid = o.get("tool_id", f"tool_{i}")
            text = o.get("text", "")
            if text:
                parts.append(f"**{tid.replace('_', ' ').title()}**\n{text}")
        return "\n\n".join(parts)

    def _boxes_to_geojson(self, boxes: list[dict], metadata: dict) -> dict:
        """Convert pixel bounding boxes to approximate GeoJSON (if lat/lon metadata provided)."""
        lat = metadata.get("lat")
        lon = metadata.get("lon")
        if lat is None or lon is None:
            return {"type": "FeatureCollection", "features": []}

        features = []
        for box in boxes:
            bbox = box.get("bbox", [0, 0, 0, 0])
            # Approximate pixel-to-geo offset (1000px grid)
            dlat = (bbox[3] - bbox[1]) / 1000 * 0.01
            dlon = (bbox[2] - bbox[0]) / 1000 * 0.01
            features.append({
                "type": "Feature",
                "properties": {"label": box.get("label", ""), "confidence": box.get("confidence", 0)},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon + dlon * bbox[0], lat + dlat * bbox[1]],
                        [lon + dlon * bbox[2], lat + dlat * bbox[1]],
                        [lon + dlon * bbox[2], lat + dlat * bbox[3]],
                        [lon + dlon * bbox[0], lat + dlat * bbox[3]],
                        [lon + dlon * bbox[0], lat + dlat * bbox[1]],
                    ]],
                },
            })
        return {"type": "FeatureCollection", "features": features}

    async def close(self):
        await self.vlm.close()
