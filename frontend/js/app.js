const API = '';

function initBoot() {
    const boot = document.getElementById('boot');
    const ring = document.getElementById('bootRing');
    const percent = document.getElementById('bootPercent');
    if (!boot || !ring) return;

    const circumference = 226.2;

    async function pingBackend() {
        try {
            const r = await fetch('/api/health', { method: 'GET' });
            return r.ok;
        } catch (e) {
            return false;
        }
    }

    let progress = 0;
    function tickBoot() {
        progress += Math.random() * 3 + 0.5;
        if (progress > 90) progress = 90;
        ring.style.strokeDashoffset = circumference * (1 - progress / 100);
        percent.textContent = Math.floor(progress);
    }

    let awake = false;
    let attempts = 0;
    (async function checkBackend() {
        while (!awake) {
            attempts++;
            tickBoot();
            awake = await pingBackend();
            if (!awake) {
                await new Promise(r => setTimeout(r, 2000));
            }
        }
        ring.style.strokeDashoffset = 0;
        percent.textContent = '100';
        setTimeout(() => boot.classList.add('done'), 600);
    })();
}

function initMap() {
    const map = L.map('map', {
        center: [28.6139, 77.2090],
        zoom: 13,
        zoomControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CartoDB &copy; OSM',
        maxZoom: 19,
    }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);

    let marker, scanCircle;

    map.on('click', (e) => setLocation(e.latlng.lat, e.latlng.lng));
    setLocation(28.6139, 77.2090);
    window.map = map;

    function setLocation(lat, lon) {
        document.getElementById('input-lat').value = lat.toFixed(6);
        document.getElementById('input-lon').value = lon.toFixed(6);

        if (marker) map.removeLayer(marker);
        if (scanCircle) map.removeLayer(scanCircle);

        marker = L.marker([lat, lon], {
            icon: L.divIcon({
                className: 'chronovisor-marker',
                html: '<div style="width:18px;height:18px;background:#c8a87c;border-radius:0;border:3px solid #010103;box-shadow:0 0 20px rgba(200,168,124,0.5);"></div>',
                iconSize: [18, 18],
                iconAnchor: [9, 9],
            }),
        }).addTo(map);

        const radius = parseInt(document.getElementById('input-radius').value) || 500;
        scanCircle = L.circle([lat, lon], {
            radius: radius,
            color: 'rgba(200,168,124,0.25)',
            fillColor: 'rgba(200,168,124,0.02)',
            fillOpacity: 1,
            weight: 1,
            dashArray: '4,4',
        }).addTo(map);
    }
}

function setStatus(text, type) {
    const el = document.getElementById('scan-status');
    if (el) {
        const color = type === 'error' ? '#ff4444' : type === 'success' ? '#c8a87c' : '#666';
        el.innerHTML = `<span style="color:${color}">${text}</span>`;
    }
}

function getLocationData() {
    const startDate = document.getElementById('input-start').value || '2017-01-01';
    const year = parseInt(startDate.split('-')[0]);
    const clampedDate = year < 2013 ? '2013-03-18' : startDate;

    return {
        lat: parseFloat(document.getElementById('input-lat').value),
        lon: parseFloat(document.getElementById('input-lon').value),
        radius_m: parseInt(document.getElementById('input-radius').value) || 500,
        start_date: clampedDate,
        source: document.getElementById('input-source').value,
    };
}

