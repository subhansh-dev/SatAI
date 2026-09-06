/**
 * SatAI — SatQuery AI frontend (PS SIH26167)
 * Vanilla JS · no frameworks · offline-capable
 *
 * Talks to the agentic backend:
 *   GET  /vlm/status            backend + registry info
 *   POST /vlm/upload            image -> base64 + modality/format probe
 *   POST /vlm/query             full agentic pipeline
 *   POST /vlm/feedback          analyst review (👍/👎 + note) -> audit record
 *   GET  /vlm/history           recent queries (in-memory store)
 *   GET  /vlm/report/:id?format=json|html   auditable report
 *   GET  /vlm/report/:id/download           attachment
 *
 * Optional API base override for split deployments:
 *   ?api=https://host  or  localStorage.satai_api
 */
'use strict';

/* ------------------------------------------------------------------ state */
const API = (() => {
  const fromQuery = new URLSearchParams(location.search).get('api');
  return (fromQuery || localStorage.getItem('satai_api') || '').replace(/\/$/, '');
})();

const state = {
  images: [],          // {b64, name, modality, format, width, height, size}
  mode: 'auto',
  busy: false,
  responses: new Map() // query_id -> full response JSON (this session)
};

const $ = id => document.getElementById(id);
const chat = $('chat');

/* ------------------------------------------------------------------ boot */
document.addEventListener('DOMContentLoaded', () => {
  attachUploadHandlers();
  attachComposerHandlers();
  attachChromeHandlers();
  attachThemeToggle();
  attachEvidenceNavigation();
  refreshStatus();
  refreshHistory();
  setInterval(refreshStatus, 60000);
});

/* ================================================================ STATUS */
async function refreshStatus() {
  const dot = $('statusDot'), txt = $('statusText');
  try {
    const r = await fetch(`${API}/vlm/status`);
    const d = await r.json();
    const model = (d.model || '').split('/').pop();
    txt.textContent = `${d.available ? 'online' : 'no key'} · ${d.mode} · ${model}`;
    dot.className = 'status-dot ' + (d.available ? 'online' : 'offline');
    $('sideVersion').textContent = d.version ? `v${d.version} · ${d.ps_id}` : 'v2.0';
    renderTools(d.tools || []);
  } catch {
    txt.textContent = 'backend unreachable';
    dot.className = 'status-dot offline';
  }
}

function renderTools(tools) {
  const el = $('toolsList');
  el.innerHTML = tools.length
    ? tools.map(t => `<span class="tool-chip" title="${esc(t.description || t.ps_requirement || '')}">${esc(t.id || t.tool_id)}</span>`).join('')
    : '<span class="dim pad8">registry unavailable</span>';
}

/* ================================================================ UPLOAD */
const MAX_IMAGES = 4;
const MAX_MB = 20;

function attachUploadHandlers() {
  $('attachBtn').addEventListener('click', () => $('fileInput').click());
  $('fileInput').addEventListener('change', e => {
    addFiles([...e.target.files]);
    e.target.value = '';
  });

  let dragDepth = 0;
  document.addEventListener('dragenter', e => { e.preventDefault(); if (++dragDepth === 1) document.body.classList.add('dragging'); });
  document.addEventListener('dragleave', e => { e.preventDefault(); if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove('dragging'); } });
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => {
    e.preventDefault();
    dragDepth = 0; document.body.classList.remove('dragging');
    if (e.dataTransfer?.files?.length) addFiles([...e.dataTransfer.files]);
  });

  // paste images straight into the composer
  document.addEventListener('paste', e => {
    const files = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith('image/') || /\.(tiff?|png|jpe?g)$/i.test(f.name));
    if (files.length) addFiles(files);
  });
}

