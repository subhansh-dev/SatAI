import asyncio
from backend.vlm.controller import Controller

async def test():
    c = Controller()
    
    # Test task classification (rule-based since VLM is down)
    task = c._fallback_classify(1, "single")
    print(f"Single image task: {task}")
    
    task = c._fallback_classify(2, "bitemporal")
    print(f"Bi-temporal task: {task}")
    
    task = c._fallback_classify(2, "crossmodal")
    print(f"Cross-modal task: {task}")
    
    # Test tool registry selection
    from backend.vlm.tool_registry import registry
    for task_type in ["single_vqa", "single_caption", "single_ground", "bi_change", "cross_modal", "env_analysis"]:
        tools = registry.select(task_type)
        print(f"  {task_type} -> {tools}")
    
    # Test full execute with a dummy image (will use VLM fallback)
    print("\nTesting full pipeline with fallback VLM...")
    result = await c.execute(
        query="Describe the land cover",
        images=["dGVzdA=="],  # dummy base64
        mode="single",
    )
    print(f"Result response: {result.response[:100]}")
    print(f"Result confidence: {result.confidence}")
    print(f"Trace task: {result.trace.task_type}")
    print(f"Trace tools: {result.trace.tools_invoked}")
    print(f"Trace time: {result.trace.total_execution_time_ms}ms")

asyncio.run(test())
