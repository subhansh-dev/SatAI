const API = '';
let _map, _marker, _scanCircle;
let _lastScanData = null;
let _chatHistory = [];
let _chatSessionId = 'session_' + Date.now();

// ─── BOOT ────────────────────────────────────────────
function initBoot() {
    const boot = document.getElementById('boot');
    const ring = document.getElementById('bootRing');
    const percent = document.getElementById('bootPercent');
    if (!boot || !ring) return;
    const circumference = 226.2;
    let progress = 0;
    function tickBoot() {
        progress += Math.random() * 3 + 0.5;
        if (progress > 90) progress = 90;
        ring.style.strokeDashoffset = circumference * (1 - progress / 100);
        percent.textContent = Math.floor(progress);
    }
    (async function checkBackend() {
        let awake = false;
        while (!awake) {
            tickBoot();
            try { const r = await fetch('/api/health'); awake = r.ok; } catch { awake = false; }
            if (!awake) await new Promise(r => setTimeout(r, 2000));
        }
        ring.style.strokeDashoffset = 0;
        percent.textContent = '100';
        setTimeout(() => boot.classList.add('done'), 600);
    })();
}

// ─── MAP ─────────────────────────────────────────────
function initMap() {
    _map = L.map('map', { center: [28.6139, 77.2090], zoom: 13, zoomControl: false });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CartoDB &copy; OSM', maxZoom: 19,
    }).addTo(_map);
    L.control.zoom({ position: 'bottomright' }).addTo(_map);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(_map);
    _map.on('click', (e) => setLocation(e.latlng.lat, e.latlng.lng));
    setLocation(28.6139, 77.2090);
    window._map = _map;
}

function setLocation(lat, lon) {
    document.getElementById('input-lat').value = lat.toFixed(6);
    document.getElementById('input-lon').value = lon.toFixed(6);
    if (_marker) _map.removeLayer(_marker);
    if (_scanCircle) _map.removeLayer(_scanCircle);
    _marker = L.marker([lat, lon], {
        icon: L.divIcon({
            className: 'chronovisor-marker',
            html: '<div style="width:18px;height:18px;background:#c8a87c;border-radius:0;border:3px solid #010103;box-shadow:0 0 20px rgba(200,168,124,0.5);"></div>',
            iconSize: [18, 18], iconAnchor: [9, 9],
        }),
    }).addTo(_map);
    const radius = parseInt(document.getElementById('input-radius').value) || 500;
    _scanCircle = L.circle([lat, lon], {
        radius, color: 'rgba(200,168,124,0.25)', fillColor: 'rgba(200,168,124,0.02)',
        fillOpacity: 1, weight: 1, dashArray: '4,4',
    }).addTo(_map);
}

