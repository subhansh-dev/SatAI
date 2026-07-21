#!/usr/bin/env python3
"""
CHRONOVISOR — Entry Point
Run: python run.py
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Load .env BEFORE importing anything that reads env vars
from core.config import API_HOST, API_PORT

from api.main import app, satellite, ai, gemini

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  CHRONOVISOR — Temporal Archaeology Engine")
    print("=" * 60)
    print()

    # Initialize engines
    satellite.initialize()
    ai.load_models()
    gemini.initialize()

    print()
    print("  Dashboard: http://localhost:8500")
    print("  API Docs:  http://localhost:8500/docs")
    print()
    print("=" * 60)

    uvicorn.run(app, host=API_HOST, port=API_PORT)
