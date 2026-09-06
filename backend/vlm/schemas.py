"""
SatAI — SatQuery AI · Schemas
Pydantic models for the agentic vision-language pipeline.
Every response carries an auditable execution trace (PS requirement).
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class InputMode(str, Enum):
    SINGLE = "single"            # one optical/SAR image
    BITEMPORAL = "bitemporal"    # two dates, same area
    CROSSMODAL = "crossmodal"    # co-registered optical + SAR
    AUTO = "auto"                # controller decides


class TaskType(str, Enum):
    SINGLE_VQA = "single_vqa"
    SINGLE_VQA_COUNT = "single_vqa_count"
    SINGLE_CAPTION = "single_caption"
    SINGLE_GROUND = "single_ground"
    BI_CHANGE = "bi_change"
    BI_CHANGE_VQA = "bi_change_vqa"
    CROSS_MODAL = "cross_modal"
    COMPOUND = "compound"


class Modality(str, Enum):
    OPTICAL = "optical"
    SAR = "sar"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ImageInput(BaseModel):
    """One input image. `data` is base64 (raw or data-URI prefixed)."""
    data: str = Field(description="Base64-encoded image bytes")
    name: Optional[str] = Field(None, description="Original filename, if any")
    modality: Optional[str] = Field(
        None, description="Declared modality: optical | sar (auto-detected if omitted)")
    tag: Optional[str] = Field(
        None, description="Optional role hint, e.g. before / after / sar / optical")


class VLMQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000,
                       description="Natural-language query about the imagery")
    images: List[ImageInput] = Field(default_factory=list)
    mode: InputMode = InputMode.AUTO
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional context: lat, lon, dates, output_format, region hints")


class CaptionRequest(BaseModel):
    images: List[ImageInput]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GroundRequest(BaseModel):
    query: str
    images: List[ImageInput]
    output_format: str = Field("hbb", pattern="^(hbb|obb)$")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChangeRequest(BaseModel):
    query: str = Field(default="What changed between these two dates, and where?")
    images: List[ImageInput] = Field(description="Exactly two images: [before, after]")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SARFusionRequest(BaseModel):
    query: str
    images: List[ImageInput] = Field(description="Two images: [optical, sar]")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation models (PS: input compatibility checking)
# ---------------------------------------------------------------------------
class ValidationIssue(BaseModel):
    level: Severity
    code: str
    message: str
    image_index: Optional[int] = None


class ImageMeta(BaseModel):
    index: int
    name: Optional[str] = None
    format: str = "unknown"              # png | jpeg | tiff | geotiff | unknown
    width: int = 0
    height: int = 0
    num_bands: int = 0
    bit_depth: Optional[str] = None
    dtype: Optional[str] = None
    declared_modality: str = Modality.UNKNOWN.value
    detected_modality: str = Modality.UNKNOWN.value
    modality_reason: Optional[str] = None
    file_size_bytes: int = 0
    georeferenced: bool = False
    ground_sample_dist_m: Optional[float] = None
    crs_note: Optional[str] = None
    extra_geo: Optional[Dict[str, Any]] = None   # pixel_scale / tiepoint for GeoJSON


class ValidationReport(BaseModel):
    ok: bool = True
    accepted: bool = True
    issues: List[ValidationIssue] = Field(default_factory=list)
    images: List[ImageMeta] = Field(default_factory=list)
    pair_compatibility: Optional[str] = None     # note for 2-image modes
    raw_size_bytes: int = 0
    total_pixels: int = 0


# ---------------------------------------------------------------------------
# Tool / trace models (auditable execution summary)
# ---------------------------------------------------------------------------
class ToolOutput(BaseModel):
    tool_id: str
    text: Optional[str] = None
    bounding_boxes: Optional[List[Dict[str, Any]]] = None
    change_stats: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    confidence_source: str = "model_self_report"
    parameters_used: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = 0.0
    model: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class VisualEvidenceItem(BaseModel):
    kind: str                                    # annotated_boxes | change_map | side_by_side | input_view
    title: str
    image_base64: str
    mime_type: str = "image/png"
    description: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None


class ExecutionTrace(BaseModel):
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode_requested: str = InputMode.AUTO.value
    task_type: str = ""
    task_confidence: float = 0.0
    classification_reason: str = ""
    tools_selected: List[str] = Field(default_factory=list)
    tools_invoked: List[str] = Field(default_factory=list)
    tool_outputs: List[ToolOutput] = Field(default_factory=list)
    validation: Optional[ValidationReport] = None
    model: str = ""
    vlm_mode: str = ""
    timestamps: Dict[str, str] = Field(default_factory=dict)
    total_execution_time_ms: float = 0.0
    notes: List[str] = Field(default_factory=list)


class VLMResponse(BaseModel):
    query_id: str
    status: str = "ok"                           # ok | rejected | error
    response: str
    task_type: str = ""
    confidence: float = 0.0
    visual_evidence: List[VisualEvidenceItem] = Field(default_factory=list)
    geojson: Optional[Dict[str, Any]] = None
    validation: Optional[ValidationReport] = None
    trace: Optional[ExecutionTrace] = None
    report_url: Optional[str] = None
    execution_time_ms: float = 0.0


class VLMStatus(BaseModel):
    mode: str
    model: str
    available: bool
    model_detail: Optional[str] = None
    ps_id: str = "SIH26167"
    version: str = "2.0.0"
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    limits: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# History / samples
# ---------------------------------------------------------------------------
class QuerySummary(BaseModel):
    query_id: str
    query: str
    task_type: str
    confidence: float
    timestamp: str
    num_images: int
    status: str = "ok"