// ─── HELPERS ─────────────────────────────────────────
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
    setStatus('Processing...');
    try {
        const resp = await fetch(API + endpoint, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
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

function formatMarkdown(text) {
    if (!text) return '';
    let h = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    h = h.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\*(.*?)\*/g, '<em>$1</em>');
    h = h.replace(/^### (.*?)$/gm, '<h4 style="color:var(--accent);margin:12px 0 6px;">$1</h4>');
    h = h.replace(/^## (.*?)$/gm, '<h3 style="color:var(--accent);margin:16px 0 8px;">$1</h3>');
    h = h.replace(/\n/g, '<br>');
    return h;
}

function getLatestScanIndex() {
    return _lastScanData?._scanIndex ?? null;
}

// ─── SCAN FUNCTIONS ──────────────────────────────────
async function runFullScan() {
    const loc = getLocationData();
    const result = await apiGet(`/api/full-scan?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}`);
    if (result) {
        _lastScanData = result;
        document.querySelector('[data-tab="analysis"]').click();
        displayFullScanResults(result);
    }
}

async function runMegaScan() {
    const loc = getLocationData();
    const place = prompt('Place name (optional):') || '';
    const result = await apiGet(`/api/mega-scan?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}&place_name=${encodeURIComponent(place)}`);
    if (result) {
        _lastScanData = result;
        document.querySelector('[data-tab="analysis"]')?.click();
        displayFullScanResults(result);
    }
}

async function runSatelliteAnalysis() {
    const loc = getLocationData();
    const result = await apiPost('/api/satellite/timeseries', loc);
    if (result) {
        _lastScanData = { satellite: result, ...(result.anomalies ? { anomalies: result.anomalies } : {}), ...(result.structural_analysis ? { structural_analysis: result.structural_analysis } : {}) };
        document.querySelector('[data-tab="analysis"]')?.click();
        displayFullScanResults(_lastScanData);
    }
}

async function runAnomalyDetection() {
    const loc = getLocationData();
    const result = await apiPost('/api/satellite/anomalies', loc);
    if (result) {
        document.querySelector('[data-tab="analysis"]')?.click();
        const anomalies = result.satellite_anomalies || [];
        let html = anomalies.length === 0
            ? '<div class="empty-state">No anomalies detected</div>'
            : anomalies.map(a => `<div class="finding-card warning"><strong>${(a.type || 'unknown').replace(/_/g, ' ').toUpperCase()}</strong><br>${a.interpretation || a.description || JSON.stringify(a)}</div>`).join('');
        document.getElementById('anomalies-content').innerHTML = html;
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

async function runHistoricalWeb() {
    const loc = getLocationData();
    const place = document.getElementById('input-place')?.value || '';
    const result = await apiGet(`/api/web/full?lat=${loc.lat}&lon=${loc.lon}&place_name=${encodeURIComponent(place)}`);
    if (result) {
        document.querySelector('[data-tab="analysis"]')?.click();
        displayWebArchives(result);
    }
}

// ─── DISPLAY RESULTS ─────────────────────────────────
function displayFullScanResults(data) {
    _lastScanData = data;
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
    findings.forEach(f => { summaryHTML += `<div class="finding-card info">${f}</div>`; });
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
        : anomalies.map(a => `<div class="finding-card warning"><strong>${(a.type || 'unknown').replace(/_/g, ' ').toUpperCase()}</strong> — ${a.date || ''}<br>${a.interpretation || a.description || ''}</div>`).join('');
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
            soilHTML += `<span class="metric"><span class="value">${v.value ?? v}</span><span class="label">${k}</span></span>`;
        }
        document.getElementById('env-content').innerHTML = soilHTML;
    }

    const web = data.historical_web || {};
    if (web.wayback?.count) {
        document.getElementById('webarchive-content').innerHTML = `<div class="finding-card info"><strong>WAYBACK MACHINE</strong> — ${web.wayback.count} archives</div>`;
    }

    const arch = data.archaeological_db || {};
    if (arch.pleiades?.places) {
        document.getElementById('archdb-content').innerHTML = `<div class="finding-card info"><strong>ARCHAEOLOGICAL SITES</strong> — ${arch.pleiades.count || arch.pleiades.places.length} nearby</div>`;
    }

    const weather = data.space_weather || {};
    if (weather.interpretation) {
        document.getElementById('weather-content').innerHTML = `<div class="finding-card info">${weather.interpretation.map(i => `<div>${i}</div>`).join('')}</div>`;
    }

    const maps = data.historical_maps || [];
    if (maps.length > 0) {
        document.getElementById('maps-content').innerHTML = maps.map(m => `<div class="finding-card info"><strong>${m.name || m.source || 'Map'}</strong><br><a href="${m.url || m.link || '#'}" target="_blank" style="color:var(--accent)">${m.url || m.link || 'View'}</a></div>`).join('');
    }
}

function displayEnvironmental(env) {
    let html = '';
    if (env.soil?.properties) {
        html += '<div class="finding-card info"><strong>SOIL</strong></div>';
        for (const [k, v] of Object.entries(env.soil.properties)) {
            html += `<span class="metric"><span class="value">${v.value ?? v}</span><span class="label">${k}</span></span>`;
        }
    }
    if (env.faults?.features?.length) {
        html += `<div class="finding-card info"><strong>SEISMIC</strong> — ${env.faults.features.length} events nearby</div>`;
    }
    if (env.population?.density) {
        html += `<div class="finding-card info"><strong>POPULATION</strong> — ${env.population.density} / km²</div>`;
    }
    const el = document.getElementById('env-content');
    if (el) el.innerHTML = html || '<div class="empty-state">No environmental data</div>';
}

function displayWebArchives(web) {
    let html = '';
    if (web.wayback?.count) {
        html += `<div class="finding-card info"><strong>WAYBACK MACHINE</strong> — ${web.wayback.count} archives</div>`;
        (web.wayback.results || []).slice(0, 5).forEach(r => {
            html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;"><a href="${r.url || r}" target="_blank" style="color:var(--accent)">${r.url || r}</a></div>`;
        });
    }
    if (web.osm?.historic_features?.length) {
        html += `<div class="finding-card info"><strong>OSM HISTORIC</strong> — ${web.osm.historic_features.length} features</div>`;
    }
    document.getElementById('webarchive-content').innerHTML = html || '<div class="empty-state">No web archives found</div>';
}

// ─── CHARTS ──────────────────────────────────────────
function plotTimeseries(data) {
    const dates = data.map(d => d.date);
    const ndvi = data.map(d => d.ndvi);
    const thermal = data.map(d => d.thermal);

    Plotly.newPlot('timeseries-chart', [{
        x: dates, y: ndvi, name: 'NDVI', line: { color: '#c8a87c', width: 2 },
    }], {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#4a5a6a', size: 10 }, margin: { t: 30, r: 60, b: 40, l: 60 },
        showlegend: false, xaxis: { gridcolor: 'rgba(255,255,255,0.03)' },
        yaxis: { gridcolor: 'rgba(255,255,255,0.03)', title: 'NDVI' },
    }, { responsive: true, displayModeBar: false });

    const surfaceEl = document.getElementById('timeseries-chart-surface');
    if (surfaceEl && thermal.length > 0 && thermal.some(t => t != null)) {
        Plotly.newPlot('timeseries-chart-surface', [{
            x: dates, y: thermal, name: 'Surface Temp', line: { color: '#ff6b4a', width: 2 },
        }], {
            paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#4a5a6a', size: 10 }, margin: { t: 30, r: 60, b: 40, l: 60 },
            showlegend: false, xaxis: { gridcolor: 'rgba(255,255,255,0.03)' },
            yaxis: { gridcolor: 'rgba(255,255,255,0.03)', title: 'Surface Temp (K)' },
        }, { responsive: true, displayModeBar: false });
    } else if (surfaceEl) {
        surfaceEl.innerHTML = '<div class="empty-state" style="padding:24px;">No thermal data available for surface analysis</div>';
    }
}

// ─── SEARCH ──────────────────────────────────────────
async function searchPlace() {
    const query = document.getElementById('input-place').value.trim();
    if (!query) return;
    setStatus('Searching...');
    const result = await apiGet('/api/geocode?q=' + encodeURIComponent(query));
    if (result?.results?.length > 0) {
        const place = result.results[0];
        setLocation(place.lat, place.lon);
        if (_map) _map.setView([place.lat, place.lon], 13);
        document.querySelector('[data-tab="map"]')?.click();
        setStatus(`Found: ${place.name || query}`, 'success');
    } else {
        setStatus('Place not found', 'error');
    }
}

// ─── SITE INTELLIGENCE ───────────────────────────────
async function loadNDVIChange() {
    const loc = getLocationData();
    const el = document.getElementById('ndvi-change-content');
    if (el) el.innerHTML = '<div class="empty-state">Loading NDVI change data...</div>';
    const result = await apiGet(`/api/site/ndvi-change?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const p1 = result.period1_mean ?? result.period1?.mean ?? '--';
            const p2 = result.period2_mean ?? result.period2?.mean ?? '--';
            const change = result.change ?? result.change_pct ?? '--';
            el.innerHTML = `
                <div class="metric-row">
                    <div class="metric"><span class="metric-value">${typeof p1 === 'number' ? p1.toFixed(3) : p1}</span><span class="metric-label">Period 1 NDVI</span></div>
                    <div class="metric"><span class="metric-value">${typeof p2 === 'number' ? p2.toFixed(3) : p2}</span><span class="metric-label">Period 2 NDVI</span></div>
                    <div class="metric"><span class="metric-value" style="color:${change > 0 ? '#4caf50' : '#ff4444'}">${typeof change === 'number' ? change.toFixed(3) : change}</span><span class="metric-label">Change</span></div>
                </div>
            `;
        }
    }
}

async function loadElevationProfile() {
    const loc = getLocationData();
    const direction = document.getElementById('elev-direction')?.value || 'E-W';
    const el = document.getElementById('elev-profile-chart');
    if (el) el.innerHTML = '<div class="empty-state">Scanning elevation...</div>';
    const result = await apiGet(`/api/site/elevation-profile?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&direction=${direction}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const profile = result.profile || result.elevations || [];
            const distances = result.distances || profile.map((_, i) => i);
            Plotly.newPlot(el, [{
                x: distances, y: profile, name: 'Elevation',
                line: { color: '#c8a87c', width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(200,168,124,0.1)',
            }], {
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#4a5a6a', size: 10 }, margin: { t: 20, r: 40, b: 30, l: 50 },
                xaxis: { title: 'Distance (m)', gridcolor: 'rgba(255,255,255,0.03)' },
                yaxis: { title: 'Elevation (m)', gridcolor: 'rgba(255,255,255,0.03)' },
            }, { responsive: true, displayModeBar: false });
        }
    }
}

async function loadWaterProximity() {
    const loc = getLocationData();
    const el = document.getElementById('water-content');
    if (el) el.innerHTML = '<div class="empty-state">Scanning water sources...</div>';
    const result = await apiGet(`/api/site/water?lat=${loc.lat}&lon=${loc.lon}&radius_m=2000`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const sources = result.water_sources || result.features || [];
            if (sources.length === 0) {
                el.innerHTML = '<div class="empty-state">No water sources found within 2km</div>';
            } else {
                el.innerHTML = sources.map(w => `<div class="finding-card info"><strong>${w.name || w.tags?.name || 'Water source'}</strong> — ${w.distance_m ? w.distance_m.toFixed(0) + 'm away' : ''}<br>${w.type || w.tags?.waterway || ''}</div>`).join('');
            }
        }
    }
}

async function loadGeology() {
    const loc = getLocationData();
    const el = document.getElementById('geology-content');
    if (el) el.innerHTML = '<div class="empty-state">Loading geology data...</div>';
    const result = await apiGet(`/api/site/geology?lat=${loc.lat}&lon=${loc.lon}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            let html = '';
            if (result.lithology) html += `<div class="finding-card info"><strong>LITHOLOGY</strong><br>${JSON.stringify(result.lithology)}</div>`;
            if (result.bedrock) html += `<div class="finding-card info"><strong>BEDROCK</strong><br>${JSON.stringify(result.bedrock)}</div>`;
            if (result.soil) html += `<div class="finding-card info"><strong>SOIL TYPE</strong><br>${JSON.stringify(result.soil)}</div>`;
            el.innerHTML = html || `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
        }
    }
}

async function loadNearbyPlaces() {
    const loc = getLocationData();
    const el = document.getElementById('places-content');
    if (el) el.innerHTML = '<div class="empty-state">Searching nearby places...</div>';
    const result = await apiGet(`/api/site/places?lat=${loc.lat}&lon=${loc.lon}&radius_km=50`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const places = result.places || result.features || [];
            if (places.length === 0) {
                el.innerHTML = '<div class="empty-state">No nearby places found</div>';
            } else {
                el.innerHTML = places.slice(0, 15).map(p => `<div class="finding-card info"><strong>${p.name || p.tags?.name || 'Unknown'}</strong> — ${p.type || p.tags?.place || ''}<br>${p.distance_km ? p.distance_km.toFixed(1) + ' km' : ''}</div>`).join('');
            }
        }
    }
}

