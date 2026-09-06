"""
SatAI — SatQuery AI · Launcher
python run.py   →  http://localhost:8500
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402

from core import config  # noqa: E402

BANNER = r"""
   ___    _____  _____  ___
  / _ |  / ___/ / ___/ / _ \    SatQuery AI — Agentic Vision-Language
 / __ | _\ \   / /__  / // /    Assistant for Multimodal Remote Sensing
/_/ |_|/___/  \___/ /____/      PS SIH26167 · ISRO · SpaceTech

  VLM mode  : {mode}
  Model     : {model}
  URL       : http://{host}:{port}   (docs at /docs)
"""

if __name__ == "__main__":
    print(BANNER.format(
        mode=config.VLM_MODE,
        model=config.VLM_MODEL if config.VLM_MODE == "local" else config.CLOUD_MODEL,
        host=config.API_HOST, port=config.API_PORT))

    if config.VLM_MODE == "cloud" and not config.OPENROUTER_API_KEY:
        print("  ⚠  VLM_MODE=cloud but OPENROUTER_API_KEY is not set.")
        print("     Copy .env.example → .env and add your key (cloud dev mode),")
        print("     or set VLM_MODE=local with a running vLLM server.\n")

    uvicorn.run(
        "api.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        log_level="info",
    )
