"""
SatAI — PDF Report Generator (reportlab)
Renders the auditable analysis report as a true PDF artifact — the same
content as the HTML report (query, validation, agentic execution summary,
confidence, visual evidence, GeoJSON summary, integrity digest), so analysts
can file the report without a browser-print step.

Dependency: reportlab (declared in requirements.txt). The route degrades
gracefully with a 501 + explanation if the package is absent.
"""
from __future__ import annotations

import html as _html
import io
import json
from typing import Any, Dict, List, Optional

_REPORT_STYLES = None          # lazy-built stylesheet cache


def _esc(s: Any) -> str:
    return _html.escape(str(s if s is not None else ""))


def render_pdf_report(response: Dict[str, Any]) -> bytes:
    """Build the PDF; raises ImportError when reportlab is missing."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (Image as RLImage, KeepTogether,
                                        PageBreak, Paragraph, SimpleDocTemplate,
                                        Spacer, Table, TableStyle)
    except ImportError as e:                     # pragma: no cover
        raise ImportError("reportlab is required for PDF export") from e

    r = response
    trace = r.get("trace") or {}
    navy = colors.HexColor("#0b1f4b")
    saffron = colors.HexColor("#e8590c")
    dim = colors.HexColor("#5a6478")
    line = colors.HexColor("#dfe4ee")

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], fontSize=18,
                        textColor=navy, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=8.5,
                         textColor=dim, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontSize=10.5,
                        textColor=navy, spaceBefore=12, spaceAfter=4,
                        borderPadding=(0, 0, 0, 4))
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=13)
    small = ParagraphStyle("small", parent=base["Normal"], fontSize=7.5,
                           leading=10, textColor=dim)
    mono = ParagraphStyle("mono", parent=base["Normal"], fontName="Courier",
                          fontSize=7, leading=9, textColor=dim)

    def tbl(data: List[List[Any]], widths: Optional[List[float]] = None,
            font_size: float = 7.5) -> Table:
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2fb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), navy),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    story: List[Any] = []

    # ---------------- header ----------------
    conf = float(r.get("confidence") or 0)
    task = _esc(r.get("task_type") or trace.get("task_type") or "—")
    total_ms = trace.get("total_execution_time_ms") or r.get("execution_time_ms")
    story.append(Paragraph("SatAI · SatQuery AI — Analysis Report", h1))
    story.append(Paragraph(
        "Agentic Vision-Language Assistant for Multimodal Remote Sensing — "
        "PS SIH26167 · ISRO · Department of Space", sub))

    audit_hash = str(r.get("audit_hash") or "")
    if audit_hash:
        story.append(Paragraph(
            f"<b>Integrity digest (SHA-256)</b> — recompute over the canonical "
            f"JSON of this record (excluding audit_hash and feedback) to verify "
            f"it was not altered.", small))
        story.append(Paragraph(_esc(audit_hash), mono))
        story.append(Spacer(1, 6))

    # ---------------- query + confidence ----------------
    story.append(Paragraph("Query", h2))
    meta = [
        ["Query", Paragraph(_esc(trace.get("query") or "(not recorded)"), body)],
        ["Task", Paragraph(
            f"{task} · mode {_esc(trace.get('mode_requested'))} · "
            f"model {_esc(trace.get('model'))} ({_esc(trace.get('vlm_mode'))})<br/>"
            f"Executed {_esc((trace.get('timestamps') or {}).get('received', '—'))} "
            f"· duration {total_ms} ms · confidence <b>{conf:.0%}</b>", body)],
    ]
    story.append(tbl([[Paragraph(f"<b>{a}</b>", body), b] for a, b in meta],
                     widths=[28 * mm, None]))

    story.append(Paragraph("Answer", h2))
    story.append(Paragraph(_esc(r.get("response") or "(no content)")
                           .replace("\n", "<br/>"), body))

    # ---------------- validation ----------------
    val = trace.get("validation") or {}
    imgs = val.get("images") or []
    story.append(Paragraph("Input Validation &amp; Compatibility", h2))
    issue_rows = [["Level", "Code", "Message"]]
    for i in val.get("issues") or []:
        issue_rows.append([_esc(i.get("level")), _esc(i.get("code")),
                           _esc(i.get("message"))])
    if len(issue_rows) == 1:
        issue_rows.append(["ok", "—", "No issues — inputs accepted."])
    story.append(tbl(issue_rows, widths=[18 * mm, 40 * mm, None]))
    if imgs:
        img_rows = [["#", "File", "Format", "Size (px)", "Bands", "Modality",
                     "GeoTIFF", "GSD (m/px)"]]
        for im in imgs:
            img_rows.append([
                str((im.get("index", 0)) + 1),
                _esc(im.get("name") or "untitled"),
                _esc(im.get("format")),
                f"{im.get('width', '?')}x{im.get('height', '?')}",
                str(im.get("num_bands", "?")),
                _esc(im.get("detected_modality")),
                "yes" if im.get("georeferenced") else "no",
                str(im.get("ground_sample_dist_m") or "-"),
            ])
        story.append(Spacer(1, 4))
        story.append(tbl(img_rows))
    if val.get("pair_compatibility"):
        story.append(Paragraph(f"Pair compatibility: "
                               f"{_esc(val.get('pair_compatibility'))}", small))

    # ---------------- agentic execution summary ----------------
    story.append(Paragraph("Agentic Execution Summary", h2))
    story.append(Paragraph(
        f"Classification: <b>{task}</b> — "
        f"{_esc(trace.get('classification_reason'))} (router confidence "
        f"{float(trace.get('task_confidence') or 0):.0%})<br/>"
        f"Tools selected: <b>{_esc(', '.join(trace.get('tools_selected') or []) or '—')}</b> "
        f"· invoked: <b>{_esc(', '.join(trace.get('tools_invoked') or []) or '—')}</b>",
        body))
    out_rows = [["Tool", "Model", "Parameters", "Conf", "Time (ms)",
                 "Output (excerpt)"]]
    for o in trace.get("tool_outputs") or []:
        params = ", ".join(f"{k}={v}" for k, v in
                           (o.get("parameters_used") or {}).items())
        out_rows.append([
            _esc(o.get("tool_id")), _esc(o.get("model") or ""),
            _esc(params or "-"),
            f"{float(o.get('confidence') or 0):.0%} "
            f"({_esc(o.get('confidence_source'))})",
            f"{o.get('execution_time_ms', 0):.0f}",
            _esc((o.get("text") or "")[:200]),
        ])
    if len(out_rows) > 1:
        story.append(Spacer(1, 4))
        story.append(tbl(out_rows, widths=[22 * mm, 26 * mm, 28 * mm, 24 * mm,
                                           14 * mm, None]))
    if trace.get("notes"):
        story.append(Paragraph("Notes: " + _esc(" · ".join(trace["notes"])),
                               small))

    # ---------------- visual evidence (one per page section) ----------------
    ev = r.get("visual_evidence") or []
    if ev:
        story.append(Paragraph("Visual Evidence (chain of evidence)", h2))
        for idx, e in enumerate(ev, 1):
            stats = e.get("stats") or {}
            bits = []
            if stats.get("changed_pixels_pct") is not None:
                bits.append(f"{stats['changed_pixels_pct']}% pixels changed")
            if stats.get("verdict"):
                bits.append(str(stats["verdict"]))
            if stats.get("boxes"):
                bits.append(f"{len(stats['boxes'])} box(es)")
            cap = (f"<b>EV-{idx} · {_esc(e.get('title'))}</b> — "
                   f"{_esc(e.get('description') or '')}"
                   + (" · " + _esc(" · ".join(bits)) if bits else ""))
            img_b64 = e.get("image_base64")
            block: List[Any] = [Paragraph(cap, small)]
            if img_b64:
                try:
                    import base64
                    raw = base64.b64decode(img_b64)
                    rl_img = RLImage(io.BytesIO(raw))
                    ratio = rl_img.imageWidth / max(rl_img.imageHeight, 1)
                    max_w, max_h = 150 * mm, 80 * mm
                    w = min(max_w, max_h * ratio)
                    rl_img.drawWidth, rl_img.drawHeight = w, w / ratio
                    block.append(rl_img)
                except Exception:
                    pass
            story.append(KeepTogether(block))

    # ---------------- geojson summary ----------------
    gj = r.get("geojson")
    if gj and gj.get("features"):
        story.append(Paragraph("Localisation Export (GeoJSON)", h2))
        story.append(Paragraph(f"CRS: {_esc(gj.get('crs'))}", small))
        feat_rows = [["#", "Label", "Confidence", "Geometry"]]
        for k, f in enumerate(gj.get("features", [])[:20], 1):
            p = f.get("properties") or {}
            geom = f.get("geometry") or {}
            feat_rows.append([
                str(k), _esc(p.get("label") or "-"),
                _esc(p.get("confidence") if p.get("confidence") is not None
                     else "-"),
                _esc(geom.get("type") or "-"),
            ])
        story.append(tbl(feat_rows, widths=[10 * mm, 60 * mm, 25 * mm, None]))
        story.append(Paragraph(
            "Full machine-readable GeoJSON is included in the JSON export "
            "(report download, format=json).", small))

    # ---------------- analyst feedback ----------------
    fb = r.get("feedback") or []
    if fb:
        story.append(Paragraph("Analyst Review (Human-in-the-Loop)", h2))
        fb_rows = [["Verdict", "Note", "Recorded"]]
        for f in fb:
            fb_rows.append(["up" if f.get("rating") == "up" else "down",
                            _esc(f.get("comment") or "-"),
                            _esc(f.get("timestamp") or "")])
        story.append(tbl(fb_rows))
        story.append(Paragraph(
            "Feedback is recorded after the answer is frozen and never alters "
            "the integrity digest.", small))

    # ---------------- footer ----------------
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Generated by SatAI — SatQuery AI for Smart India Hackathon 2026, "
        "PS SIH26167 (ISRO): \u201cAn Interactive Vision-Language Assistant for "
        "Multimodal Remote Sensing Image Analysis through Text Queries\u201d. "
        "This report is an auditable execution summary; confidence values are "
        "model self-estimates or parsing-derived scores, and the spatial change "
        "map is a heuristic estimate produced without reference masks.", small))

    buf = io.BytesIO()

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(dim)
        canvas.drawString(18 * mm, 12 * mm,
                          f"SatAI · PS SIH26167 · query "
                          f"{str(r.get('query_id', ''))[:18]}")
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm,
                               f"Page {doc.page}")
        canvas.setStrokeColor(line)
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm,
                            rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=20 * mm, title="SatAI Analysis Report",
                            author="SatAI — SatQuery AI (SIH26167)")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
