"""
SatAI — Render free-tier keep-alive.

Render free web services sleep after ~15 min without inbound traffic; the
first request afterwards eats a ~50 s cold boot (and judges see a 503).
Render injects RENDER_EXTERNAL_URL into the service environment, so the app
can simply ping its own /api/health on a timer to stay warm.

Enable with SATAI_KEEPALIVE=1 (set in render.yaml). Locally the variable is
unset and the thread exits immediately — zero overhead in development.
An explicit SATAI_KEEPALIVE_URL overrides the Render-injected URL (useful
for pinging a different host, e.g. the frontend's health probe target).
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request

logger = logging.getLogger("satai.keepalive")

PING_INTERVAL_SEC = int(os.getenv("SATAI_KEEPALIVE_INTERVAL_SEC", "600"))  # 10 min


def _ping(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "satai-keepalive/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:                       # never crash the app on a ping
        logger.debug("keepalive ping failed: %s", e)
        return False


def _loop(url: str) -> None:
    fails = 0
    while True:
        time.sleep(PING_INTERVAL_SEC)
        ok = _ping(f"{url}/api/health")
        if ok:
            fails = 0
            logger.debug("keepalive ping ok -> %s", url)
        else:
            fails += 1
            if fails == 3:
                logger.warning("keepalive: 3 consecutive ping failures — check the service")


def start_keepalive() -> None:
    """Start the daemon ping thread when running on Render (or told to)."""
    enabled = os.getenv("SATAI_KEEPALIVE", "") == "1"
    url = os.getenv("SATAI_KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
    if not enabled or not url:
        if enabled:
            logger.info("keepalive enabled but no URL — set SATAI_KEEPALIVE_URL "
                        "(Render injects RENDER_EXTERNAL_URL automatically)")
        return
    t = threading.Thread(target=_loop, args=(url.rstrip("/"),),
                         name="satai-keepalive", daemon=True)
    t.start()
    logger.info("keepalive started — pinging %s/api/health every %ss",
                url, PING_INTERVAL_SEC)
