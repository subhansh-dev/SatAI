"""
SatAI — Agentic Controller
Implements the PS-mandated orchestration loop:

  1. Interpret the query  -> classify the task (VLM judge + rule-based fallback)
  2. Check input images   -> number / modality / format / metadata / compatibility
  3. Select models+tools  -> from the specialist registry (predefined)
  4. Execute workflow     -> configuring ONLY permitted parameters
  5. Combine outputs      -> text + spatial evidence, confidence estimation
  6. Auditable summary    -> execution trace, visual evidence, GeoJSON, reports
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from core import config
from .image_utils import decode_b64, prepare_for_vlm, prepare_pair_for_vlm
from .input_validator import validate_inputs
from .schemas import (
    ExecutionTrace, ImageInput, Severity, ToolOutput, ValidationReport,
    VisualEvidenceItem, VLMResponse, QuerySummary,
)
from .tool_registry import TASK_LABELS, registry
from .vlm_client import VLMClient, VLMError
from .visual_evidence import (
    input_view_b64, render_change_map, render_grounding, side_by_side_b64,
)
from .tools.vqa_tool import VQATool
from .tools.caption_tool import CaptionTool
from .tools.ground_tool import GroundTool
from .tools.change_tool import ChangeDescTool
from .tools.sar_fusion_tool import SARFusionTool
from .tools.numeric_tool import NumericTool

logger = logging.getLogger("satai.controller")

_CLASSIFY_SYSTEM = (
    "You are the task router of a satellite-imagery analysis system. Classify "
    "the user request into EXACTLY one task type from the list. Reply with "
    "the task-type string only — no punctuation, no explanation.\n"
    "single_vqa — question about one image\n"
    "single_vqa_count — counting/quantity question about one image\n"
    "single_caption — describe / summarise one image\n"
    "single_ground — find / locate / highlight a referred object in one image\n"
    "bi_change — two dates, open-ended 'what changed'\n"
    "bi_change_vqa — two dates plus a specific question about the change\n"
    "cross_modal — optical + SAR pair used together\n"
    "compound — the request mixes several of the above"
)

_COUNT_RE = __import__("re").compile(
    r"\b(how many|number of|count|how much (?:area|percentage)|what percentage)\b",
    __import__("re").IGNORECASE)
_GROUND_RE = __import__("re").compile(
    r"\b(highlight|locate|find|mark|show me|where is|bound(ing|ary) box|outline)\b",
    __import__("re").IGNORECASE)
_CHANGE_RE = __import__("re").compile(
    r"\b(chang|differ|before|after|two dates|between (?:these )?(?:two |the )?(?:dates|images|years))\b",
    __import__("re").IGNORECASE)
_DESCRIBE_RE = __import__("re").compile(
    r"\b(describe|caption|what do you see|summaris|summariz|land.?cover)\b",
    __import__("re").IGNORECASE)


class QueryStore:
    """Bounded in-memory store of recent full responses (audits + reports)."""

    def __init__(self, size: int = 50):
        self._size = size
        self._store: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    def put(self, response: Dict[str, Any]) -> None:
        qid = response.get("query_id")
        if not qid:
            return
        self._store[qid] = response
        while len(self._store) > self._size:
            self._store.popitem(last=False)

    def get(self, query_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(query_id)

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for resp in reversed(self._store.values()):
            trace = resp.get("trace") or {}
            out.append({
                "query_id": resp.get("query_id"),
                "query": (trace.get("query") or "")[:200],
                "task_type": resp.get("task_type", ""),
                "confidence": resp.get("confidence", 0.0),
                "timestamp": trace.get("timestamps", {}).get("received", ""),
                "num_images": len(trace.get("validation", {}).get("images", [])
                                  if trace.get("validation") else []),
                "status": resp.get("status", "ok"),
            })
        return out


class Controller:
    def __init__(self):
        self.vlm = VLMClient()
        self.store = QueryStore(config.QUERY_STORE_SIZE)
        self._register_tools()

    def _register_tools(self) -> None:
        registry.register(VQATool(self.vlm))
        registry.register(NumericTool(self.vlm))
        registry.register(CaptionTool(self.vlm))
        registry.register(GroundTool(self.vlm))
        registry.register(ChangeDescTool(self.vlm))
        registry.register(SARFusionTool(self.vlm))

    # ------------------------------------------------------------ pipeline
    async def execute(self, query: str, images: List[ImageInput],
                      mode: str = "auto",
                      metadata: Optional[Dict[str, Any]] = None) -> VLMResponse:
        t_start = time.time()
        metadata = dict(metadata or {})
        notes: List[str] = []
        ts = {"received": time.strftime("%Y-%m-%dT%H:%M:%SZ")}

        # ---- Step 1: input validation (PS: compatibility checking) --------
        validation = validate_inputs(images, mode, metadata)
        if not validation.accepted:
            errors = [i.message for i in validation.issues
                      if i.level == Severity.ERROR]
            return self._reject(query, mode, validation, errors, t_start, ts)

        # ---- Step 2: task classification ----------------------------------
        forced = metadata.get("force_task")
        if forced and forced in TASK_LABELS and \
                not (forced in ("bi_change", "bi_change_vqa", "cross_modal",
                                "compound") and len(validation.images) < 2):
            task_type = forced
            class_reason, class_conf = "direct tool endpoint (forced task)", 1.0
        else:
            task_type, class_reason, class_conf = await self.classify(
                query, validation, mode)
        ts["classified"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # ---- Step 3: tool selection (predefined registry) ------------------
        n_images = len(validation.images)
        tool_ids = registry.select(task_type, n_images)
        # cross-modal: grounding sub-step needs only 1 image; drop if explicit
        if task_type == "cross_modal" and metadata.get("no_grounding"):
            tool_ids = ["sar_fusion"]
        logger.info("task=%s tools=%s", task_type, tool_ids)

        # ---- Step 4: prepare VLM-ready views of every image ----------------
        vlm_images: List[str] = []
        prepare_notes: List[Dict[str, Any]] = []
        pair_task = task_type in ("bi_change", "bi_change_vqa") or \
            (task_type == "compound" and len(images) >= 2)
        try:
            if pair_task and len(images) >= 2:
                # joint radiometric normalisation — mandatory for honest diffs
                raws = [decode_b64(i.data) for i in images[:2]]
                sar = [validation.images[i].detected_modality == "sar"
                       for i in range(2)]
                b64a, b64b, ia, ib = prepare_pair_for_vlm(
                    raws[0], raws[1], sar[0], sar[1],
                    max_side=config.VLM_MAX_SIDE)
                vlm_images, prepare_notes = [b64a, b64b], [ia, ib]
                images_rest = images[2:]
                rest_start = 2
            else:
                images_rest = images
                rest_start = 0
            for i, img_in in enumerate(images_rest, start=rest_start):
                raw = decode_b64(img_in.data)
                is_sar = (validation.images[i].detected_modality == "sar"
                          if i < len(validation.images) else False)
                b64, info = prepare_for_vlm(raw, is_sar=is_sar,
                                            max_side=config.VLM_MAX_SIDE)
                vlm_images.append(b64)
                prepare_notes.append(info)
        except ValueError:
            pass  # already rejected during validation
        if any(p.get("downscaled_to") or
               (p.get("stretch") not in (None, "none")) or
               p.get("normalisation") for p in prepare_notes):
            notes.append("Images normalised for the VLM (percentile/log "
                         f"stretch, downscale to {config.VLM_MAX_SIDE}px"
                         + (", shared pair normalisation for honest change "
                            "comparison" if pair_task else "") + ").")

        # ---- Step 5: execute tools with permitted params only --------------
        tool_outputs: List[ToolOutput] = []
        for tid in tool_ids:
            tool = registry.get(tid)
            if tool is None:
                notes.append(f"tool '{tid}' missing — skipped")
                continue
            params = self._permitted_params(tool, metadata)
            t0 = time.time()
            try:
                raw_out = await tool.execute(
                    query=query, images=vlm_images,
                    metadata=metadata, **params)
            except VLMError as e:
                logger.warning("tool %s VLM error: %s", tid, e)
                tool_outputs.append(ToolOutput(
                    tool_id=tid,
                    text=f"The vision-language backend could not complete this "
                         f"step ({e}). Check VLM_MODE / API key / server.",
                    confidence=0.0, confidence_source="error",
                    parameters_used=params,
                    execution_time_ms=round((time.time() - t0) * 1000, 2)))
                continue
            except Exception as e:  # tool bug must not kill the pipeline
                logger.exception("tool %s crashed", tid)
                tool_outputs.append(ToolOutput(
                    tool_id=tid, text=f"Specialist tool '{tid}' failed: {e}",
                    confidence=0.0, confidence_source="error",
                    parameters_used=params,
                    execution_time_ms=round((time.time() - t0) * 1000, 2)))
                continue
            raw_out.setdefault("tool_id", tid)
            tool_outputs.append(ToolOutput(**{
                k: v for k, v in raw_out.items() if k in ToolOutput.model_fields
            }))

        ts["tools_done"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # ---- Step 6: combine outputs + confidence --------------------------
        final_text = self._assemble_response(task_type, tool_outputs, query)
        confidence = self._overall_confidence(tool_outputs)

        # ---- Step 7: visual evidence (PS: text + visual results) -----------
        evidence = self._build_evidence(task_type, tool_outputs, vlm_images,
                                        validation)

        # ---- Step 8: GeoJSON for grounding outputs -------------------------
        geojson = self._boxes_to_geojson(tool_outputs, validation, metadata)

        # ---- Step 9: auditable execution trace ------------------------------
        total_ms = round((time.time() - t_start) * 1000, 2)
        trace = ExecutionTrace(
            mode_requested=mode,
            task_type=task_type,
            task_confidence=class_conf,
            classification_reason=class_reason,
            tools_selected=tool_ids,
            tools_invoked=[o.tool_id for o in tool_outputs],
            tool_outputs=tool_outputs,
            validation=validation,
            model=self.vlm.active_model,
            vlm_mode=self.vlm.mode,
            timestamps=ts,
            total_execution_time_ms=total_ms,
            notes=notes,
        )
        trace.timestamps = ts

        resp = VLMResponse(
            query_id=trace.query_id,
            status="ok",
            response=final_text,
            task_type=task_type,
            confidence=confidence,
            visual_evidence=evidence,
            geojson=geojson,
            validation=validation,
            trace=trace,
            report_url=f"/vlm/report/{trace.query_id}",
            execution_time_ms=total_ms,
        )
        payload = resp.model_dump()
        payload["trace"]["query"] = query          # keep query text for history
        payload["trace"]["image_preparation"] = prepare_notes
        self.store.put(payload)
        return resp

    # ------------------------------------------------------------ classify
    async def classify(self, query: str, validation: ValidationReport,
                       mode: str) -> tuple[str, str, float]:
        """Returns (task_type, reason, confidence)."""
        n = len(validation.images)
        mods = [m.detected_modality for m in validation.images]

        # explicit user mode wins (deterministic, zero-latency)
        if mode == "crossmodal" and n == 2:
            return "cross_modal", "user-selected cross-modal mode", 1.0
        if mode == "bitemporal" and n == 2:
            return ("bi_change_vqa" if self._is_specific(query)
                    else "bi_change"), "user-selected bi-temporal mode", 1.0
        if mode == "single" and n >= 1:
            task = self._rule_classify(query, n)
            return task, "user-selected single-image mode (rule-based)", 0.95

        # strong lexical shortcuts first (cheaper + more reliable than VLM)
        rule = self._rule_classify(query, n)
        if n >= 2:
            if mods and "sar" in mods and "optical" in mods:
                return "cross_modal", "modality detection: optical + SAR pair", 0.95
            if rule in ("bi_change", "bi_change_vqa", "compound"):
                return rule, f"rule-based on 2 images + query pattern", 0.9
        elif rule in ("single_vqa_count", "single_ground", "single_caption"):
            return rule, "high-confidence keyword rule", 0.9

        # VLM-as-judge for the ambiguous remainder
        try:
            prompt = (
                "Task list:\n" + "\n".join(
                    f"- {k}" for k in TASK_LABELS) +
                f"\n\nQuery: {query}\nImages: {n} "
                f"(modalities: {', '.join(mods) or 'unknown'})\n"
                "Reply with one task-type string."
            )
            data = await self.vlm.query(
                messages=[{"role": "system", "content": _CLASSIFY_SYSTEM},
                          {"role": "user", "content": prompt}],
                max_tokens=24, temperature=0.0)
            raw = (data.get("choices") or [{}])[0].get("message", {}) \
                .get("content", "")
            task = str(raw).strip().lower().strip('"\' .')
            if task in TASK_LABELS:
                return task, "VLM task router", 0.85
        except VLMError:
            pass
        return rule, "fallback rule-based classification", 0.6

    def _rule_classify(self, query: str, n: int) -> str:
        q = query or ""
        has_change = bool(_CHANGE_RE.search(q))
        has_count = bool(_COUNT_RE.search(q))
        has_ground = bool(_GROUND_RE.search(q))
        has_desc = bool(_DESCRIBE_RE.search(q))
        if n >= 2:
            # compound = change question that ALSO asks to describe/locate/count
            if has_change and sum((has_desc, has_count, has_ground)) >= 1:
                return "compound"
            return "bi_change_vqa" if self._is_specific(q) else "bi_change"
        if has_count:
            return "single_vqa_count"
        if has_ground:
            return "single_ground"
        if has_desc:
            return "single_caption"
        return "single_vqa"

    @staticmethod
    def _is_specific(query: str) -> bool:
        """A change question is 'specific' when it asks about a class/region."""
        q = (query or "").lower()
        generic = ("what changed between these two dates", "what changed",
                   "describe the change", "any change", "changes?")
        return len(q) > 40 and not any(g in q for g in generic)

    @staticmethod
    def _is_multi_intent(query: str) -> bool:
        q = (query or "").lower()
        markers = (" and ", "; ", " also ", " then ", "plus ")
        return any(m in q for m in markers)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _permitted_params(tool: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Only parameters the tool explicitly allows may be configured."""
        return {k: metadata[k] for k in getattr(tool, "allowed_params", [])
                if k in metadata}

    def _assemble_response(self, task_type: str, outputs: List[ToolOutput],
                           query: str) -> str:
        good = [o for o in outputs if o.text]
        if not good:
            return ("Analysis could not be completed — the vision-language "
                    "backend returned no content. Check the execution trace "
                    "and VLM configuration.")
        if len(good) == 1:
            return good[0].text or ""
        headers = {
            "change_desc": "CHANGE ANALYSIS",
            "vqa": "ANSWER TO YOUR QUESTION",
            "caption": "SCENE DESCRIPTION",
            "numeric": "QUANTITATIVE ANSWER",
            "ground": "LOCALISATION",
            "sar_fusion": "OPTICAL + SAR FUSION",
        }
        parts = [f"**{headers.get(o.tool_id, o.tool_id.upper())}**\n{o.text}"
                 for o in good]
        return "\n\n".join(parts)

    @staticmethod
    def _overall_confidence(outputs: List[ToolOutput]) -> float:
        """Weighted mean — grounding/numeric parse success earns full weight,
        unself-reported fallbacks are dinged."""
        if not outputs:
            return 0.0
        weights = {"model_self_report": 1.0, "box_scores+parse": 1.0,
                   "parsed_answer+model_self_report": 1.0, "unparsed": 0.6,
                   "error": 0.0}
        num = sum(o.confidence * weights.get(o.confidence_source, 0.8)
                  for o in outputs)
        den = sum(weights.get(o.confidence_source, 0.8) for o in outputs)
        return round(num / den, 3) if den else 0.0

    def _build_evidence(self, task_type: str, outputs: List[ToolOutput],
                        vlm_images: List[str],
                        validation: ValidationReport) -> List[VisualEvidenceItem]:
        items: List[VisualEvidenceItem] = []
        try:
            for o in outputs:
                if o.tool_id == "ground" and o.bounding_boxes:
                    for k, im_b64 in enumerate(vlm_images[:1]):
                        ann, desc = render_grounding(im_b64, o.bounding_boxes)
                        items.append(VisualEvidenceItem(
                            kind="annotated_boxes",
                            title=f"Grounding — {len(o.bounding_boxes)} region(s)",
                            image_base64=ann, description=desc,
                            stats={"boxes": o.bounding_boxes}))
            if task_type in ("bi_change", "bi_change_vqa", "compound") \
                    and len(vlm_images) >= 2:
                cm = render_change_map(vlm_images[0], vlm_images[1])
                items.append(VisualEvidenceItem(
                    kind="change_map", title="Estimated spatial change map",
                    image_base64=cm["mask_b64"], description=cm["description"],
                    stats=cm["stats"]))
                items.append(VisualEvidenceItem(
                    kind="side_by_side", title="Before / After comparison",
                    image_base64=cm["side_b64"],
                    description="Bi-temporal pair, labelled."))
            elif task_type == "cross_modal" and len(vlm_images) >= 2:
                s, desc = side_by_side_b64(vlm_images[0], vlm_images[1],
                                           "OPTICAL", "SAR")
                items.append(VisualEvidenceItem(
                    kind="side_by_side", title="Optical | SAR composite",
                    image_base64=s, description=desc))
            # input views for every image (evidence strip)
            for i, meta in enumerate(validation.images[:4]):
                label = f"Image {i + 1} · {meta.detected_modality}"
                if meta.format:
                    label += f" · {meta.format}"
                iv, _ = input_view_b64(vlm_images[i], label)
                items.append(VisualEvidenceItem(
                    kind="input_view", title=f"Input {i + 1}",
                    image_base64=iv,
                    description=f"{meta.width}x{meta.height}, "
                                f"{meta.num_bands} band(s), modality: "
                                f"{meta.detected_modality}"))
        except Exception:
            logger.exception("visual evidence rendering failed")
        return items

    def _boxes_to_geojson(self, outputs: List[ToolOutput],
                          validation: ValidationReport,
                          metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for o in outputs:
            if not o.bounding_boxes:
                continue
            img_meta = validation.images[0] if validation.images else None
            if not img_meta:
                continue
            w, h = img_meta.width or 1, img_meta.height or 1
            geo = img_meta.extra_geo or {}
            crs_label, ring_transform = "image-pixel", None
            features = []
            for box in o.bounding_boxes:
                try:
                    x1, y1, x2, y2 = (float(v) for v in box["bbox"])
                except (KeyError, TypeError, ValueError):
                    continue
                px = [x1 / 1000 * w, y1 / 1000 * h, x2 / 1000 * w, y2 / 1000 * h]
                from .image_utils import pixel_to_geo
                crs_label, ring = pixel_to_geo(px, w, h, geo)
                if ring is None:
                    ring = [[px[0], px[1]], [px[2], px[1]],
                            [px[2], px[3]], [px[0], px[3]], [px[0], px[1]]]
                    coords_note = "pixel coordinates (no georeference)"
                else:
                    coords_note = "map coordinates from GeoTIFF geotransform"
                features.append({
                    "type": "Feature",
                    "properties": {
                        "label": box.get("label", ""),
                        "confidence": box.get("confidence"),
                        "pixel_bbox": [round(v, 1) for v in px],
                        "coordinate_system": coords_note,
                    },
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                })
            fc = {
                "type": "FeatureCollection",
                "crs": crs_label,
                "source_image": {
                    "width": w, "height": h,
                    "format": img_meta.format,
                    "georeferenced": img_meta.georeferenced,
                    "ground_sample_dist_m": img_meta.ground_sample_dist_m,
                },
                "features": features,
            }
            return fc
        return None

    # ------------------------------------------------------------ reject
    def _reject(self, query: str, mode: str, validation: ValidationReport,
                errors: List[str], t_start: float,
                ts: Dict[str, str]) -> VLMResponse:
        total_ms = round((time.time() - t_start) * 1000, 2)
        trace = ExecutionTrace(
            mode_requested=mode, task_type="rejected",
            classification_reason="input validation failed",
            tools_selected=[], tools_invoked=[],
            validation=validation, model=self.vlm.active_model,
            vlm_mode=self.vlm.mode, timestamps=ts,
            total_execution_time_ms=total_ms,
            notes=errors)
        resp = VLMResponse(
            query_id=trace.query_id, status="rejected",
            response="Input rejected by compatibility check:\n- "
                     + "\n- ".join(errors),
            task_type="rejected", confidence=0.0,
            validation=validation, trace=trace,
            report_url=f"/vlm/report/{trace.query_id}",
            execution_time_ms=total_ms)
        payload = resp.model_dump()
        payload["trace"]["query"] = query
        self.store.put(payload)
        return resp

    async def close(self) -> None:
        await self.vlm.close()


# ---------------------------------------------------------------------------
# Lazy singleton accessor (used by the API layer)
# ---------------------------------------------------------------------------
_controller: Optional[Controller] = None


async def get_controller() -> Controller:
    global _controller
    if _controller is None:
        _controller = Controller()
        logger.info("VLM Controller initialised (mode=%s, model=%s)",
                    _controller.vlm.mode, _controller.vlm.active_model)
    return _controller