async function addFiles(files) {
  for (const f of files) {
    if (state.images.length >= MAX_IMAGES) { toast(`Limit is ${MAX_IMAGES} images per query`); break; }
    if (f.size > MAX_MB * 1024 * 1024) { toast(`${f.name} exceeds ${MAX_MB} MB`); continue; }
    try {
      // server-side probe: format sniffing, modality detection, dimensions
      const fd = new FormData();
      fd.append('file', f);
      const r = await fetch(`${API}/vlm/upload`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
      const meta = await r.json();
      state.images.push(meta);
      renderPreview();
    } catch (err) {
      toast(`Could not read ${f.name}: ${err.message}`);
    }
  }
}

function renderPreview() {
  const strip = $('previewStrip');
  strip.hidden = state.images.length === 0;
  strip.innerHTML = state.images.map((im, i) => {
    const role = state.images.length === 2
      ? (i === 0 ? 'BEFORE / OPTICAL' : 'AFTER / SAR')
      : (im.detected_modality || 'image').toUpperCase();
    return `
      <div class="pv-item" title="${esc(im.filename || '')} — ${im.width}×${im.height}, ${im.bands} band(s), ${esc(im.format || '?')}">
        <img src="data:${im.preview_b64 ? 'image/jpeg' : 'application/octet-stream'};base64,${im.preview_b64 || im.base64}" alt="">
        <button class="pv-x" data-i="${i}" title="Remove">&times;</button>
        <div class="pv-tag">${role}</div>
      </div>`;
  }).join('');
  strip.querySelectorAll('.pv-x').forEach(b =>
    b.addEventListener('click', () => { state.images.splice(+b.dataset.i, 1); renderPreview(); }));
}

/* =============================================================== COMPOSER */
function attachComposerHandlers() {
  const input = $('queryInput');
  $('sendBtn').addEventListener('click', send);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  });

  $('modeSelect').addEventListener('change', e => { state.mode = e.target.value; });

  document.querySelectorAll('.chip[data-q]').forEach(chip => {
    chip.addEventListener('click', () => {
      input.value = chip.dataset.q;
      if (chip.dataset.mode) { state.mode = chip.dataset.mode; $('modeSelect').value = chip.dataset.mode; }
      input.focus();
    });
  });
}

