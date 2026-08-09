"""
CHRONOVISOR CLI
Usage: chrono [--port PORT] [--host HOST] [--no-browser]
"""
import sys
import os
import argparse
import webbrowser
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="chrono",
        description="CHRONOVISOR - Temporal Archaeology Engine",
        epilog="Examples:\n  chrono                    # Start on default port 8500\n  chrono --port 3000        # Custom port\n  chrono --no-browser       # Don't auto-open browser\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--port", "-p", type=int, default=None, help="Port (default: 8500)")
    parser.add_argument("--host", "-H", type=str, default=None, help="Host (default: 0.0.0.0)")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--check", action="store_true", help="Check dependencies and exit")
    args = parser.parse_args()

    # Find project root (where .env and run.py live)
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Load .env
    env_file = project_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

    # Add backend to path
    sys.path.insert(0, str(project_root / "backend"))

    if args.check:
        _check_deps()
        return

    # Banner
    print()
    print("=" * 60)
    print("  CHRONOVISOR  -  Temporal Archaeology Engine")
    print("=" * 60)
    print()

    # Import and initialize
    try:
        from api.main import app, satellite, ai, gemini
    except ImportError as e:
        print(f"  ERROR: Failed to import modules: {e}")
        print(f"  Run: pip install -r requirements.txt")
        sys.exit(1)

    # Initialize engines
    print("  Initializing engines...")
    satellite.initialize()
    ai.load_models()
    gemini.initialize()
    print()

    # Get config
    host = args.host or os.getenv("CHRONOVISOR_HOST", "0.0.0.0")
    port = args.port or int(os.getenv("CHRONOVISOR_PORT", "8500"))
    url = f"http://localhost:{port}"

    print(f"  Dashboard:  {url}")
    print(f"  API Docs:   {url}/docs")
    print(f"  Health:     {url}/api/health")
    print()
    print("  Ctrl+C to stop")
    print("=" * 60)
    print()

    # Auto-open browser
    if not args.no_browser:
        time.sleep(1.5)
        webbrowser.open(url)

    # Run
    import uvicorn
    uvicorn.run(app, host=host, port=port)


def _check_deps():
    """Check if all required packages are installed."""
    required = [
        "fastapi", "uvicorn", "numpy", "scipy", "requests",
        "pydantic", "httpx",
    ]
    optional = [
        ("ee", "Google Earth Engine"),
        ("google.genai", "Google Gemini SDK"),
    ]

    print("  Checking dependencies...\n")
    ok = 0
    for pkg in required:
        name = pkg.split(".")[-1] if "." in pkg else pkg
        try:
            __import__(pkg)
            print(f"  OK   {name}")
            ok += 1
        except ImportError:
            print(f"  MISS {name}  ->  pip install {name}")

    print()
    for pkg, desc in optional:
        try:
            __import__(pkg)
            print(f"  OK   {pkg} ({desc})")
        except ImportError:
            print(f"  --   {pkg} ({desc}) [optional]")

    print(f"\n  {ok}/{len(required)} required packages installed.")
    if ok < len(required):
        print("  Run: pip install -r requirements.txt")
    else:
        print("  All good. Run: chrono")
