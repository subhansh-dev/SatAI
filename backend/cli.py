"""
SatAI — SatQuery AI CLI

Usage:
    python -m backend.cli serve [--port 8500] [--no-browser]
    python -m backend.cli check

'check' verifies required + optional dependencies without starting the server.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def cmd_check() -> int:
    required = ["fastapi", "uvicorn", "httpx", "numpy", "PIL", "pydantic"]
    optional = [
        ("torch", "LoRA fine-tuning (scripts/train_lora.py)"),
        ("transformers", "HF model classes"),
        ("peft", "LoRA adapters"),
        ("rasterio", "GeoTIFF deep-probe (optional; tifffile used otherwise)"),
    ]
    ok = 0
    print("Required:")
    for pkg in required:
        try:
            __import__(pkg)
            print(f"  OK   {pkg}")
            ok += 1
        except ImportError:
            print(f"  MISS {pkg}")
    print("Optional (training / geo deep-probe):")
    for pkg, why in optional:
        try:
            __import__(pkg)
            print(f"  OK   {pkg}  ({why})")
        except ImportError:
            print(f"  --   {pkg}  ({why})")
    print(f"\n{ok}/{len(required)} required packages installed.")
    if ok == len(required):
        print("All good — start with: python run.py")
    else:
        print("Run: pip install -r requirements.txt")
    return 0 if ok == len(required) else 1


def cmd_serve(port: int, host: str, open_browser: bool) -> None:
    sys.path.insert(0, str(REPO / "backend"))
    _load_env()

    print("=" * 62)
    print("  SatAI — SatQuery AI · Agentic RS Vision-Language Assistant")
    print("  PS SIH26167 · ISRO · Smart India Hackathon 2026")
    print("=" * 62)

    import uvicorn  # noqa: E402
    from core import config  # noqa: E402  (after sys.path bootstrap)

    host = host or os.getenv("SATAI_HOST", "0.0.0.0")
    port = port or int(os.getenv("SATAI_PORT", "8500"))
    url = f"http://{'localhost' if host in ('0.0.0.0', '') else host}:{port}"

    print(f"  App      : {url}")
    print(f"  API docs : {url}/docs")
    print(f"  Health   : {url}/api/health")
    print(f"  VLM mode : {config.VLM_MODE} ({config.VLM_MODEL if config.VLM_MODE == 'local' else config.CLOUD_MODEL})")
    print("  Ctrl+C to stop")
    print("=" * 62 + "\n")

    if open_browser:
        time.sleep(1.2)
        webbrowser.open(url)

    uvicorn.run("api.main:app", host=host, port=port, log_level="info")


def main() -> None:
    p = argparse.ArgumentParser(prog="satai", description="SatAI — SatQuery AI (SIH26167)")
    sub = p.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="start the API + frontend server")
    serve.add_argument("--port", "-p", type=int, default=None)
    serve.add_argument("--host", "-H", type=str, default=None)
    serve.add_argument("--no-browser", action="store_true")
    sub.add_parser("check", help="verify dependencies and exit")
    args = p.parse_args()

    if args.cmd == "check":
        sys.exit(cmd_check())
    if args.cmd == "serve":
        cmd_serve(args.port, args.host or "", not args.no_browser)
        return
    p.print_help()


if __name__ == "__main__":
    main()
