"""SatAI test suite — sys.path bootstrap for `import vlm.*` / `import api.*`."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
