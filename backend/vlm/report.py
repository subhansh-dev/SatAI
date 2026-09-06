"""
SatAI — Report Generator
Self-contained, printable HTML reports (browser -> PDF via print) and raw
JSON exports for every query — PS deliverable: "downloadable reports".
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional

_CSS = """
:root{color-scheme:light}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#f4f6fa;
     color:#101623;padding:32px;max-width:1080px;margin:0 auto}
.head{display:flex;justify-content:space-between;align-items:flex-start;
      border-bottom:3px solid #0b1f4b;padding-bottom:16px;margin-bottom:24px}
.brand{font-size:26px;font-weight:800;color:#0b1f4b;letter-spacing:.5px}
.brand span{color:#e8590c}
.sub{color:#5a6478;font-size:13px;margin-top:4px}
.badge{background:#0b1f4b;color:#fff;border-radius:8px;padding:8px 14px;
       font-size:12px;text-align:right;line-height:1.5}
h2{font-size:15px;text-transform:uppercase;letter-spacing:1.2px;color:#0b1f4b;
   margin:26px 0 10px;border-left:4px solid #e8590c;padding-left:10px}
.card{background:#fff;border:1px solid #dfe4ee;border-radius:12px;padding:18px;
      margin-bottom:14px;box-shadow:0 1px 3px rgba(16,22,35,.06)}
.query{font-size:17px;font-weight:600}
.meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
.chip{background:#eef2fb;border:1px solid #cfd9f2;color:#27407b;border-radius:999px;
      padding:4px 12px;font-size:12px;font-weight:600}
.confbar{height:10px;background:#e6e9f2;border-radius:999px;overflow:hidden;margin-top:8px}
.confbar>div{height:100%;background:linear-gradient(90deg,#2f9e44,#94d82d)}
.confnum{font-size:13px;font-weight:700;color:#2b8a3e;margin-top:6px}
p.ans{white-space:pre-wrap;line-height:1.65;font-size:14.5px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #edf0f6;vertical-align:top}
th{color:#5a6478;font-size:11px;text-transform:uppercase;letter-spacing:.8px}
img{max-width:100%;border-radius:10px;border:1px solid #dfe4ee;margin:8px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.evc{background:#fff;border:1px solid #dfe4ee;border-radius:10px;overflow:hidden}
.evc .cap{padding:10px 12px;font-size:12px;color:#3d4658}
.issue{padding:8px 12px;border-radius:8px;font-size:13px;margin-bottom:6px}
.ok{background:#ebfbee;color:#2b8a3e;border:1px solid #b2f2bb}
.warn{background:#fff9db;color:#997a00;border:1px solid #ffe066}
.err{background:#fff5f5;color:#c92a2a;border:1px solid #ffc9c9}
.foot{margin-top:28px;color:#8a93a6;font-size:11.5px;line-height:1.6;
      border-top:1px solid #dfe4ee;padding-top:14px}
@media print{body{background:#fff;padding:12px}.card{box-shadow:none}}
"""


def render_html_report(response: Dict[str, Any]) -> str:
    """Full audit report: query, validation, classification, tools, evidence."""
    r = response
    trace = r.get("trace") or {}
    esc = html.escape

    # ---------- header ----------
    task = esc(str(r.get("task_type") or trace.get("task_type") or "—"))
    conf = float(r.get("confidence") or 0)
    conf_pct = f"{conf * 100:.0f}%"
    model = esc(str(trace.get("model") or "—"))
    vlm_mode = esc(str(trace.get("vlm_mode") or "—"))
    ts = esc(str((trace.get("timestamps") or {}).get("received", "—")))
    total_ms = trace.get("total_execution_time_ms") or r.get("execution_time_ms")

    html_parts: List[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>SatAI Analysis Report</title>",
        f"<style>{_CSS}</style></head><body>",
        "<div class='head'><div><div class='brand'>Sat<span>AI</span> · SatQuery AI</div>",
        "<div class='sub'>Agentic Vision-Language Assistant for Multimodal "
        "Remote Sensing — Analysis Report</div></div>",
        f"<div class='badge'>PS ID: SIH26167 · ISRO<br>Query ID: {esc(str(r.get('query_id','')))[:18]}…<br>"
        f"Status: {esc(str(r.get('status','ok')).upper())}</div></div>",

        "<h2>Query</h2><div class='card'><div class='query'>",
        esc(str(trace.get("query") or "")),
        "</div><div class='meta'>",
        f"<span class='chip'>Task: {task}</span>",
        f"<span class='chip'>Mode: {esc(str(trace.get('mode_requested','')))}</span>",
        f"<span class='chip'>Model: {model} ({vlm_mode})</span>",
        f"<span class='chip'>Executed: {ts}</span>",
        f"<span class='chip'>Duration: {total_ms} ms</span>",
        "</div>",
        "<div class='confbar'><div style='width:"
        f"{max(2.0, conf * 100):.0f}%'></div></div>",
        f"<div class='confnum'>Overall confidence: {conf_pct}</div></div>",

        "<h2>Answer</h2><div class='card'><p class='ans'>",
        esc(str(r.get("response") or "")),
        "</p></div>",
    ]

    # ---------- validation ----------
    val = trace.get("validation") or {}
    imgs = val.get("images") or []
    issues_html = ""
    for i in val.get("issues") or []:
        lvl = i.get("level", "info")
        cls = {"error": "err", "warning": "warn"}.get(lvl, "ok")
        issues_html += (f"<div class='issue {cls}'>"
                        f"<b>{esc(lvl.upper())} · {esc(str(i.get('code','')))}</b> — "
                        f"{esc(str(i.get('message','')))}</div>")
    img_rows = "".join(
        f"<tr><td>#{(im.get('index', 0)) + 1}</td>"
        f"<td>{esc(str(im.get('name') or 'untitled'))}</td>"
        f"<td>{esc(str(im.get('format','')))}</td>"
        f"<td>{im.get('width','?')}×{im.get('height','?')}</td>"
        f"<td>{im.get('num_bands','?')}</td>"
        f"<td>{esc(str(im.get('detected_modality','')))}</td>"
        f"<td>{'yes' if im.get('georeferenced') else 'no'}</td>"
        f"<td>{im.get('ground_sample_dist_m') or '—'}</td></tr>"
        for im in imgs)
    html_parts += [
        "<h2>Input Validation &amp; Compatibility</h2><div class='card'>",
        issues_html or "<div class='issue ok'>No issues — inputs accepted.</div>",
        ("<table><tr><th>#</th><th>File</th><th>Format</th><th>Size (px)</th>"
         "<th>Bands</th><th>Modality</th><th>GeoTIFF</th><th>GSD (m/px)</th></tr>"
         + img_rows + "</table>") if img_rows else "",
        f"<p style='margin-top:10px;font-size:12.5px;color:#5a6478'>Pair "
        f"compatibility: {esc(str(val.get('pair_compatibility') or '—'))}</p></div>",
    ]

    # ---------- classification + tools (auditable summary) ----------
    rows = ""
    for o in trace.get("tool_outputs") or []:
        params = ", ".join(f"{k}={esc(str(v))}"
                           for k, v in (o.get("parameters_used") or {}).items())
        rows += (f"<tr><td><b>{esc(str(o.get('tool_id','')))}</b></td>"
                 f"<td>{esc(str(o.get('model') or ''))}</td>"
                 f"<td>{esc(params or '—')}</td>"
                 f"<td>{float(o.get('confidence') or 0):.0%}"
                 f"<br><small>{esc(str(o.get('confidence_source','')))}</small></td>"
                 f"<td>{o.get('execution_time_ms', 0):.0f} ms</td>"
                 f"<td>{esc((o.get('text') or '')[:220])}</td></tr>")
    html_parts += [
        "<h2>Agentic Execution Summary</h2><div class='card'>",
        f"<p style='font-size:13px;margin-bottom:10px'>Classification: "
        f"<b>{task}</b> — {esc(str(trace.get('classification_reason','')))} "
        f"(router confidence {float(trace.get('task_confidence') or 0):.0%})<br>"
        f"Tools selected: <b>{esc(', '.join(trace.get('tools_selected') or []) or '—')}</b> "
        f"· invoked: <b>{esc(', '.join(trace.get('tools_invoked') or []) or '—')}</b></p>",
        f"<table><tr><th>Tool</th><th>Model</th><th>Parameters used</th>"
        f"<th>Confidence</th><th>Time</th><th>Output (excerpt)</th></tr>{rows}</table>",
    ]
    if trace.get("notes"):
        html_parts.append("<p style='margin-top:10px;font-size:12.5px;color:#5a6478'>"
                          "Notes: " + esc(" · ".join(trace["notes"])) + "</p>")
    html_parts.append("</div>")

    # ---------- visual evidence ----------
    ev = r.get("visual_evidence") or []
    if ev:
        cards = "".join(
            f"<div class='evc'><img src='data:{esc(str(e.get('mime_type','image/png')))};"
            f"base64,{e.get('image_base64','')}'>"
            f"<div class='cap'><b>{esc(str(e.get('title','')))}</b><br>"
            f"{esc(str(e.get('description') or ''))}</div></div>"
            for e in ev)
        html_parts.append(f"<h2>Visual Evidence</h2><div class='grid'>{cards}</div>")

    # ---------- geojson ----------
    gj = r.get("geojson")
    if gj and gj.get("features"):
        gj_text = json.dumps(gj, indent=2)[:4000]
        html_parts += [
            "<h2>Localisation Export (GeoJSON)</h2><div class='card'>",
            f"<p style='font-size:12px;color:#5a6478'>CRS: {esc(str(gj.get('crs','')))}</p>",
            f"<pre style='font-size:11px;overflow:auto;background:#f6f8fc;"
            f"padding:12px;border-radius:8px'>{esc(gj_text)}</pre></div>",
        ]

    html_parts += [
        "<div class='foot'>Generated by <b>SatAI — SatQuery AI</b> for Smart India "
        "Hackathon 2026, Problem Statement SIH26167 (ISRO, Department of Space): "
        "“An Interactive Vision-Language Assistant for Multimodal Remote Sensing "
        "Image Analysis through Text Queries”. This report is an auditable "
        "execution summary: task classification, specialist tools, configured "
        "parameters, per-tool confidence and timing are recorded above. Internal "
        "model reasoning is neither required nor included (per the PS evaluation "
        "protocol). Confidence values are model self-estimates or parsing-derived "
        "scores; the spatial change map is a heuristic estimate produced without "
        "reference masks.</div>",
        "</body></html>",
    ]
    return "".join(html_parts)


def render_json_report(response: Dict[str, Any]) -> Dict[str, Any]:
    """Machine-readable audit export (trace + answer + evidence metadata)."""
    out = dict(response)
    out["exported_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ")
    return out
