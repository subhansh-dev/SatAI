"""
SatAI — Transparency & auditability tests.

Covers the 2026-09 transparency batch:
- audit_hash: SHA-256 integrity digest stamped on every response (ok + rejected)
- digest verifiability: recomputable over the canonical JSON minus audit_hash/feedback
- trace.query round-trips inside the API-facing response model
- analyst feedback endpoint: records 👍/👎 + note, updates summary, 404 on unknown id
- feedback never mutates the machine answer or the audit digest
- HTML report carries the integrity digest, EV-indexed evidence and the review trail
"""
from __future__ import annotations

import base64
import hashlib
import io
import json

import pytest
from PIL import Image

from vlm.controller import Controller
from vlm.schemas import ImageInput


def make_png(w: int = 96, h: int = 96, color=(40, 90, 60)) -> str:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture()
def controller(monkeypatch):
    from tests.mock_vlm import MockVLM
    from vlm.tool_registry import registry
    from vlm.tools.caption_tool import CaptionTool
    from vlm.tools.change_tool import ChangeDescTool
    from vlm.tools.ground_tool import GroundTool
    from vlm.tools.numeric_tool import NumericTool
    from vlm.tools.sar_fusion_tool import SARFusionTool
    from vlm.tools.vqa_tool import VQATool

    ctrl = Controller()
    mock = MockVLM()
    monkeypatch.setattr(ctrl, "vlm", mock)
    registry.register(VQATool(mock))
    registry.register(NumericTool(mock))
    registry.register(CaptionTool(mock))
    registry.register(GroundTool(mock))
    registry.register(ChangeDescTool(mock))
    registry.register(SARFusionTool(mock))
    yield ctrl


@pytest.fixture()
def api_client(controller, monkeypatch):
    import httpx
    from api.main import app
    monkeypatch.setattr("vlm.controller._controller", controller)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ===========================================================================
# Integrity digest
# ===========================================================================
class TestAuditHash:
    async def test_ok_response_carries_digest(self, controller):
        resp = await controller.execute("Describe this image",
                                        [ImageInput(data=make_png())])
        assert resp.status == "ok"
        assert resp.audit_hash
        assert len(resp.audit_hash) == 64            # SHA-256 hex

    async def test_rejected_response_carries_digest(self, controller):
        resp = await controller.execute("Describe", [], mode="bitemporal")
        assert resp.status == "rejected"
        assert resp.audit_hash and len(resp.audit_hash) == 64

    async def test_digest_verifiable_from_report_json(self, controller):
        """Anyone can recompute the digest over the stored record."""
        resp = await controller.execute("Describe this image",
                                        [ImageInput(data=make_png())])
        stored = controller.store.get(resp.query_id)
        body = {k: v for k, v in stored.items()
                if k not in ("audit_hash", "feedback")}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                               default=str)
        recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert recomputed == stored["audit_hash"] == resp.audit_hash

    async def test_trace_query_round_trips(self, controller):
        q = "Describe this image in detail"
        resp = await controller.execute(q, [ImageInput(data=make_png())])
        assert resp.trace.query == q
        stored = controller.store.get(resp.query_id)
        assert stored["trace"]["query"] == q


# ===========================================================================
# Analyst feedback (human-in-the-loop)
# ===========================================================================
class TestFeedback:
    async def test_feedback_up_down_and_summary(self, controller, api_client):
        resp = await controller.execute("Describe this image",
                                        [ImageInput(data=make_png())])
        r = await api_client.post("/vlm/feedback", json={
            "query_id": resp.query_id, "rating": "up", "comment": "solid"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] and d["feedback_summary"] == {"up": 1, "down": 0}

        r2 = await api_client.post("/vlm/feedback", json={
            "query_id": resp.query_id, "rating": "down", "comment": "missed the dam"})
        d2 = r2.json()
        assert d2["feedback_summary"] == {"up": 1, "down": 1}

    async def test_feedback_unknown_query_404(self, api_client):
        r = await api_client.post("/vlm/feedback", json={
            "query_id": "no-such-id", "rating": "up"})
        assert r.status_code == 404

    async def test_feedback_invalid_rating_422(self, api_client):
        r = await api_client.post("/vlm/feedback", json={
            "query_id": "x", "rating": "meh"})
        assert r.status_code == 422

    async def test_feedback_never_mutates_answer_or_digest(self, controller,
                                                           api_client):
        resp = await controller.execute("Describe this image",
                                        [ImageInput(data=make_png())])
        stored = controller.store.get(resp.query_id)
        answer_before = stored["response"]
        digest_before = stored["audit_hash"]
        await api_client.post("/vlm/feedback", json={
            "query_id": resp.query_id, "rating": "down", "comment": "wrong"})
        stored_after = controller.store.get(resp.query_id)
        assert stored_after["response"] == answer_before
        assert stored_after["audit_hash"] == digest_before
        assert len(stored_after["feedback"]) == 1
        assert stored_after["feedback"][0]["comment"] == "wrong"


# ===========================================================================
# Reports expose the transparency layer
# ===========================================================================
class TestTransparencyReports:
    async def test_html_report_has_digest_and_ev_labels(self, controller):
        from vlm.report import render_html_report
        resp = await controller.execute("Describe this image",
                                        [ImageInput(data=make_png())])
        html = render_html_report(controller.store.get(resp.query_id))
        assert "INTEGRITY DIGEST" in html
        assert resp.audit_hash in html
        assert "EV-1" in html

    async def test_html_report_lists_feedback(self, controller, api_client):
        from vlm.report import render_html_report
        resp = await controller.execute("Describe this image",
                                        [ImageInput(data=make_png())])
        await api_client.post("/vlm/feedback", json={
            "query_id": resp.query_id, "rating": "down", "comment": "off by a river"})
        html = render_html_report(controller.store.get(resp.query_id))
        assert "Analyst Review" in html
        assert "off by a river" in html