// ─── SIGNALS ─────────────────────────────────────────
async function loadMagneticField() {
    const loc = getLocationData();
    const el = document.getElementById('spectrum-chart');
    if (el) el.innerHTML = '<div class="empty-state">Loading magnetic field data...</div>';
    const result = await apiGet(`/api/signal/magnetic-gradient?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const profile = result.profile || [];
            const distances = profile.map((p, i) => i * (result.radius_m || 500) / Math.max(profile.length - 1, 1));
            const values = profile.map(p => p.total_nT ?? p.nT ?? p);
            Plotly.newPlot(el, [{
                x: distances, y: values, name: 'Magnetic Field',
                line: { color: '#7b68ee', width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(123,104,238,0.1)',
            }], {
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#4a5a6a', size: 10 }, margin: { t: 20, r: 40, b: 30, l: 50 },
                xaxis: { title: 'Distance (m)', gridcolor: 'rgba(255,255,255,0.03)' },
                yaxis: { title: 'nT', gridcolor: 'rgba(255,255,255,0.03)' },
            }, { responsive: true, displayModeBar: false });
        }
    }
}

async function loadSARBackscatter() {
    const loc = getLocationData();
    const el = document.getElementById('em-field-chart');
    if (el) el.innerHTML = '<div class="empty-state">Loading SAR data...</div>';
    const result = await apiGet(`/api/sar/backscatter?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const vv = result.vv || result.timeseries?.map(t => t.vv) || [];
            const vh = result.vh || result.timeseries?.map(t => t.vh) || [];
            const dates = result.dates || result.timeseries?.map(t => t.date) || vv.map((_, i) => i);
            const traces = [];
            if (vv.length) traces.push({ x: dates, y: vv, name: 'VV', line: { color: '#00f0ff', width: 2 } });
            if (vh.length) traces.push({ x: dates, y: vh, name: 'VH', line: { color: '#ff6b4a', width: 2 } });
            Plotly.newPlot(el, traces, {
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#4a5a6a', size: 10 }, margin: { t: 20, r: 40, b: 30, l: 50 },
                showlegend: traces.length > 1,
                xaxis: { gridcolor: 'rgba(255,255,255,0.03)' },
                yaxis: { title: 'dB', gridcolor: 'rgba(255,255,255,0.03)' },
            }, { responsive: true, displayModeBar: false });
        }
    }
}

