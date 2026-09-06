"""
SatAI — VLM Client (cloud <-> local flip)

Cloud : OpenRouter (or any OpenAI-compatible endpoint) — development mode.
Local : vLLM OpenAI-compatible server (see vllm_config.yaml) — ISRO finals /
        air-gapped deployment, running the RS-adapted Qwen2.5-VL weights.

Both paths use the *same* OpenAI vision wire format: images travel as
`image_url` content parts inside the user message (this is what vLLM's
OpenAI server expects — the old code stuffed images in a top-level field
where vLLM silently ignored them).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from core import config

logger = logging.getLogger("satai.vlm")


class VLMError(Exception):
    """Raised when the VLM backend cannot produce a usable completion."""


class VLMClient:
    def __init__(self) -> None:
        self.mode = config.VLM_MODE if config.VLM_MODE in ("cloud", "local") else "cloud"
        self.local_url = config.VLM_LOCAL_URL.rstrip("/")
        self.cloud_url = config.CLOUD_BASE_URL.rstrip("/")
        self.cloud_key = config.OPENROUTER_API_KEY
        self.cloud_model = config.CLOUD_MODEL
        self.local_model = config.VLM_MODEL
        self.lora_adapter = config.VLM_LORA_ADAPTER
        self.timeout = config.VLM_TIMEOUT_SEC
        self._http = httpx.AsyncClient(timeout=self.timeout, limits=httpx.Limits(
            max_connections=8, max_keepalive_connections=4))
        self._health_cache: tuple[bool, float] = (False, 0.0)
        self._served_models: Optional[List[str]] = None
        self._model_resolved = False
        self.last_latency_ms: Optional[float] = None
        self.last_usage: Optional[Dict[str, Any]] = None
        self.request_count = 0

    # ------------------------------------------------------------------ info
    @property
    def active_model(self) -> str:
        return self.local_model if self.mode == "local" else self.cloud_model

    @property
    def active_url(self) -> str:
        return self.local_url if self.mode == "local" else self.cloud_url

    @property
    def configured(self) -> bool:
        if self.mode == "local":
            return bool(self.local_url)
        return bool(self.cloud_key)

    # ------------------------------------------------------------------ main
    async def query(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_json: bool = False,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Chat completion with optional image attachments.
        `images` = list of base64 JPEG/PNG (no data: prefix) prepared for the VLM.
        `model`  = optional per-call override (model registry routing).
        Raises VLMError after retries — callers decide the fallback story.
        """
        payload: Dict[str, Any] = {
            "model": model or self.active_model,
            "messages": self._inject_images(messages, images or []),
            "max_tokens": max_tokens or config.VLM_MAX_TOKENS,
            "temperature": config.VLM_TEMPERATURE if temperature is None else temperature,
        }
        if self.mode == "local":
            await self._resolve_local_model(payload)
        elif payload["model"] in ("lora", "base", "flagship"):
            # cloud mode has one flagship — registry hints resolve to it
            payload["model"] = self.cloud_model
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.mode == "cloud":
            if not self.cloud_key:
                raise VLMError("No OPENROUTER_API_KEY configured (cloud mode)")
            headers["Authorization"] = f"Bearer {self.cloud_key}"
            headers.setdefault("HTTP-Referer", "https://satai.local")
            headers.setdefault("X-Title", "SatAI SatQuery AI")

        last_err: Optional[str] = None
        for attempt in range(config.VLM_MAX_RETRIES + 1):
            t0 = time.time()
            try:
                self.request_count += 1
                resp = await self._http.post(
                    f"{self.active_url}/chat/completions",
                    json=payload, headers=headers)
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    if attempt < config.VLM_MAX_RETRIES:
                        await asyncio.sleep(self._retry_delay(attempt, resp))
                        continue
                    break
                resp.raise_for_status()
                data = resp.json()
                self.last_latency_ms = (time.time() - t0) * 1000
                self.last_usage = data.get("usage")
                return data
            except httpx.HTTPStatusError as e:
                raise VLMError(f"VLM HTTP {e.response.status_code}: "
                               f"{e.response.text[:300]}") from e
            except (httpx.ConnectError, httpx.ConnectTimeout,
                    httpx.ReadTimeout) as e:
                # ConnectTimeout previously fell into the generic branch and
                # was never retried — a cold vLLM server boot killed queries.
                last_err = f"connection: {type(e).__name__}"
                if attempt < config.VLM_MAX_RETRIES:
                    await asyncio.sleep(self._retry_delay(attempt, None))
                    continue
                break
            except httpx.HTTPError as e:
                raise VLMError(f"VLM transport error: {e}") from e
        raise VLMError(f"VLM unavailable after retries ({last_err})")

    @staticmethod
    def _retry_delay(attempt: int, resp: Optional[httpx.Response]) -> float:
        """Respect Retry-After when present; exponential backoff + jitter."""
        if resp is not None:
            ra = resp.headers.get("retry-after")
            if ra:
                try:
                    return min(30.0, float(ra))
                except ValueError:
                    pass
        import random
        return min(20.0, 1.5 * (2 ** attempt) + random.uniform(0, 0.5))

    # ------------------------------------------------------------------ local
    async def _resolve_local_model(self, payload: Dict[str, Any]) -> None:
        """
        Local-mode model name resolution (fixes the deployment bug where the
        client requested a model name the vLLM server didn't serve and every
        call 404'd). Registry hints (lora | base | flagship) resolve against
        the served-model list with graceful fallback:
        1. probe GET /models once
        2. 'lora'  -> LoRA adapter when actually served, else base, else first
        3. 'base'  -> configured base weights when served, else first served
        4. concrete names must be served, else fall back with a warning
        """
        asked = payload.get("model")
        if self._model_resolved and asked not in ("lora", "base", "flagship"):
            return
        served = await self._list_served_models()
        if served:
            self._served_models = served
        else:
            served = self._served_models or []
        self._model_resolved = True

        if asked == "lora":
            for cand in (self.lora_adapter, self.local_model,
                         *(served or [])):
                if cand and cand in served:
                    payload["model"] = cand
                    return
            if served:
                payload["model"] = served[0]
            return
        if asked in ("base", "flagship"):
            for cand in (self.local_model, *(served or [])):
                if cand and cand in served:
                    payload["model"] = cand
                    return
            if served:
                payload["model"] = served[0]
            return
        # concrete model name — verify when possible
        if asked and served and asked not in served:
            logger.warning("local VLM: requested %r but server serves %s — "
                           "using %r", asked, served, served[0])
            payload["model"] = served[0]

    async def _list_served_models(self) -> Optional[List[str]]:
        try:
            resp = await self._http.get(f"{self.local_url}/models", timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            ids = [d.get("id") for d in data.get("data", []) if d.get("id")]
            return ids or None
        except Exception:
            return None

    # ------------------------------------------------------------------ health
    async def health_check(self, force: bool = False) -> bool:
        now = time.time()
        ok, at = self._health_cache
        if not force and (now - at) < config.VLM_HEALTH_TTL_SEC:
            return ok
        ok = await self._health_probe()
        self._health_cache = (ok, now)
        return ok

    async def _health_probe(self) -> bool:
        try:
            headers = {}
            if self.mode == "cloud":
                if not self.cloud_key:
                    return False
                headers["Authorization"] = f"Bearer {self.cloud_key}"
            resp = await self._http.get(f"{self.active_url}/models",
                                        headers=headers, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------ wire
    def _inject_images(self, messages: List[Dict[str, Any]],
                       images: List[str]) -> List[Dict[str, Any]]:
        """OpenAI vision format for BOTH cloud and local (vLLM) backends."""
        if not images:
            return messages
        out = [dict(m) for m in messages]
        # find last user message
        idx = next((i for i in range(len(out) - 1, -1, -1)
                    if out[i].get("role") == "user"), None)
        if idx is None:
            idx = len(out) - 1
            out.append({"role": "user", "content": ""})
        text = out[idx].get("content", "")
        if isinstance(text, list):  # already multimodal — append raw images
            content = list(text) + [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                for b64 in images]
        else:
            # images first, then the instruction text (standard vision ordering)
            content = [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                for b64 in images]
            content.append({"type": "text", "text": str(text)})
        out[idx]["content"] = content
        return out

    async def close(self) -> None:
        await self._http.aclose()
