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

The daemon's live state is exposed via get_status() and surfaced on
/api/health so the ping loop can be verified from the outside — a silent
no-op (e.g. env var missing on a dashboard-created service) is exactly the
failure mode this exists to prevent.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request

logger = logging.getLogger("satai.keepalive")

PING_INTERVAL_SEC = int(os.getenv("SATAI_KEEPALIVE_INTERVAL_SEC", "600"))  # 10 min

_state: dict = {
    "active": False,          # daemon thread actually running?
    "url": "",                # where we ping
    "interval_sec": PING_INTERVAL_SEC,
    "last_attempt": None,     # epoch of last ping attempt (None = never)
    "last_ok": None,          # epoch of last successful ping (None = never)
    "consecutive_fails": 0,
    "last_result": "not started",
}
_lock = threading.Lock()


def _ping(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "satai-keepalive/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:   # covers cold-boot ~50 s
            ok = r.status == 200
    except Exception as e:                       # never crash the app on a ping
        ok = False
        logger.debug("keepalive ping failed: %s", e)
    with _lock:
        _state["last_attempt"] = time.time()
        if ok:
            _state["last_ok"] = _state["last_attempt"]
            _state["consecutive_fails"] = 0
            _state["last_result"] = "ok"
        else:
            _state["consecutive_fails"] = int(_state["consecutive_fails"]) + 1
            _state["last_result"] = f"fail x{_state['consecutive_fails']}"
    return ok


def _loop(url: str) -> None:
    fails = 0
    while True:
        ok = _ping(f"{url}/api/health")          # ping immediately on boot, too
        if ok:
            fails = 0
            logger.debug("keepalive ping ok -> %s", url)
        else:
            fails += 1
            if fails == 3:
                logger.warning("keepalive: 3 consecutive ping failures — check the service")
        time.sleep(PING_INTERVAL_SEC)


def start_keepalive() -> None:
    """Start the daemon ping thread when running on Render (or told to)."""
    enabled = os.getenv("SATAI_KEEPALIVE", "") == "1"
    url = os.getenv("SATAI_KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
    if not enabled or not url:
        with _lock:
            _state["active"] = False
            _state["last_result"] = (
                "disabled (SATAI_KEEPALIVE != 1)" if not enabled
                else "enabled but no URL — set SATAI_KEEPALIVE_URL")
        if enabled:
            logger.info("keepalive enabled but no URL — set SATAI_KEEPALIVE_URL "
                        "(Render injects RENDER_EXTERNAL_URL automatically)")
        return
    t = threading.Thread(target=_loop, args=(url.rstrip("/"),),
                         name="satai-keepalive", daemon=True)
    t.start()
    with _lock:
        _state["active"] = True
        _state["url"] = url.rstrip("/")
    logger.info("keepalive started — pinging %s/api/health every %ss",
                url, PING_INTERVAL_SEC)


def get_status() -> dict:
    """JSON-safe snapshot of the daemon state for /api/health."""
    with _lock:
        snap = dict(_state)
    la, lo = snap.get("last_attempt"), snap.get("last_ok")
    snap["last_attempt"] = round(la, 1) if isinstance(la, float) else la
    snap["last_ok"] = round(lo, 1) if isinstance(lo, float) else lo
    snap["seconds_since_ok"] = (round(time.time() - lo, 1)
                                if isinstance(lo, float) else None)
    return snap