async function loadRadioData() {
    const loc = getLocationData();
    const el = document.getElementById('radio-chart');
    if (el) el.innerHTML = '<div class="empty-state">Loading solar radiation data...</div>';
    const result = await apiGet(`/api/data/radio-astronomy?lat=${loc.lat}&lon=${loc.lon}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const irradiance = result.irradiance || result.solar_radiation || result.daily || [];
            const dates = result.dates || irradiance.map((_, i) => i);
            Plotly.newPlot(el, [{
                x: dates, y: irradiance, name: 'Solar Irradiance',
                line: { color: '#ffa726', width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(255,167,38,0.1)',
            }], {
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#4a5a6a', size: 10 }, margin: { t: 20, r: 40, b: 30, l: 50 },
                xaxis: { gridcolor: 'rgba(255,255,255,0.03)' },
                yaxis: { title: 'W/m²', gridcolor: 'rgba(255,255,255,0.03)' },
            }, { responsive: true, displayModeBar: false });
        }
    }
}

// ─── TERRAIN 3D ──────────────────────────────────────
async function generateTerrain() {
    const loc = getLocationData();
    const el = document.getElementById('terrain-3d');
    const info = document.getElementById('terrain-info');
    if (info) info.innerHTML = '<div style="font-size:11px;color:#666;">Generating terrain model...</div>';

    const result = await fetch(API + `/api/ai/terrain?lat=${loc.lat}&lon=${loc.lon}&grid_size=20`, { method: 'POST' }).then(r => r.json());
    if (result?.error) {
        if (info) info.innerHTML = `<div style="font-size:11px;color:#ff4444;">${result.error}</div>`;
        return;
    }

    const elevation = result.elevation || result.grid || [];
    if (!elevation.length || !elevation[0]?.length) {
        if (info) info.innerHTML = '<div style="font-size:11px;color:#ff4444;">No elevation data</div>';
        return;
    }

    el.innerHTML = '';
    const width = el.clientWidth || 600;
    const height = el.clientHeight || 400;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x010103);
    scene.fog = new THREE.FogExp2(0x010103, 0.008);

    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    camera.position.set(0, 40, 60);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);

    const rows = elevation.length;
    const cols = elevation[0].length;
    const geometry = new THREE.PlaneGeometry(60, 60, cols - 1, rows - 1);
    const positions = geometry.attributes.position.array;

    let minElev = Infinity, maxElev = -Infinity;
    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const val = elevation[r][c] || 0;
            if (val < minElev) minElev = val;
            if (val > maxElev) maxElev = val;
        }
    }

    for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
            const idx = r * cols + c;
            const val = elevation[r][c] || 0;
            const normalized = maxElev > minElev ? (val - minElev) / (maxElev - minElev) : 0;
            positions[idx * 3 + 2] = normalized * 15;
        }
    }

    geometry.computeVertexNormals();
    const material = new THREE.MeshPhongMaterial({
        color: 0x1a3a2a, wireframe: false, flatShading: true,
        side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 2;
    scene.add(mesh);

    const wireGeo = geometry.clone();
    const wireMat = new THREE.MeshBasicMaterial({ color: 0xc8a87c, wireframe: true, transparent: true, opacity: 0.15 });
    const wireMesh = new THREE.Mesh(wireGeo, wireMat);
    wireMesh.rotation.x = -Math.PI / 2;
    scene.add(wireMesh);

    const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xc8a87c, 0.8);
    dirLight.position.set(20, 40, 20);
    scene.add(dirLight);
    const pointLight = new THREE.PointLight(0x00f0ff, 0.4, 100);
    pointLight.position.set(-10, 30, -10);
    scene.add(pointLight);

    const anomalies = result.anomalies || [];
    anomalies.forEach(a => {
        const markerGeo = new THREE.SphereGeometry(0.8, 8, 8);
        const markerMat = new THREE.MeshBasicMaterial({ color: 0xff4444 });
        const marker = new THREE.Mesh(markerGeo, markerMat);
        const row = a.row ?? Math.floor(rows / 2);
        const col = a.col ?? Math.floor(cols / 2);
        marker.position.set(
            (col / cols - 0.5) * 60,
            ((elevation[row]?.[col] || 0) - minElev) / (maxElev - minElev || 1) * 15 + 2,
            (row / rows - 0.5) * 60
        );
        scene.add(marker);
    });

    let angle = 0;
    function animate() {
        requestAnimationFrame(animate);
        angle += 0.003;
        camera.position.x = Math.sin(angle) * 50;
        camera.position.z = Math.cos(angle) * 50;
        camera.lookAt(0, 0, 0);
        renderer.render(scene, camera);
    }
    animate();

    if (info) {
        info.innerHTML = `
            <div style="font-size:11px;color:#666;line-height:1.8;">
                Grid: ${cols}×${rows}<br>
                Elevation: ${minElev.toFixed(0)}m — ${maxElev.toFixed(0)}m<br>
                Anomalies: ${anomalies.length}
            </div>
        `;
    }
}

// ─── AI ANALYST ──────────────────────────────────────
async function runGeminiAnalysis() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Running AI analysis...';
    const result = await apiPost('/api/gemini/analyze', loc);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        return;
    }
    document.querySelector('[data-tab="ai"]')?.click();
    const ai = result?.ai_analysis || {};
    const scan = result?.scan || {};
    const score = scan.summary?.archaeological_potential || 0;
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
    if (status) status.innerHTML = 'Analysis complete';
}

async function runGeminiReport() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Generating field report...';
    const place = document.getElementById('input-place')?.value || '';
    const result = await apiPost(`/api/gemini/report?location_name=${encodeURIComponent(place)}`, loc);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        return;
    }
    const el = document.getElementById('ai-result');
    if (el) {
        el.innerHTML = `<div style="padding:12px;font-size:13px;line-height:1.7;"><h3 style="color:#c8a87c;margin-bottom:12px;">Field Report</h3>${formatMarkdown(result?.report || result?.text || JSON.stringify(result))}</div>`;
    }
    if (status) status.innerHTML = 'Report generated';
}

async function loadHistoricalContext() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Loading historical context...';
    const place = document.getElementById('input-place')?.value || '';
    const result = await apiGet(`/api/gemini/history?lat=${loc.lat}&lon=${loc.lon}&name=${encodeURIComponent(place)}`);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        return;
    }
    const el = document.getElementById('ai-result');
    if (el) {
        el.innerHTML = `<div style="padding:12px;font-size:13px;line-height:1.7;"><h3 style="color:#c8a87c;margin-bottom:12px;">Historical Context</h3>${formatMarkdown(result?.context || result?.text || result?.timeline || JSON.stringify(result))}</div>`;
    }
    if (status) status.innerHTML = 'Context loaded';
}

async function runInvestigationPlan() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Creating investigation plan...';
    const result = await apiPost('/api/gemini/investigate', loc);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        return;
    }
    const el = document.getElementById('ai-result');
    if (el) {
        el.innerHTML = `<div style="padding:12px;font-size:13px;line-height:1.7;"><h3 style="color:#c8a87c;margin-bottom:12px;">Investigation Plan</h3>${formatMarkdown(result?.plan || result?.text || JSON.stringify(result))}</div>`;
    }
    if (status) status.innerHTML = 'Plan ready';
}

async function sendChat() {
    const input = document.getElementById('chat-input');
    const msg = input?.value?.trim();
    if (!msg) return;
    input.value = '';

    const messagesEl = document.getElementById('chat-messages');
    messagesEl.innerHTML += `<div style="margin-bottom:8px;padding:8px 12px;background:rgba(200,168,124,0.08);border-left:2px solid #c8a87c;font-size:12px;">${msg}</div>`;
    messagesEl.innerHTML += `<div id="chat-typing" style="margin-bottom:8px;padding:8px 12px;color:#666;font-size:12px;font-style:italic;">Thinking...</div>`;
    messagesEl.scrollTop = messagesEl.scrollHeight;

    const loc = getLocationData();
    const result = await fetch(API + '/api/gemini/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: msg,
            session_id: _chatSessionId,
            scan_index: getLatestScanIndex(),
        }),
    }).then(r => r.json()).catch(() => null);

    const typing = document.getElementById('chat-typing');
    if (typing) typing.remove();

    if (result?.error) {
        messagesEl.innerHTML += `<div style="margin-bottom:8px;padding:8px 12px;background:rgba(255,68,68,0.08);border-left:2px solid #ff4444;font-size:12px;color:#ff4444;">${result.error}</div>`;
    } else {
        const reply = result?.response || result?.reply || result?.text || 'No response';
        messagesEl.innerHTML += `<div style="margin-bottom:8px;padding:8px 12px;background:rgba(0,240,255,0.05);border-left:2px solid #00f0ff;font-size:12px;line-height:1.6;">${formatMarkdown(reply)}</div>`;
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ─── EXPORTS ─────────────────────────────────────────
function exportReport() {
    const loc = getLocationData();
    window.open(API + `/api/export/report?lat=${loc.lat}&lon=${loc.lon}`, '_blank');
}

function exportJSON() {
    const loc = getLocationData();
    window.open(API + `/api/export/json?lat=${loc.lat}&lon=${loc.lon}`, '_blank');
}

function exportCSV() {
    const loc = getLocationData();
    window.open(API + `/api/export/csv?lat=${loc.lat}&lon=${loc.lon}`, '_blank');
}

// ─── HISTORY ─────────────────────────────────────────
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
        _lastScanData = result;
        _lastScanData._scanIndex = index;
        document.querySelector('[data-tab="analysis"]')?.click();
        displayFullScanResults(result);
    }
}

function showNoScanMessage() {
    const els = ['summary-content', 'anomalies-content', 'structural-content', 'env-content', 'webarchive-content', 'archdb-content', 'weather-content', 'maps-content'];
    els.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="empty-state">Run a scan from the Map tab to analyze a location.</div>';
    });
}

function loadLatestScan() {
    if (!document.getElementById('tab-analysis')?.classList.contains('active')) return;
    const status = document.getElementById('scan-status') || document.getElementById('ai-status');
    if (status) status.innerHTML = 'Loading latest scan...';
    apiGet('/api/history').then(result => {
        if (!result?.scans?.length) { showNoScanMessage(); return; }
        const latest = result.scans[result.scans.length - 1];
        if (latest?.id != null) {
            viewHistoryScan(latest.id);
        } else {
            showNoScanMessage();
        }
    }).catch(() => { if (status) status.innerHTML = 'Error loading scan'; });
}

// ─── INIT ────────────────────────────────────────────
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
        if (btn.dataset.tab === 'analysis') loadLatestScan();
        if (btn.dataset.tab === 'history') loadHistory();
    });
});
