"""
SatAI — VLM Client
Cloud <-> Local flip for vision-language model inference.
Set VLM_MODE=cloud for dev (this laptop), VLM_MODE=local for ISRO finals.
"""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger("satai.vlm")


class VLMClient:
    def __init__(self):
        self.mode = os.getenv("VLM_MODE", "cloud")
        self.local_url = os.getenv("VLM_LOCAL_URL", "http://localhost:8000/v1")
        self.cloud_url = os.getenv("CLOUD_BASE_URL", "https://openrouter.ai/api/v1")
        self.cloud_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.cloud_model = os.getenv("CLOUD_MODEL", "qwen/qwen-2.5-vl-72b-instruct")
        self.local_model = os.getenv("VLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
        self._http = httpx.AsyncClient(timeout=120)

    @property
    def active_model(self) -> str:
        return self.local_model if self.mode == "local" else self.cloud_model

    @property
    def active_url(self) -> str:
        return self.local_url if self.mode == "local" else self.cloud_url

    async def query(
        self,
        messages: list[dict],
        images: Optional[list[str]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> dict:
        """Send a query to the VLM (local vLLM or cloud API)."""
        payload = self._build_payload(messages, images, max_tokens, temperature)
        headers = self._build_headers()

        try:
            resp = await self._http.post(
                f"{self.active_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"VLM HTTP error {e.response.status_code}: {e.response.text[:500]}")
            return self._fallback_response(f"HTTP {e.response.status_code}")
        except httpx.ConnectError:
            logger.warning(f"Cannot connect to VLM at {self.active_url}")
            return self._fallback_response("VLM unavailable — check server")
        except Exception as e:
            logger.error(f"VLM query failed: {e}")
            return self._fallback_response(str(e))

    async def health_check(self) -> bool:
        """Check if the VLM server is reachable."""
        try:
            if self.mode == "local":
                resp = await self._http.get(f"{self.local_url}/models", timeout=5)
                return resp.status_code == 200
            else:
                resp = await self._http.get(
                    f"{self.cloud_url}/models",
                    headers=self._build_headers(),
                    timeout=10,
                )
                return resp.status_code == 200
        except Exception:
            return False

    def _build_payload(
        self, messages: list[dict], images: Optional[list[str]],
        max_tokens: int, temperature: float,
    ) -> dict:
        payload = {
            "model": self.active_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if images and self.mode == "local":
            payload["images"] = images
        elif images and self.mode == "cloud":
            payload["messages"] = self._inject_images_cloud(messages, images)
        return payload

    def _inject_images_cloud(self, messages: list[dict], images: list[str]) -> list[dict]:
        """Inject images into the last user message for cloud OpenAI-vision format."""
        out = [m.copy() for m in messages]
        content = []
        for img_b64 in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            })
        if out and out[-1]["role"] == "user":
            existing = out[-1].get("content", "")
            if isinstance(existing, str):
                content.append({"type": "text", "text": existing})
            out[-1]["content"] = content
        return out

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.mode == "cloud" and self.cloud_key:
            headers["Authorization"] = f"Bearer {self.cloud_key}"
        return headers

    def _fallback_response(self, reason: str) -> dict:
        return {
            "choices": [{
                "message": {
                    "content": f"[SatAI] VLM unavailable ({reason}). Using fallback mode."
                }
            }],
            "error": reason,
        }

    async def close(self):
        await self._http.aclose()