async function apiPost(endpoint, data) {
    setStatus('Scanning...');
    try {
        const resp = await fetch(API + endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        const result = await resp.json();
        setStatus('Complete', 'success');
        setTimeout(() => setStatus('Ready'), 3000);
        return result;
    } catch (err) {
        setStatus('Error: ' + err.message, 'error');
        return null;
    }
}

async function apiGet(endpoint) {
    setStatus('Fetching...');
    try {
        const resp = await fetch(API + endpoint);
        const result = await resp.json();
        setStatus('Ready');
        return result;
    } catch (err) {
        setStatus('Error: ' + err.message, 'error');
        return null;
    }
}

async function runFullScan() {
    const loc = getLocationData();
    const result = await apiGet(`/api/full-scan?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}`);
    if (result) {
        document.querySelector('[data-tab="analysis"]').click();
        displayFullScanResults(result);
    }
}

function displayFullScanResults(data) {
    const summary = data.summary || {};
    const findings = summary.findings || [];
    const conf = summary.confidence || 'low';
    const score = summary.archaeological_potential || 0;

    const badge = document.getElementById('confidence-badge');
    if (badge) badge.textContent = conf.toUpperCase();

    let summaryHTML = `
        <div class="metric-row">
            <div class="metric"><span class="metric-value">${score.toFixed(0)}%</span><span class="metric-label">Archaeological Potential</span></div>
            <div class="metric"><span class="metric-value">${data.satellite?.data_points || 0}</span><span class="metric-label">Data Points</span></div>
            <div class="metric"><span class="metric-value">${data.lightning?.strikes || '--'}</span><span class="metric-label">EM Events</span></div>
        </div>
    `;

    findings.forEach(f => {
        summaryHTML += `<div class="finding-card info">${f}</div>`;
    });

    document.getElementById('summary-content').innerHTML = summaryHTML;

    const ts = data.satellite?.timeseries || [];
    if (ts.length > 0) {
        setTimeout(() => plotTimeseries(ts), 300);
    } else {
        const noData = '<div class="finding-card info">No satellite data for this date range. Sentinel-2 (2017+), Landsat 8 (2013+).</div>';
        document.getElementById('timeseries-chart').innerHTML = noData;
        document.getElementById('timeseries-chart-surface').innerHTML = noData;
    }

    const anomalies = data.anomalies || [];
    let anomalyHTML = anomalies.length === 0
        ? '<div class="empty-state">No anomalies detected</div>'
        : anomalies.map(a => `<div class="finding-card warning"><strong>${a.type.replace(/_/g, ' ').toUpperCase()}</strong> — ${a.date}<br>${a.interpretation}</div>`).join('');
    document.getElementById('anomalies-content').innerHTML = anomalyHTML;

    const structural = data.structural_analysis || {};
    const structScore = structural.structural_probability || 0;
    document.getElementById('structural-content').innerHTML = `
        <div class="metric-row">
            <div class="metric"><span class="metric-value">${structScore.toFixed(0)}%</span><span class="metric-label">Structure Probability</span></div>
        </div>
    `;

    const env = data.environmental || {};
    if (env.soil?.properties) {
        let soilHTML = '<div class="finding-card info"><strong>SOIL</strong></div>';
        for (const [k, v] of Object.entries(env.soil.properties)) {
            soilHTML += `<span class="metric"><span class="value">${v.value}</span><span class="label">${k}</span></span>`;
        }
        document.getElementById('env-content').innerHTML = soilHTML;
    }

    const web = data.historical_web || {};
    if (web.wayback?.count) {
        let webHTML = `<div class="finding-card info"><strong>WAYBACK MACHINE</strong> — ${web.wayback.count} archives</div>`;
        document.getElementById('webarchive-content').innerHTML = webHTML;
    }

    const arch = data.archaeological_db || {};
    if (arch.pleiades?.places) {
        let archHTML = `<div class="finding-card info"><strong>ARCHAEOLOGICAL SITES</strong> — ${arch.pleiades.count} nearby</div>`;
        document.getElementById('archdb-content').innerHTML = archHTML;
    }
}

async function runMegaScan() {
    const loc = getLocationData();
    const place = prompt('Place name (optional):') || '';
    const result = await apiGet(`/api/mega-scan?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}&place_name=${encodeURIComponent(place)}`);
    if (result) {
        document.querySelector('[data-tab="analysis"]')?.click();
        displayFullScanResults(result);
    }
}

async function runEnvironmentalScan() {
    const loc = getLocationData();
    const result = await apiGet(`/api/env/full?lat=${loc.lat}&lon=${loc.lon}`);
    if (result) {
        document.querySelector('[data-tab="analysis"]')?.click();
        displayEnvironmental(result);
    }
}

function displayEnvironmental(env) {
    let html = '';
    if (env.soil?.properties) {
        html += '<div class="finding-card info"><strong>SOIL</strong></div>';
        for (const [k, v] of Object.entries(env.soil.properties)) {
            html += `<span class="metric"><span class="value">${v.value}</span><span class="label">${k}</span></span>`;
        }
    }
    const el = document.getElementById('env-content');
    if (el) el.innerHTML = html || '<div class="empty-state">No environmental data</div>';
}

async function runHistoricalWeb() {
    const loc = getLocationData();
    const place = prompt('Place name:') || '';
    const result = await apiGet(`/api/web/full?lat=${loc.lat}&lon=${loc.lon}&place_name=${encodeURIComponent(place)}`);
    if (result) {
        document.querySelector('[data-tab="analysis"]')?.click();
        displayWebArchives(result);
    }
}

async function loadHistory() {
    const result = await apiGet('/api/history');
    const el = document.getElementById('history-content');
    if (!el || !result?.scans?.length) {
        if (el) el.innerHTML = '<div class="empty-state">No scans yet</div>';
        return;
    }

    let html = `<div style="margin-bottom:12px;font-size:11px;color:#666;">${result.count} scan(s) in history</div>`;
    result.scans.forEach((s, i) => {
        const score = s.structural_probability || 0;
        const color = score > 70 ? '#c8a87c' : score > 40 ? '#ff8800' : '#4a5a6a';
        html += `<div class="finding-card" style="cursor:pointer" onclick="viewHistoryScan(${i})">
            <strong>#${i}</strong> ${(s.place_name || '')} (${s.lat?.toFixed(4)}, ${s.lon?.toFixed(4)})
            <span style="color:${color}">Score: ${score.toFixed(0)}%</span>
        </div>`;
    });
    el.innerHTML = html;
}

async function viewHistoryScan(index) {
    const result = await apiGet('/api/history/' + index);
    if (result) {
        document.querySelector('[data-tab="analysis"]').click();
        displayFullScanResults(result);
    }
}

async function runGeminiAnalysis() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Running AI analysis...';
    const result = await apiPost('/api/gemini/analyze', loc);
    if (result?.error) {
        if (status) status.innerHTML = result.error;
        return;
    }
    document.querySelector('[data-tab="ai"]')?.click();
    const ai = result?.ai_analysis || {};
    const scan = result?.scan || {};
    const summary = scan.summary || {};
    const score = summary.archaeological_potential || 0;

    const el = document.getElementById('ai-result');
    if (el) {
        el.innerHTML = `
            <div style="padding:12px;font-size:13px;line-height:1.7;">
                <h3 style="color:#c8a87c;margin-bottom:12px;">AI Analysis</h3>
                ${formatMarkdown(ai.analysis || '')}
                <div style="margin-top:16px;">
                    <span class="metric"><span class="value">${score.toFixed(0)}%</span><span class="label">Potential</span></span>
                </div>
            </div>
        `;
    }
}

