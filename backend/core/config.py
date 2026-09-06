"""
SatAI — SatQuery AI · Core Configuration
SIH26167 — ISRO | Agentic Vision-Language Assistant for Remote Sensing
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# .env bootstrap (before python-dotenv is even needed)
# ---------------------------------------------------------------------------
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent                                  # SatAI/
DATA_DIR = Path(os.getenv("SATAI_DATA_DIR", REPO_DIR / "data"))
SAMPLES_DIR = REPO_DIR / "samples"
QUERIES_DIR = DATA_DIR / "queries"                          # persisted query results
for _d in (DATA_DIR, QUERIES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# API server
# ---------------------------------------------------------------------------
API_HOST = os.getenv("SATAI_HOST", "0.0.0.0")
API_PORT = int(os.getenv("SATAI_PORT", "8500"))
APP_VERSION = "2.0.0"
PS_ID = "SIH26167"

# Rate limiting (per IP)
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))

# ---------------------------------------------------------------------------
# Input validation limits (PS: "check input images — number, modality, format,
# metadata, compatibility")
# ---------------------------------------------------------------------------
MAX_IMAGES_PER_QUERY = 4
MAX_IMAGE_BYTES = 20 * 1024 * 1024            # 20 MB per image
MAX_TOTAL_PAYLOAD_BYTES = 64 * 1024 * 1024    # 64 MB total request payload
MIN_IMAGE_DIM = 32                            # px — reject tiny/corrupt
MAX_IMAGE_DIM = 20000                         # px — warn on gigantic rasters

# VLM input preparation: big rasters are downscaled so the VLM sees a clean,
# token-efficient view. 1344 px matches Qwen2.5-VL's native long-side budget.
VLM_MAX_SIDE = int(os.getenv("VLM_MAX_SIDE", "1344"))
EVIDENCE_MAX_SIDE = 1024                      # annotated evidence render size
THUMB_MAX_SIDE = 512

# ---------------------------------------------------------------------------
# VLM backends — cloud (OpenRouter, dev) <-> local vLLM (ISRO finals / air-gap)
# ---------------------------------------------------------------------------
VLM_MODE = os.getenv("VLM_MODE", "cloud").lower()             # cloud | local

# Cloud (OpenAI-compatible; OpenRouter by default)
CLOUD_BASE_URL = os.getenv("CLOUD_BASE_URL", "https://openrouter.ai/api/v1")
CLOUD_MODEL = os.getenv("CLOUD_MODEL", "qwen/qwen-2.5-vl-72b-instruct")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Local (vLLM OpenAI-compatible server; see vllm_config.yaml)
VLM_LOCAL_URL = os.getenv("VLM_LOCAL_URL", "http://localhost:8000/v1")
VLM_MODEL = os.getenv("VLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
# Optional LoRA adapter path served by vLLM --lora-modules (RS-adapted weights)
VLM_LORA_ADAPTER = os.getenv("VLM_LORA_ADAPTER", "satai-rs")

# Inference defaults
VLM_TIMEOUT_SEC = float(os.getenv("VLM_TIMEOUT_SEC", "180"))
VLM_MAX_TOKENS = int(os.getenv("VLM_MAX_TOKENS", "1024"))
VLM_TEMPERATURE = float(os.getenv("VLM_TEMPERATURE", "0.1"))
VLM_MAX_RETRIES = int(os.getenv("VLM_MAX_RETRIES", "2"))
VLM_HEALTH_TTL_SEC = float(os.getenv("VLM_HEALTH_TTL_SEC", "30"))

# Self-consistency sampling for quantitative answers (calibrated confidence):
# n completions per counting query; modal answer + agreement bonus.
SELF_CONSISTENCY_SAMPLES = int(os.getenv("SELF_CONSISTENCY_SAMPLES", "3"))

# ---------------------------------------------------------------------------
# Query store (auditable execution summaries + downloadable reports)
# ---------------------------------------------------------------------------
QUERY_STORE_SIZE = int(os.getenv("QUERY_STORE_SIZE", "50"))

# ---------------------------------------------------------------------------
# Change-mask estimation (heuristic spatial change map; reference masks from
# the eval set are used by backend/vlm/eval/*)
# ---------------------------------------------------------------------------
CHANGE_DIFF_BLUR = int(os.getenv("CHANGE_DIFF_BLUR", "3"))
CHANGE_DIFF_K = float(os.getenv("CHANGE_DIFF_K", "2.5"))      # threshold = mean + k*std
CHANGE_MIN_REGION_PCT = float(os.getenv("CHANGE_MIN_REGION_PCT", "0.05"))
