import asyncio
from backend.vlm.vlm_client import VLMClient

async def test():
    c = VLMClient()
    health = await c.health_check()
    print(f"Health check: {health}")
    
    resp = await c.query(
        messages=[{"role": "user", "content": "Say hello in 5 words"}],
        max_tokens=50,
    )
    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "FAILED")
    print(f"VLM response: {content[:200]}")
    err = resp.get("error")
    if err:
        print(f"Error: {err}")

asyncio.run(test())