function formatMarkdown(text) {
    if (!text) return '';
    let h = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    h = h.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\*(.*?)\*/g, '<em>$1</em>');
    h = h.replace(/^### (.*?)$/gm, '<h4>$1</h4>');
    h = h.replace(/^## (.*?)$/gm, '<h3>$1</h3>');
    h = h.replace(/\n/g, '<br>');
    return h;
}

document.addEventListener('DOMContentLoaded', () => {
    initBoot();
    initMap();
    loadLatestScan();
});

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');

        // Auto-load data when Analysis tab is activated
        if (btn.dataset.tab === 'analysis') {
            loadLatestScan();
        }
    });
});

let _lastTimeseriesData = null;

function loadLatestScan() {
    // Only load on Analysis tab
    if (!document.getElementById('tab-analysis').classList.contains('active')) {
        return;
    }

    const status = document.getElementById('scan-status') || document.getElementById('ai-status');
    if (status) status.innerHTML = 'Loading latest scan...';

    apiGet('/api/history')
        .then(result => {
            if (!result?.scans?.length) {
                showNoScanMessage();
                return;
            }

            const latestScan = result.scans[result.scans.length - 1];
            if (latestScan?.id && latestScan?.result) {
                viewHistoryScan(latestScan.id);
            } else {
                showNoScanMessage();
            }
        })
        .catch(() => {
            if (status) status.innerHTML = 'Error loading scan';
        });
}

function showNoScanMessage() {
    const summaryEl = document.getElementById('summary-content');
    const anomaliesEl = document.getElementById('anomalies-content');
    const structuralEl = document.getElementById('structural-content');
    const envEl = document.getElementById('env-content');
    const webEl = document.getElementById('webarchive-content');
    const archEl = document.getElementById('archdb-content');

    if (summaryEl) {
        summaryEl.innerHTML = `
            <div class="empty-state">
                <div style="margin-bottom: 12px; font-size: 14px; color: var(--text-tertiary);">
                    No scan data found.
                </div>
                <div style="font-size: 12px; color: var(--text-muted);">
                    Run a scan from the Map tab to analyze a location.
                </div>
                <button class="btn-scan" onclick="document.querySelector('[data-tab=\"map\"]').click(); searchPlace()" style="margin-top: 16px;">
                    Search Location
                </button>
            </div>
        `;
    }

    if (anomaliesEl) anomaliesEl.innerHTML = '<div class="empty-state">Scan data will appear here</div>';
    if (structuralEl) structuralEl.innerHTML = '<div class="empty-state">Scan data will appear here</div>';
    if (envEl) envEl.innerHTML = '<div class="empty-state">Scan data will appear here</div>';
    if (webEl) webEl.innerHTML = '<div class="empty-state">Scan data will appear here</div>';
    if (archEl) archEl.innerHTML = '<div class="empty-state">Scan data will appear here</div>';
}

function plotTimeseries(data) {
    _lastTimeseriesData = data;
    const dates = data.map(d => d.date);
    const ndvi = data.map(d => d.ndvi);
    const thermal = data.map(d => d.thermal);

    Plotly.newPlot('timeseries-chart', [{
        x: dates, y: ndvi, name: 'NDVI',
        line: { color: '#c8a87c', width: 2 },
    }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#4a5a6a', size: 10 },
        margin: { t: 30, r: 60, b: 40, l: 60 },
        showlegend: false,
    }, { responsive: true, displayModeBar: false });
}

async function searchPlace() {
    const query = document.getElementById('input-place').value.trim();
    if (!query) return;
    const status = document.getElementById('scan-status');
    if (status) status.innerHTML = 'Searching...';
    const result = await apiGet('/api/geocode?q=' + encodeURIComponent(query));
    if (result?.results?.length > 0) {
        const place = result.results[0];
        setLocation(place.lat, place.lon);
        document.querySelector('[data-tab="map"]').click();
    }
}