async function send() {
  const input = $('queryInput');
  const query = input.value.trim();
  if (state.busy) return;
  if (!query) { toast('Type a question first'); return; }
  if (state.images.length === 0) { toast('Attach at least one satellite image'); return; }
  if (state.mode === 'bitemporal' && state.images.length !== 2) { toast('Bi-temporal mode needs exactly 2 images (before / after)'); return; }
  if (state.mode === 'crossmodal' && state.images.length !== 2) { toast('Optical + SAR mode needs exactly 2 images'); return; }

  addUserMsg(query);
  input.value = ''; input.style.height = 'auto';
  setBusy(true);

  const payload = {
    query,
    images: state.images.map(im => ({
      data: im.base64,
      name: im.filename || null,
      modality: im.detected_modality === 'sar' ? 'sar'
        : im.detected_modality === 'optical' ? 'optical' : null
    })),
    mode: state.mode
  };

  const t0 = performance.now();
  try {
    const r = await fetch(`${API}/vlm/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
    state.responses.set(data.query_id, data);
    addAIMsg(data, performance.now() - t0);
    refreshHistory();
  } catch (err) {
    addSystemMsg(`Request failed: ${err.message}`, true);
  } finally {
    setBusy(false);
  }
}

function setBusy(on) {
  state.busy = on;
  $('sendBtn').disabled = on;
  $('busyHint').hidden = !on;
  $('dropHint').hidden = on;
  document.querySelectorAll('#pipelineList li').forEach(li => {
    li.className = '';
    if (!on) return;
    const order = ['validate', 'classify', 'select', 'execute', 'combine', 'report'];
    li.classList.add('active');                 // simple animated marker
    void order;
  });
  if (on) {
    const items = [...document.querySelectorAll('#pipelineList li')];
    items.forEach((li, i) => setTimeout(() => {
      items.forEach((x, j) => { x.className = j < i ? 'done' : x === li ? 'active' : ''; });
    }, i * 450));
  }
}

/* ================================================================ RENDER */
function addUserMsg(text) {
  hideWelcome();
  chat.insertAdjacentHTML('beforeend', `
    <div class="msg msg-user">
      <div class="avatar">YOU</div>
      <div class="bubble"><div class="m-text">${liteMd(text)}</div></div>
    </div>`);
  scrollChat();
}

function addAIMsg(data, clientMs) {
  const rejected = data.status === 'rejected';
  const conf = Math.round((data.confidence || 0) * 100);
  const val = data.validation || {};
  const issues = val.issues || [];
  const trace = data.trace || {};

  const valPills = `
    <span class="v-pill ${rejected ? 'err' : 'ok'}">${rejected ? 'INPUT REJECTED' : 'INPUTS ACCEPTED'}</span>
    ${issues.filter(i => i.level !== 'error').map(i => `<span class="v-pill ${i.level === 'error' ? 'err' : i.level}">${esc(i.code)}</span>`).join('')}
    ${(val.images || []).map(im => `<span class="v-pill">${esc(im.format || '?')} · ${im.width}×${im.height} · ${esc(im.detected_modality)}</span>`).join('')}`;

  const manifestHtml = renderManifest(data.visual_evidence || []);
  const evidenceHtml = renderEvidence(data.visual_evidence || []);
  const geoHtml = renderGeoJSON(data.geojson);

  // provenance: which model produced this answer and how it is served
  const provBits = [];
  if (trace.model) provBits.push(shortModel(trace.model));
  if (trace.vlm_mode) provBits.push(esc(trace.vlm_mode));
  const prov = provBits.length
    ? `<span class="prov-chip" title="Model provenance — the model and serving mode that produced this answer (see execution trace for the full model-registry decision)">${provBits.join(' · ')}</span>` : '';

  chat.insertAdjacentHTML('beforeend', `
    <div class="msg msg-ai" data-qid="${esc(data.query_id)}">
      <div class="avatar">AI</div>
      <div class="bubble">
        <div class="val-banner">${valPills}</div>
        <div class="m-text">${liteMd(data.response || '(no content)')}</div>
        ${manifestHtml}
        ${evidenceHtml}
        ${geoHtml}
        <div class="msg-meta">
          ${!rejected ? `
          <span class="conf" title="${esc(confTooltip(data))}"><span class="conf-bar"><i style="width:${conf}%"></i></span>${conf}% confidence</span>` : ''}
          ${prov}
          <span class="v-pill">${esc(data.task_type || '—')}</span>
          <span>${(data.execution_time_ms || 0).toFixed(0)} ms</span>
          <button class="meta-link" onclick="openTrace('${data.query_id}')">execution trace</button>
          <button class="meta-link" onclick="openReport('${data.query_id}','html')">report</button>
          <button class="meta-link" onclick="downloadReport('${data.query_id}','html')">↓ html</button>
          <button class="meta-link" onclick="downloadReport('${data.query_id}','json')">↓ json</button>
          ${!rejected ? `
          <span class="fb-group" role="group" aria-label="Rate this answer">
            <button class="fb-btn fb-up" title="Correct / useful — record a positive analyst review" onclick="sendFeedback('${data.query_id}','up',this)">👍</button>
            <button class="fb-btn fb-down" title="Flag for review — record a negative analyst review" onclick="sendFeedback('${data.query_id}','down',this)">👎</button>
          </span>` : ''}
        </div>
      </div>
    </div>`);
  scrollChat();
  void clientMs;
}

/* ---------------- chain of evidence (transparency) ---------------- */
const EV_KIND_LABEL = {
  annotated_boxes: 'grounding',
  change_map: 'change map',
  side_by_side: 'comparison',
  index_map: 'spectral index',
  input_view: 'input'
};

function renderManifest(items) {
  if (!items.length) return '';
  const chips = items.map((ev, i) => `
    <button class="ev-chip" data-ev="${i + 1}" type="button"
            title="Jump to ${esc(ev.title)}">
      <span class="ev-chip-id">EV-${i + 1}</span>${esc(EV_KIND_LABEL[ev.kind] || 'evidence')}
    </button>`).join('');
  return `<div class="ev-manifest">
    <span class="ev-manifest-label" title="Every claim is backed by numbered, inspectable visual evidence (chain-of-evidence)">Chain of evidence</span>${chips}
  </div>`;
}

function renderEvidence(items) {
  if (!items.length) return '';
  const cards = items.map((ev, i) => {
    const kind = esc(EV_KIND_LABEL[ev.kind] || (ev.kind || 'evidence'));
    return `
    <figure class="ev-card" data-ev="${i + 1}">
      <div class="ev-imgwrap" onclick="lightbox('data:${ev.mime_type || 'image/jpeg'};base64,${ev.image_base64}')">
        <img src="data:${ev.mime_type || 'image/jpeg'};base64,${ev.image_base64}" alt="${esc(ev.title)}" loading="lazy">
        <span class="ev-kind ev-kind-${esc(ev.kind || 'input_view')}">${kind} · EV-${i + 1}</span>
      </div>
      <figcaption class="ev-cap"><b>${esc(ev.title)}</b>${esc(ev.description || '')}</figcaption>
      ${renderEvStats(ev)}
    </figure>`;
  }).join('');
  return `<div class="evidence">${cards}</div>`;
}

function renderEvStats(ev) {
  const s = ev.stats || {};
  if (ev.kind === 'change_map') {
    const sig = /significant/.test(String(s.verdict || ''));
    return `
      <div class="ev-stats">
        ${s.changed_pixels_pct != null ? `<span class="stat"><b>${esc(String(s.changed_pixels_pct))}%</b> pixels changed</span>` : ''}
        ${(s.regions || []).length ? `<span class="stat"><b>${s.regions.length}</b> dominant region(s)</span>` : ''}
        ${s.verdict ? `<span class="stat stat-verdict ${sig ? 'is-sig' : 'is-quiet'}" title="Heuristic verdict — computed without reference masks">${esc(String(s.verdict))}</span>` : ''}
        ${s.method ? `<span class="stat stat-method" title="${esc(String(s.method))} — heuristic estimate without reference masks">method ⓘ</span>` : ''}
      </div>`;
  }
  if (ev.kind === 'annotated_boxes' && Array.isArray(s.boxes) && s.boxes.length) {
    const rows = s.boxes.map((b, i) => `
      <tr>
        <td>#${i + 1}</td>
        <td>${esc(b.label)}</td>
        <td><span class="conf-bar"><i style="width:${Math.round((b.confidence || 0) * 100)}%"></i></span></td>
        <td class="num">${Math.round((b.confidence || 0) * 100)}%</td>
        <td class="num">[${(b.bbox || []).map(v => Math.round(v)).join(', ')}]</td>
      </tr>`).join('');
    return `
      <details class="box-table">
        <summary>Grounded box data (${s.boxes.length}) — machine-readable</summary>
        <table>
          <thead><tr><th>#</th><th>Label</th><th></th><th>Conf</th><th>bbox 0–1000</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </details>`;
  }
  if (ev.kind === 'index_map' && s && typeof s === 'object') {
    const bits = [];
    if (s.index) bits.push(`<span class="stat"><b>${esc(String(s.index).toUpperCase())}</b></span>`);
    if (s.mean != null) bits.push(`<span class="stat">mean <b>${esc(Number(s.mean).toFixed(3))}</b></span>`);
    if (s.median != null) bits.push(`<span class="stat">median <b>${esc(Number(s.median).toFixed(3))}</b></span>`);
    if (s.p05 != null && s.p95 != null)
      bits.push(`<span class="stat">5–95% <b>${esc(Number(s.p05).toFixed(2))} … ${esc(Number(s.p95).toFixed(2))}</b></span>`);
    const tf = s.threshold_fraction || {};
    if (tf.fraction != null || tf.pct != null)
      bits.push(`<span class="stat"><b>${esc(String(tf.fraction ?? tf.pct))}</b> above threshold</span>`);
    return bits.length ? `<div class="ev-stats">${bits.join('')}</div>` : '';
  }
  return '';
}

function confTooltip(data) {
  const outs = (data.trace?.tool_outputs || []);
  const sources = [...new Set(outs.map(o => o.confidence_source).filter(Boolean))];
  const perTool = outs.map(o => `${o.tool_id} ${Math.round((o.confidence || 0) * 100)}%`);
  return 'Overall confidence = weighted mean of specialist-tool confidences'
    + (sources.length ? ' · sources: ' + sources.join(', ') : '')
    + (perTool.length ? ' · ' + perTool.join(', ') : '');
}

function shortModel(m) {
  return esc(String(m).split('/').pop().slice(0, 34));
}

async function sendFeedback(qid, rating, btn) {
  let comment = '';
  if (rating === 'down') {
    comment = prompt('What went wrong? (optional note, recorded in the audit report)') || '';
  }
  try {
    const r = await fetch(`${API}/vlm/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query_id: qid, rating, comment })
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
    const d = await r.json();
    const group = btn.closest('.fb-group');
    if (group) {
      group.querySelectorAll('.fb-btn').forEach(b => { b.disabled = true; });
      btn.classList.add('active');
    }
    toast(`Analyst review recorded (${d.feedback_summary.up}👍 / ${d.feedback_summary.down}👎) — included in the audit report`);
  } catch (e) {
    toast(`Feedback failed: ${e.message}`);
  }
}

function attachEvidenceNavigation() {
  // chain-of-evidence chips: jump from the answer text to the evidence card
  chat.addEventListener('click', e => {
    const chip = e.target.closest('.ev-chip');
    if (!chip) return;
    const msg = chip.closest('.msg-ai');
    const card = msg?.querySelector(`.ev-card[data-ev="${chip.dataset.ev}"]`);
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add('flash');
    setTimeout(() => card.classList.remove('flash'), 1800);
  });
}

function renderGeoJSON(gj) {
  if (!gj) return '';
  const json = JSON.stringify(gj, null, 2);
  const id = 'gj' + Math.random().toString(36).slice(2, 8);
  window['_' + id] = json;
  return `
    <div class="geojson-block">
      <div class="geojson-head">
        <span>GeoJSON · ${gj.features?.length || 0} feature(s) · ${esc(gj.crs || '')}</span>
        <span>
          <button class="meta-link" onclick="copyText(window._${id})">copy</button>
          <button class="meta-link" onclick="downloadGeoJSON(window._${id})">↓ .geojson</button>
        </span>
      </div>
      <pre class="geojson-body" id="${id}">${esc(json)}</pre>
    </div>`;
}

function addSystemMsg(text, isErr = false) {
  hideWelcome();
  chat.insertAdjacentHTML('beforeend', `<div class="msg-system ${isErr ? 'error' : ''}">${esc(text)}</div>`);
  scrollChat();
}

function hideWelcome() { $('welcome')?.remove(); }
function scrollChat() { chat.scrollTop = chat.scrollHeight; }

/* lite markdown: **bold**, `code`, line breaks — input is escaped first */
function liteMd(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

/* ================================================================ TRACE */
function openTrace(qid) {
  const data = state.responses.get(qid);
  if (!data?.trace) { toast('Trace not available in this session'); return; }
  const t = data.trace;
  const val = t.validation || {};
  $('traceQid').textContent = '· ' + (t.query_id || '').slice(0, 8);

  const kv = (k, v) => `<div class="k">${esc(k)}</div><div class="v">${esc(String(v ?? '—'))}</div>`;

  // waterfall: per-tool share of the total wall-clock time
  const total = Math.max(t.total_execution_time_ms || 0, 1);
  const waterfall = (t.tool_outputs || []).map(o => {
    const pct = Math.max(2, Math.min(100, ((o.execution_time_ms || 0) / total) * 100));
    return `
      <div class="wf-row">
        <span class="wf-tool">${esc(o.tool_id)}</span>
        <span class="wf-track"><i style="width:${pct}%"></i></span>
        <span class="wf-ms">${(o.execution_time_ms || 0).toFixed(0)} ms · conf ${(o.confidence ?? 0).toFixed(2)}</span>
      </div>`;
  }).join('');

  // pipeline stage chips from the recorded timestamps
  const stageOrder = ['received', 'classified', 'tools_done'];
  const stages = stageOrder.filter(k => t.timestamps?.[k]);
  const stageHtml = stages.length ? `
    <div class="stage-row">
      ${stages.map((k, i) => `
        <span class="stage-chip"><b>${esc(k)}</b><time>${esc(t.timestamps[k])}</time></span>
        ${i < stages.length - 1 ? '<span class="stage-arrow">→</span>' : ''}`).join('')}
    </div>` : '';

  // integrity digest (transparency)
  const hash = data.audit_hash || '';
  const hashHtml = hash ? `
    <div class="tr-section">
      <p class="tr-title">Integrity</p>
      <div class="hash-row">
        <code>${esc(hash)}</code>
        <button class="meta-link" onclick="copyText('${esc(hash)}')">copy</button>
      </div>
      <div class="tr-note">SHA-256 over the canonical JSON of this response — recompute it over the downloaded JSON report (minus audit_hash/feedback) to prove the record was not altered.</div>
    </div>` : '';

  const prep = (t.image_preparation || []).map(p =>
    Object.entries(p || {}).filter(([, v]) => v !== null && v !== false && v !== '')
      .map(([k, v]) => `${k}=${v}`).join(' · ')).filter(Boolean);

  $('traceBody').innerHTML = `
    <div class="tr-section">
      <p class="tr-title">Query</p>
      <div class="tr-query">${esc(t.query || '(not recorded)')}</div>
    </div>
    <div class="tr-section">
      <p class="tr-title">Pipeline stages</p>
      ${stageHtml || '<div class="tr-note">No timestamps recorded.</div>'}
      <div class="tr-kv" style="margin-top:8px">
        ${kv('Total time', `${(t.total_execution_time_ms || 0).toFixed(0)} ms`)}
      </div>
    </div>
    <div class="tr-section">
      <p class="tr-title">Decision</p>
      <div class="tr-kv">
        ${kv('Task classified', t.task_type)}
        ${kv('Classification', t.classification_reason)}
        ${kv('Task confidence', (t.task_confidence ?? 0).toFixed(2))}
        ${kv('Mode requested', t.mode_requested)}
        ${kv('Model', t.model)}${kv('VLM mode', t.vlm_mode)}
      </div>
    </div>
    <div class="tr-section">
      <p class="tr-title">Tools selected → invoked</p>
      <div class="tr-kv">
        ${kv('Selected', (t.tools_selected || []).join(', '))}
        ${kv('Invoked', (t.tools_invoked || []).join(', '))}
      </div>
      ${waterfall ? `<p class="tr-title" style="margin-top:12px">Execution waterfall</p>${waterfall}` : ''}
    </div>
    ${(t.tool_outputs || []).map(o => `
      <div class="tr-section">
        <div class="tr-tool">
          <div class="tr-tool-head">
            <span class="tr-tool-id">${esc(o.tool_id)}</span>
            <span class="tr-tool-stats">${(o.execution_time_ms || 0).toFixed(0)} ms · conf ${(o.confidence ?? 0).toFixed(2)} · ${esc(o.confidence_source || '')}</span>
          </div>
          <div class="params">params: ${esc(JSON.stringify(o.parameters_used || {}))}</div>
          ${o.change_stats ? `<div class="params">change_stats: ${esc(JSON.stringify(o.change_stats))}</div>` : ''}
        </div>
      </div>`).join('')}
    <div class="tr-section">
      <p class="tr-title">Validation</p>
      <ul class="tr-issues">
        ${(val.issues || []).length
          ? (val.issues || []).map(i => `<li class="tr-note">[${esc(i.level)}] ${esc(i.code)} — ${esc(i.message)}</li>`).join('')
          : '<li class="tr-note">No issues.</li>'}
        ${(val.images || []).map(im => `<li class="tr-note">#${im.index + 1} ${esc(im.format)} ${im.width}×${im.height}, ${im.num_bands} band(s), ${esc(im.detected_modality)}${im.georeferenced ? ', georeferenced' : ''}</li>`).join('')}
      </ul>
      ${val.pair_compatibility ? `<div class="tr-note">pair: ${esc(val.pair_compatibility)}</div>` : ''}
    </div>
    ${prep.length ? `
    <div class="tr-section">
      <p class="tr-title">Image preparation</p>
      ${prep.map(p => `<div class="tr-note">• ${esc(p)}</div>`).join('')}
    </div>` : ''}
    ${(t.notes || []).length ? `
    <div class="tr-section">
      <p class="tr-title">Notes</p>
      ${(t.notes || []).map(n => `<div class="tr-note">• ${esc(n)}</div>`).join('')}
    </div>` : ''}
    ${hashHtml}
    <div class="tr-section">
      <p class="tr-title">Timeline</p>
      <div class="tr-kv">${Object.entries(t.timestamps || {}).map(([k, v]) => kv(k, v)).join('')}</div>
    </div>`;
  $('traceDrawer').hidden = false;
}

function closeTrace() { $('traceDrawer').hidden = true; }

/* ================================================================ REPORTS */
function openReport(qid, format) {
  window.open(`${API}/vlm/report/${qid}?format=${format}`, '_blank');
}
function downloadReport(qid, format) {
  const a = document.createElement('a');
  a.href = `${API}/vlm/report/${qid}/download?format=${format}`;
  a.download = '';
  a.click();
  toast('Report download started');
}
function downloadGeoJSON(jsonStr) {
  const blob = new Blob([jsonStr], { type: 'application/geo+json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `satai_grounding_${Date.now()}.geojson`;
  a.click();
  URL.revokeObjectURL(a.href);
}
async function copyText(s) {
  try { await navigator.clipboard.writeText(s); toast('Copied to clipboard'); }
  catch { toast('Clipboard blocked by browser'); }
}

/* ================================================================ HISTORY */
async function refreshHistory() {
  try {
    const r = await fetch(`${API}/vlm/history`);
    const d = await r.json();
    const qs = d.queries || [];
    $('historyList').innerHTML = qs.length
      ? qs.map(q => `
        <div class="history-item" data-qid="${esc(q.query_id)}">
          <div class="h-q">${esc(q.query || '(no text)')}</div>
          <div class="h-meta">
            <span class="h-task">${esc(q.task_type)}</span>
            <span>${Math.round((q.confidence || 0) * 100)}%</span>
            <span>${(q.timestamp || '').replace('T', ' ').slice(0, 16)}</span>
          </div>
        </div>`).join('')
      : '<div class="dim pad8">No queries yet.</div>';
    $('historyList').querySelectorAll('.history-item').forEach(el =>
      el.addEventListener('click', () => reopenQuery(el.dataset.qid)));
  } catch { /* offline — leave as-is */ }
}

async function reopenQuery(qid) {
  const local = state.responses.get(qid);
  if (local) { openTrace(qid); return; }
  try {
    const r = await fetch(`${API}/vlm/report/${qid}?format=json`);
    if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
    const full = await r.json();
    // normalise report JSON into response shape
    const resp = {
      query_id: qid,
      status: full.status || 'ok',
      response: full.response || full.answer || '',
      task_type: full.task_type || '',
      confidence: full.confidence || 0,
      visual_evidence: full.visual_evidence || [],
      geojson: full.geojson || null,
      validation: full.validation || null,
      execution_time_ms: full.execution_time_ms || full.trace?.total_execution_time_ms || 0,
      trace: full.trace || null,
      audit_hash: full.audit_hash || null
    };
    state.responses.set(qid, resp);
    addAIMsg(resp, 0);
  } catch (e) { toast(`Could not reopen query: ${e.message}`); }
}

/* ================================================================ CHROME */
function attachChromeHandlers() {
  $('traceClose').addEventListener('click', closeTrace);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeTrace(); hideLightbox(); } });

  $('aboutBtn').addEventListener('click', () => { $('aboutModal').hidden = false; });
  $('aboutClose').addEventListener('click', () => { $('aboutModal').hidden = true; });
  $('aboutModal').addEventListener('click', e => { if (e.target.id === 'aboutModal') $('aboutModal').hidden = true; });

  $('historyRefresh').addEventListener('click', refreshHistory);
  $('sidebarToggle').addEventListener('click', () => {
    const sb = $('sidebar');
    sb.classList.toggle('collapsed');
    localStorage.setItem('satai_sidebar', sb.classList.contains('collapsed') ? '0' : '1');
  });
  // Sidebar starts collapsed unless the user explicitly reopened it —
  // on narrow screens it is an overlay drawer, so keep it closed by default there.
  const sbPref = localStorage.getItem('satai_sidebar');
  const narrow = window.matchMedia('(max-width: 900px)').matches;
  if (sbPref === '0' || (sbPref !== '1' && narrow)) $('sidebar').classList.add('collapsed');
}

/* ================================================================ THEME */
function attachThemeToggle() {
  $('themeBtn').addEventListener('click', () => {
    const root = document.documentElement;
    const dark = root.classList.toggle('dark');
    localStorage.setItem('satai_theme', dark ? 'dark' : 'light');
    toast(dark ? 'Dark theme — mission-control night mode'
               : 'Light theme — daylight mode');
  });
}

function lightbox(src) {
  if (!src) return;
  const div = document.createElement('div');
  div.className = 'lightbox';
  div.innerHTML = `<img src="${src}" alt="">`;
  div.addEventListener('click', () => div.remove());
  document.body.appendChild(div);
}
function hideLightbox() { document.querySelector('.lightbox')?.remove(); }

let toastTimer;
function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s ?? '');
  return d.innerHTML;
}
