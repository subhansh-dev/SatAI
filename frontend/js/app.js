/**
 * SatAI — SatQuery AI frontend (PS SIH26167)
 * Vanilla JS · no frameworks · offline-capable
 *
 * Talks to the agentic backend:
 *   GET  /vlm/status            backend + registry info
 *   POST /vlm/upload            image -> base64 + modality/format probe
 *   POST /vlm/query             full agentic pipeline
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
        <img src="data:application/octet-stream;base64,${im.base64}" alt="">
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

  const valPills = `
    <span class="v-pill ${rejected ? 'err' : 'ok'}">${rejected ? 'INPUT REJECTED' : 'INPUTS ACCEPTED'}</span>
    ${issues.filter(i => i.level !== 'error').map(i => `<span class="v-pill ${i.level === 'error' ? 'err' : i.level}">${esc(i.code)}</span>`).join('')}
    ${(val.images || []).map(im => `<span class="v-pill">${esc(im.format || '?')} · ${im.width}×${im.height} · ${esc(im.detected_modality)}</span>`).join('')}`;

  const evidenceHtml = renderEvidence(data.visual_evidence || []);
  const geoHtml = renderGeoJSON(data.geojson);

  chat.insertAdjacentHTML('beforeend', `
    <div class="msg msg-ai">
      <div class="avatar">AI</div>
      <div class="bubble">
        <div class="val-banner">${valPills}</div>
        <div class="m-text">${liteMd(data.response || '(no content)')}</div>
        ${evidenceHtml}
        ${geoHtml}
        <div class="msg-meta">
          ${!rejected ? `
          <span class="conf"><span class="conf-bar"><i style="width:${conf}%"></i></span>${conf}% confidence</span>` : ''}
          <span class="v-pill">${esc(data.task_type || '—')}</span>
          <span>${(data.execution_time_ms || 0).toFixed(0)} ms</span>
          <button class="meta-link" onclick="openTrace('${data.query_id}')">execution trace</button>
          <button class="meta-link" onclick="openReport('${data.query_id}','html')">report</button>
          <button class="meta-link" onclick="downloadReport('${data.query_id}','html')">↓ html</button>
          <button class="meta-link" onclick="downloadReport('${data.query_id}','json')">↓ json</button>
        </div>
      </div>
    </div>`);
  scrollChat();
  void clientMs;
}

function renderEvidence(items) {
  if (!items.length) return '';
  const cards = items.map(ev => `
    <figure class="ev-card" onclick="lightbox('${ev.image_base64 ? 'data:image/png;base64,' + ev.image_base64 : ''}')">
      <img src="data:image/png;base64,${ev.image_base64}" alt="${esc(ev.title)}" loading="lazy">
      <figcaption class="ev-cap"><b>${esc(ev.title)}</b>${esc(ev.description || '')}</figcaption>
    </figure>`).join('');
  return `<div class="evidence">${cards}</div>`;
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
  $('traceBody').innerHTML = `
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
        ${kv('Total time', `${(t.total_execution_time_ms || 0).toFixed(0)} ms`)}
      </div>
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
    ${(t.notes || []).length ? `
    <div class="tr-section">
      <p class="tr-title">Notes</p>
      ${(t.notes || []).map(n => `<div class="tr-note">• ${esc(n)}</div>`).join('')}
    </div>` : ''}
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
      trace: full.trace || null
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
