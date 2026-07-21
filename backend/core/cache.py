"""
CHRONOVISOR — Cache Manager
In-memory + disk cache for API responses to avoid redundant external calls.
"""
import json
import hashlib
import time
import os
from pathlib import Path
from typing import Any, Optional
from functools import wraps


class CacheManager:
    """Two-tier cache: fast in-memory (TTL-based) + disk persistence."""

    def __init__(self, ttl: int = 3600, cache_dir: str = "data/.cache"):
        self.ttl = ttl
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, dict] = {}

    def _key(self, namespace: str, params: dict) -> str:
        raw = json.dumps(params, sort_keys=True, default=str)
        h = hashlib.sha256(f"{namespace}:{raw}".encode()).hexdigest()[:16]
        return h

    def get(self, namespace: str, params: dict) -> Optional[Any]:
        key = self._key(namespace, params)
        # Memory hit
        if key in self._memory:
            entry = self._memory[key]
            if time.time() - entry["ts"] < self.ttl:
                return entry["data"]
            del self._memory[key]
        # Disk hit
        disk_path = self.cache_dir / f"{key}.json"
        if disk_path.exists():
            try:
                data = json.loads(disk_path.read_text())
                if time.time() - data.get("ts", 0) < self.ttl:
                    self._memory[key] = data
                    return data["data"]
                disk_path.unlink()
            except Exception:
                pass
        return None

    def set(self, namespace: str, params: dict, data: Any):
        key = self._key(namespace, params)
        entry = {"ts": time.time(), "data": data}
        self._memory[key] = entry
        try:
            disk_path = self.cache_dir / f"{key}.json"
            disk_path.write_text(json.dumps(entry, default=str))
        except Exception:
            pass

    def invalidate(self, namespace: str = ""):
        if namespace:
            self._memory = {k: v for k, v in self._memory.items()
                          if not k.startswith(namespace)}
        else:
            self._memory.clear()

    def stats(self) -> dict:
        return {
            "memory_entries": len(self._memory),
            "disk_entries": len(list(self.cache_dir.glob("*.json"))),
            "ttl_seconds": self.ttl,
        }


# Global cache instance
cache = CacheManager(ttl=int(os.getenv("CACHE_TTL", "3600")))
