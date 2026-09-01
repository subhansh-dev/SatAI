/**
 * SatAI — VLM Chat Frontend
 * Handles image upload, chat, mode selection, and execution trace.
 */

let vlmImages = [];
let vlmMode = 'auto';
let vlmSending = false;
let vlmTraceOpen = false;

document.addEventListener('DOMContentLoaded', () => {
    initVLMUpload();
    initVLMModes();
    checkVLMStatus();
});

// --- Upload ---
function initVLMUpload() {
    const dz = document.getElementById('vlm-dropzone');
    const fi = document.getElementById('vlm-file-input');
    if (!dz || !fi) return;

    dz.addEventListener('click', () => fi.click());
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
    dz.addEventListener('drop', e => {
        e.preventDefault();
        dz.classList.remove('dragover');
        handleVLMFiles(e.dataTransfer.files);
    });
    fi.addEventListener('change', e => handleVLMFiles(e.target.files));
}

async function handleVLMFiles(files) {
    for (const file of files) {
        if (vlmImages.length >= 4) break;
        if (file.size > 20 * 1024 * 1024) {
            vlmAddSystem(`File too large: ${file.name} (max 20MB)`);
            continue;
        }
        try {
            const b64 = await readFileAsBase64(file);
            vlmImages.push(b64);
        } catch (e) {
            vlmAddSystem(`Failed to read ${file.name}: ${e.message}`);
        }
    }
    vlmUpdatePreview();
}

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function vlmUpdatePreview() {
    const preview = document.getElementById('vlm-preview');
    const meta = document.getElementById('vlm-metadata');
    if (!preview) return;

    if (vlmImages.length === 0) {
        preview.style.display = 'none';
        if (meta) meta.style.display = 'none';
        return;
    }

    preview.style.display = 'flex';
    if (meta) meta.style.display = 'block';
    preview.innerHTML = vlmImages.map((b64, i) => `
        <div class="vlm-preview-item">
            <img src="data:image/jpeg;base64,${b64}" alt="Image ${i + 1}">
            <button class="vlm-preview-remove" onclick="vlmRemoveImage(${i})" title="Remove">&times;</button>
            <div class="vlm-preview-label">${i === 0 ? 'Before' : i === 1 ? 'After' : `Img ${i+1}`}</div>
        </div>
    `).join('');
}

function vlmRemoveImage(idx) {
    vlmImages.splice(idx, 1);
    vlmUpdatePreview();
}

// --- Mode Selection ---
function initVLMModes() {
    document.querySelectorAll('.vlm-mode-card').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.vlm-mode-card').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            vlmMode = btn.dataset.mode;
        });
    });
}

// --- Chat ---
function vlmSend() {
    const input = document.getElementById('vlm-input');
    const query = input.value.trim();
    if (!query || vlmSending) return;
    if (vlmImages.length === 0) {
        vlmAddSystem('Upload at least one satellite image before asking a question.');
        return;
    }

    vlmAddUser(query);
    input.value = '';
    input.style.height = 'auto';
    vlmSending = true;
    const btn = document.getElementById('vlm-send-btn');
    if (btn) btn.disabled = true;

    vlmCallAPI(query);
}

function vlmSuggestion(text) {
    const input = document.getElementById('vlm-input');
    if (input) input.value = text;
    vlmSend();
}

async function vlmCallAPI(query) {
    const payload = { query, images: vlmImages, mode: vlmMode };
    const lat = document.getElementById('vlm-lat')?.value;
    const lon = document.getElementById('vlm-lon')?.value;
    if (lat && lon) payload.metadata = { lat: parseFloat(lat), lon: parseFloat(lon) };

    try {
        const resp = await fetch('/vlm/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) {
            vlmAddSystem(`Error ${resp.status}: ${data.detail || data.error || 'Request failed'}`);
        } else {
            vlmAddAssistant(data.response, data.confidence);
            if (data.trace) vlmShowTrace(data.trace);
        }
    } catch (e) {
        vlmAddSystem(`Network error: ${e.message}`);
    } finally {
        vlmSending = false;
        const btn = document.getElementById('vlm-send-btn');
        if (btn) btn.disabled = false;
    }
}

// --- Messages ---
function vlmAddUser(text) {
    const chat = document.getElementById('vlm-chat');
    const welcome = chat.querySelector('.vlm-welcome');
    if (welcome) welcome.remove();
    chat.innerHTML += `
        <div class="vlm-msg vlm-msg-user">
            <div class="vlm-msg-avatar">You</div>
            <div class="vlm-msg-body">${escHtml(text)}</div>
        </div>`;
    vlmScrollChat();
}

