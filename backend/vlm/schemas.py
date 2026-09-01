"""
SatAI — VLM Schemas
Pydantic models for vision-language query/response structures.
"""
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Any
import uuid
import time


class InputMode(str, Enum):
    SINGLE = "single"
    BITEMPORAL = "bitemporal"
    CROSSMODAL = "crossmodal"
    AUTO = "auto"


class TaskType(str, Enum):
    SINGLE_VQA = "single_vqa"
    SINGLE_CAPTION = "single_caption"
    SINGLE_GROUND = "single_ground"
    BI_CHANGE = "bi_change"
    BI_CHANGE_VQA = "bi_change_vqa"
    CROSS_MODAL = "cross_modal"
    ENV_ANALYSIS = "env_analysis"
    COMPOUND = "compound"


class VLMQuery(BaseModel):
    query: str = Field(description="Natural language query about satellite imagery")
    images: list[str] = Field(default_factory=list, description="Base64-encoded images")
    mode: InputMode = Field(default=InputMode.AUTO, description="Input mode override")
    metadata: Optional[dict] = Field(default=None, description="Extra context (lat/lon, dates, etc.)")


class ToolOutput(BaseModel):
    tool_id: str
    text: Optional[str] = None
    bounding_boxes: Optional[list[dict]] = None
    change_mask: Optional[str] = None
    confidence: float = 0.0
    execution_time_ms: float = 0.0
    metadata: Optional[dict] = None


class ExecutionTrace(BaseModel):
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType
    tools_invoked: list[str] = Field(default_factory=list)
    tool_outputs: list[ToolOutput] = Field(default_factory=list)
    final_response: str = ""
    total_execution_time_ms: float = 0.0
    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


class VLMResponse(BaseModel):
    query_id: str
    response: str
    confidence: float = 0.0
    visual_evidence: Optional[dict] = None
    geojson: Optional[dict] = None
    trace: ExecutionTrace


class VLMStatus(BaseModel):
    mode: str
    model: str
    available: bool
    tools: list[dict] = Field(default_factory=list)


class CaptionRequest(BaseModel):
    images: list[str] = Field(description="Base64-encoded images")


class GroundRequest(BaseModel):
    query: str = Field(description="What to locate in the image")
    images: list[str] = Field(description="Base64-encoded images")
    output_format: str = Field(default="hbb", description="hbb or obb")


class ChangeRequest(BaseModel):
    query: str = Field(default="What changed between these two dates?")
    images: list[str] = Field(description="Two base64-encoded images [before, after]")


class SARFusionRequest(BaseModel):
    query: str = Field(description="What to analyze using both modalities")
    optical_image: str = Field(description="Base64-encoded optical image")
    sar_image: str = Field(description="Base64-encoded SAR image")