function vlmAddAssistant(text, confidence) {
    const chat = document.getElementById('vlm-chat');
    const formatted = escHtml(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    const conf = confidence != null
        ? `<span class="vlm-conf">${(confidence * 100).toFixed(0)}%</span>`
        : '';
    chat.innerHTML += `
        <div class="vlm-msg vlm-msg-assistant">
            <div class="vlm-msg-avatar">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            </div>
            <div class="vlm-msg-body">${formatted} ${conf}</div>
        </div>`;
    vlmScrollChat();
}

function vlmAddSystem(text) {
    const chat = document.getElementById('vlm-chat');
    chat.innerHTML += `
        <div class="vlm-msg vlm-msg-system">
            <div class="vlm-msg-body">${escHtml(text)}</div>
        </div>`;
    vlmScrollChat();
}

function vlmScrollChat() {
    const chat = document.getElementById('vlm-chat');
    if (chat) chat.scrollTop = chat.scrollHeight;
}

// --- Trace ---
function vlmShowTrace(trace) {
    const panel = document.getElementById('vlm-trace');
    const content = document.getElementById('vlm-trace-content');
    const summary = document.getElementById('vlm-trace-summary');
    if (!panel || !content) return;

    panel.style.display = 'block';

    const toolCount = (trace.tools_invoked || []).length;
    const totalMs = trace.total_execution_time_ms?.toFixed(0) || '?';
    if (summary) summary.textContent = `${toolCount} tools, ${totalMs}ms`;

    const tools = (trace.tools_invoked || []).map(t => `<span class="vlm-trace-tag">${t}</span>`).join(' ');
    const steps = (trace.tool_outputs || []).map(o => `
        <div class="vlm-trace-step">
            <span class="vlm-trace-tool">${o.tool_id}</span>
            <span class="vlm-trace-time">${o.execution_time_ms?.toFixed(0) || '?'}ms</span>
            <span class="vlm-trace-conf">${o.confidence != null ? (o.confidence * 100).toFixed(0) : '?'}%</span>
        </div>
    `).join('');

    content.innerHTML = `
        <div class="vlm-trace-row"><span class="vlm-trace-label">Task:</span> ${trace.task_type}</div>
        <div class="vlm-trace-row"><span class="vlm-trace-label">Tools:</span> ${tools}</div>
        <div class="vlm-trace-row"><span class="vlm-trace-label">Total:</span> ${totalMs}ms</div>
        <div class="vlm-trace-row"><span class="vlm-trace-label">ID:</span> <code>${trace.query_id?.slice(0, 8) || '?'}</code></div>
        <div class="vlm-trace-steps">${steps}</div>
    `;
}

function vlmToggleTrace() {
    const content = document.getElementById('vlm-trace-content');
    const toggle = document.querySelector('.vlm-trace-toggle');
    if (!content) return;
    vlmTraceOpen = !vlmTraceOpen;
    content.style.display = vlmTraceOpen ? 'block' : 'none';
    if (toggle) toggle.classList.toggle('open', vlmTraceOpen);
}

function vlmClearChat() {
    const chat = document.getElementById('vlm-chat');
    if (!chat) return;
    chat.innerHTML = `
        <div class="vlm-welcome">
            <div class="vlm-welcome-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 6v6l4 2"/>
                </svg>
            </div>
            <div class="vlm-welcome-title">SatQuery AI</div>
            <div class="vlm-welcome-sub">Ready</div>
        </div>`;
    const trace = document.getElementById('vlm-trace');
    if (trace) trace.style.display = 'none';
    vlmTraceOpen = false;
}

// --- Status ---
async function checkVLMStatus() {
    const dot = document.getElementById('vlm-status-dot');
    const text = document.getElementById('vlm-status');
    try {
        const resp = await fetch('/vlm/status');
        const data = await resp.json();
        if (text) text.textContent = `${data.mode.toUpperCase()} — ${data.model.split('/').pop()}`;
        if (dot) dot.className = 'vlm-status-dot ' + (data.available ? 'online' : 'offline');
    } catch (e) {
        if (text) text.textContent = 'offline';
        if (dot) dot.className = 'vlm-status-dot offline';
    }
}

// --- Util ---
function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
