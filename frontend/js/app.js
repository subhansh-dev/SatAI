const API = '';
let _map, _marker, _scanCircle;
let _lastScanData = null;
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
function setBtnLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
        btn._origText = btn.innerHTML;
        btn.classList.add('loading');
        btn.innerHTML = '<span style="display:inline-flex;align-items:center;gap:6px;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation:spin 0.8s linear infinite;"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>SCANNING...</span>';
        btn.style.justifyContent = 'center';
    } else {
        btn.classList.remove('loading');
        btn.innerHTML = btn._origText || btn.innerHTML;
    }
}

async function runFullScan(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const result = await apiGet(`/api/full-scan?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}`);
    if (result) {
        _lastScanData = result;
        document.querySelector('[data-tab="analysis"]').click();
        displayFullScanResults(result);
    }
    setBtnLoading(btn, false);
}

async function runMegaScan(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const place = prompt('Place name (optional):') || '';
    const result = await apiGet(`/api/mega-scan?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}&place_name=${encodeURIComponent(place)}`);
    if (result) {
        _lastScanData = result;
        document.querySelector('[data-tab="analysis"]')?.click();
        displayFullScanResults(result);
    }
    setBtnLoading(btn, false);
}

async function runSatelliteAnalysis(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const result = await apiPost('/api/satellite/timeseries', loc);
    if (result) {
        _lastScanData = { satellite: result, ...(result.anomalies ? { anomalies: result.anomalies } : {}), ...(result.structural_analysis ? { structural_analysis: result.structural_analysis } : {}) };
        document.querySelector('[data-tab="analysis"]')?.click();
        displayFullScanResults(_lastScanData);
    }
    setBtnLoading(btn, false);
}

async function runAnomalyDetection(btn) {
    setBtnLoading(btn, true);
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
    setBtnLoading(btn, false);
}

async function runEnvironmentalScan(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const result = await apiGet(`/api/env/full?lat=${loc.lat}&lon=${loc.lon}`);
    if (result) {
        document.querySelector('[data-tab="analysis"]')?.click();
        displayEnvironmental(result);
    }
    setBtnLoading(btn, false);
}

async function runHistoricalWeb(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const place = document.getElementById('input-place')?.value || '';
    const result = await apiGet(`/api/web/full?lat=${loc.lat}&lon=${loc.lon}&place_name=${encodeURIComponent(place)}`);
    if (result) {
        document.querySelector('[data-tab="analysis"]')?.click();
        displayWebArchives(result);
    }
    setBtnLoading(btn, false);
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
        : anomalies.map((a, i) => `<div class="finding-card warning"><strong>${(a.type || 'unknown').replace(/_/g, ' ').toUpperCase()}</strong> — ${a.date || ''}<br>${a.interpretation || a.description || ''}<br><button class="btn-inline" onclick="explainAnomaly(${i})" style="margin-top:6px;">EXPLAIN</button></div>`).join('');
    document.getElementById('anomalies-content').innerHTML = anomalyHTML;

    const structural = data.structural_analysis || {};
    const structScore = structural.structural_probability || 0;
    document.getElementById('structural-content').innerHTML = `
        <div class="metric-row">
            <div class="metric"><span class="metric-value">${structScore.toFixed(0)}%</span><span class="metric-label">Structure Probability</span></div>
        </div>
    `;

loadEnvPanel(data);
    loadWebArchivePanel(data);
    loadArchDBPanel(data);
    loadWeatherPanel(data);
    loadHistoricalMapsPanel(data);
    loadSignalsPanels(data);
}

function loadEnvPanel(data) {
    const env = data.environmental || {};
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
    if (env.water_table) {
        html += `<div class="finding-card info"><strong>WATER TABLE</strong> — ${env.water_table.water_table || env.water_table.estimate || 'estimated'}</div>`;
    }
    const el = document.getElementById('env-content');
    if (el) el.innerHTML = html || '<div class="empty-state">No environmental data</div>';
}

function loadWebArchivePanel(data) {
    const web = data.historical_web || {};
    let html = '';
    if (web.wayback?.count) {
        html += `<div class="finding-card info"><strong>WAYBACK MACHINE</strong> — ${web.wayback.count} archives</div>`;
        (web.wayback.results || []).slice(0, 5).forEach(r => {
            html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;"><a href="${r.url || r.archived || r}" target="_blank" style="color:var(--accent)">${r.url || r.archived || r}</a></div>`;
        });
    }
    if (web.osm?.historic_features?.length) {
        html += `<div class="finding-card info"><strong>OSM HISTORIC</strong> — ${web.osm.historic_features.length} features</div>`;
    }
    document.getElementById('webarchive-content').innerHTML = html || '<div class="empty-state">No web archives found</div>';
}

function loadArchDBPanel(data) {
    const arch = data.archaeological_db || {};
    let html = '';
    if (arch.pleiades?.places) {
        html += `<div class="finding-card info"><strong>ANCIENT SITES (Pleiades)</strong> — ${arch.pleiades.count || arch.pleiades.places.length} nearby</div>`;
        arch.pleiades.places.slice(0, 5).forEach(p => {
            html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;">${p.title} (${p.distance_km}km)</div>`;
        });
    }
    if (arch.wikidata?.sites) {
        html += `<div class="finding-card info"><strong>ARCHAEOLOGICAL SITES (Wikidata)</strong> — ${arch.wikidata.count || arch.wikidata.sites.length} nearby</div>`;
        arch.wikidata.sites.slice(0, 5).forEach(s => {
            html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;">${s.name} (${s.distance_km}km)</div>`;
        });
    }
    if (arch.gbif?.species) {
        html += `<div class="finding-card info"><strong>SPECIES (GBIF)</strong> — ${arch.gbif.count || arch.gbif.species.length} observations</div>`;
    }
    if (arch.magnetic?.total_intensity_nt) {
        html += `<div class="finding-card info"><strong>MAGNETIC FIELD</strong> — ${arch.magnetic.total_intensity_nt.toFixed(0)} nT</div>`;
    }
    if (arch.nighttime_lights?.granules) {
        html += `<div class="finding-card info"><strong>NIGHTTIME LIGHTS</strong> — ${arch.nighttime_lights.granules} VIIRS granules</div>`;
    }
    if (arch.lidar?.available !== undefined) {
        html += `<div class="finding-card info"><strong>LIDAR/SRTM</strong> — ${arch.lidar.available ? 'Available' : 'Not available'} ${arch.lidar.resolution ? '(' + arch.lidar.resolution + ')' : ''}</div>`;
    }
    if (arch.climate?.temperature !== undefined) {
        html += `<div class="finding-card info"><strong>CLIMATE</strong> — ${arch.climate.temperature}°C avg, ${arch.climate.precipitation || '?'}mm precip</div>`;
        if (arch.climate.interpretation) {
            arch.climate.interpretation.forEach(i => { html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;">${i}</div>`; });
        }
    }
    if (arch.land_cover?.description) {
        html += `<div class="finding-card info"><strong>LAND COVER</strong> — ${arch.land_cover.description}</div>`;
    }
    if (arch.suitability?.score !== undefined) {
        const sc = arch.suitability.score;
        html += `<div class="finding-card info"><strong>SUITABILITY</strong> — Score: ${sc}/100 (${sc > 70 ? 'High' : sc > 40 ? 'Moderate' : 'Low'} potential)</div>`;
        if (arch.suitability.factors) {
            Object.entries(arch.suitability.factors).forEach(([k, v]) => {
                html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;">${k}: ${typeof v === 'number' ? v.toFixed(1) : v}</div>`;
            });
        }
    }
    document.getElementById('archdb-content').innerHTML = html || '<div class="empty-state">Run Full Spectrum Scan for archaeological data</div>';
}

function loadWeatherPanel(data) {
    const weather = data.space_weather || {};
    if (weather.interpretation) {
        document.getElementById('weather-content').innerHTML = `<div class="finding-card info">${weather.interpretation.map(i => `<div>${i}</div>`).join('')}</div>`;
    } else if (weather.data?.length) {
        const sw = weather.data[0];
        document.getElementById('weather-content').innerHTML = `<div class="finding-card info">Solar wind: ${sw.speed} km/s, Density: ${sw.density} p/cm³</div>`;
    }
}

function loadHistoricalMapsPanel(data) {
    const maps = data.historical_maps || [];
    if (maps.length > 0) {
        document.getElementById('maps-content').innerHTML = maps.map(m => `<div class="finding-card info"><strong>${m.name || m.source || 'Map'}</strong><br><a href="${m.url || m.link || '#'}" target="_blank" style="color:var(--accent)">${m.url || m.link || 'View'}</a></div>`).join('');
    }
}

function displayEnvironmental(data) {
    loadEnvPanel(data);
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
            const p1 = result.period1?.ndvi ?? '--';
            const p2 = result.period2?.ndvi ?? '--';
            const change = result.pct_change ?? result.change ?? '--';
            const interp = (result.interpretation || []).join(' ');
            el.innerHTML = `
                <div class="metric-row">
                    <div class="metric"><span class="metric-value">${typeof p1 === 'number' ? p1.toFixed(4) : p1}</span><span class="metric-label">Period 1 NDVI</span></div>
                    <div class="metric"><span class="metric-value">${typeof p2 === 'number' ? p2.toFixed(4) : p2}</span><span class="metric-label">Period 2 NDVI</span></div>
                    <div class="metric"><span class="metric-value" style="color:${change > 0 ? '#4caf50' : '#ff4444'}">${typeof change === 'number' ? change.toFixed(1) + '%' : change}</span><span class="metric-label">Change</span></div>
                </div>
                ${interp ? `<div class="finding-card info">${interp}</div>` : ''}
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
            const sources = result.features || [];
            const nearest = result.nearest_water_m;
            const interp = (result.interpretation || []).join(' ');
            let html = '';
            if (nearest != null) {
                html += `<div class="metric-row"><div class="metric"><span class="metric-value">${nearest.toFixed(0)}m</span><span class="metric-label">Nearest Water</span></div></div>`;
            }
            if (sources.length === 0) {
                html += '<div class="empty-state">No water sources found within 2km</div>';
            } else {
                html += sources.slice(0, 8).map(w => `<div class="finding-card info"><strong>${w.name || 'Water source'}</strong> — ${w.distance_m ? w.distance_m.toFixed(0) + 'm away' : ''}<br>${w.type || ''}</div>`).join('');
            }
            if (interp) html += `<div class="finding-card info">${interp}</div>`;
            el.innerHTML = html;
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
            const interp = (result.interpretation || []).join(' ');
            const units = result.units || [];
            const soil = result.soil_properties || {};
            if (units.length) {
                html += '<div class="finding-card info"><strong>GEOLOGICAL UNITS</strong><br>' + units.map(u => `${u.name} (${u.age})`).join('<br>') + '</div>';
            }
            if (soil && Object.keys(soil).length) {
                html += '<div class="finding-card info"><strong>SOIL PROPERTIES</strong><br>' + Object.entries(soil).map(([k, v]) => `${k}: ${v}`).join(', ') + '</div>';
            }
            if (interp) html += `<div class="finding-card info">${interp}</div>`;
            if (!html) html = `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
            el.innerHTML = html;
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
function loadSignalsPanels(data) {
    loadMagneticField();
    loadSARBackscatter();
    loadRadioData();
}

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
            const distances = profile.map((p, i) => i * (loc.radius_m || 500) / Math.max(profile.length - 1, 1));
            const values = profile.map(p => p.total_intensity_nt ?? p.total_nT ?? p);
            const gradient = result.gradient_nt || 0;
            const mean = result.mean_nt || 0;
            const interp = (result.interpretation || []).join(' ');
            Plotly.newPlot(el, [{
                x: distances, y: values, name: 'Magnetic Field',
                line: { color: '#7b68ee', width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(123,104,238,0.1)',
            }], {
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#4a5a6a', size: 10 }, margin: { t: 30, r: 40, b: 40, l: 60 },
                xaxis: { title: 'Distance (m)', gridcolor: 'rgba(255,255,255,0.03)' },
                yaxis: { title: 'nT', gridcolor: 'rgba(255,255,255,0.03)' },
                annotations: [{
                    text: `Gradient: ${gradient} nT | Mean: ${mean} nT`,
                    xref: 'paper', yref: 'paper', x: 0.02, y: 0.98,
                    showarrow: false, font: { size: 10, color: '#c8a87c', family: 'JetBrains Mono' },
                    bgcolor: 'rgba(0,0,0,0.6)', borderpad: 4,
                }],
            }, { responsive: true, displayModeBar: false });
            if (interp) {
                el.insertAdjacentHTML('beforebegin', `<div class="signal-interp">${interp}</div>`);
            }
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
            const ts = result.timeseries || [];
            const vv = ts.map(t => t.vv);
            const vh = ts.map(t => t.vh);
            const dates = ts.map(t => t.date);
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
            const sr = result.solar_radiation || {};
            const values = sr.allsky_sw_dn_wm2 || [];
            const dates = sr.dates || [];
            const mean = sr.mean_wm2 || 0;
            const interp = (result.interpretation || []).join(' ');
            Plotly.newPlot(el, [{
                x: dates, y: values, name: 'Solar Irradiance',
                line: { color: '#ffa726', width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(255,167,38,0.1)',
            }], {
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#4a5a6a', size: 10 }, margin: { t: 30, r: 40, b: 40, l: 60 },
                xaxis: { gridcolor: 'rgba(255,255,255,0.03)' },
                yaxis: { title: 'W/m²', gridcolor: 'rgba(255,255,255,0.03)' },
                annotations: [{
                    text: `Mean: ${mean} W/m²`,
                    xref: 'paper', yref: 'paper', x: 0.02, y: 0.98,
                    showarrow: false, font: { size: 10, color: '#c8a87c', family: 'JetBrains Mono' },
                    bgcolor: 'rgba(0,0,0,0.6)', borderpad: 4,
                }],
            }, { responsive: true, displayModeBar: false });
            if (interp) {
                el.insertAdjacentHTML('beforebegin', `<div class="signal-interp">${interp}</div>`);
            }
        }
    }
}

// ─── SPECTRAL INDICES ────────────────────────────────
async function loadSpectralIndices() {
    const loc = getLocationData();
    const el = document.getElementById('spectral-idx-content');
    if (el) el.innerHTML = '<div class="empty-state">Computing spectral indices...</div>';
    const result = await apiPost('/api/satellite/spectral', loc);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const indices = result.indices || result;
            let html = '';
            const names = { ndvi: 'NDVI (Vegetation)', ndwi: 'NDWI (Water)', ndbi: 'NDBI (Built-up)', savi: 'SAVI', ndmi: 'NDMI (Moisture)', bsi: 'BSI (Bare Soil)' };
            for (const [k, v] of Object.entries(indices)) {
                if (typeof v === 'object' && v !== null) {
                    const mean = v.mean ?? v.value ?? '--';
                    const std = v.std ?? '';
                    const label = names[k] || k.toUpperCase();
                    html += `<div class="metric"><span class="metric-value">${typeof mean === 'number' ? mean.toFixed(4) : mean}</span><span class="metric-label">${label}${std ? ' (±' + (typeof std === 'number' ? std.toFixed(4) : std) + ')' : ''}</span></div>`;
                }
            }
            const interp = result.interpretation || [];
            if (interp.length) {
                html += '<div style="margin-top:8px;">';
                interp.forEach(i => { html += `<div class="finding-card info">${i}</div>`; });
                html += '</div>';
            }
            el.innerHTML = html || `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
        }
    }
}

// ─── TEMPORAL CHANGE ─────────────────────────────────
async function loadTemporalChange() {
    const loc = getLocationData();
    const el = document.getElementById('temporal-change-content');
    if (el) el.innerHTML = '<div class="empty-state">Running temporal analysis...</div>';
    const result = await apiPost('/api/ai/temporal-change', loc);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            let html = '';
            if (result.trend) {
                html += `<div class="metric"><span class="metric-value">${result.trend.direction || 'stable'}</span><span class="metric-label">Trend Direction</span></div>`;
                html += `<div class="metric"><span class="metric-value">${result.trend.slope ? result.trend.slope.toFixed(6) : '--'}</span><span class="metric-label">Slope</span></div>`;
            }
            const cps = result.change_points || [];
            if (cps.length) {
                html += `<div class="finding-card info"><strong>${cps.length} CHANGE POINTS DETECTED</strong></div>`;
                cps.slice(0, 10).forEach(cp => {
                    html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;">Date: ${cp.date || cp.index || 'N/A'} — Magnitude: ${cp.magnitude ?? cp.value ?? '--'}</div>`;
                });
            }
            const interp = result.interpretation || [];
            if (interp.length) {
                html += '<div style="margin-top:8px;">';
                interp.forEach(i => { html += `<div class="finding-card info">${i}</div>`; });
                html += '</div>';
            }
            el.innerHTML = html || `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
        }
    }
}

// ─── LIGHTNING ───────────────────────────────────────
async function loadLightning() {
    const loc = getLocationData();
    const el = document.getElementById('lightning-content');
    if (el) el.innerHTML = '<div class="empty-state">Scanning lightning data...</div>';
    const result = await apiGet(`/api/data/lightning?lat=${loc.lat}&lon=${loc.lon}&radius_km=100`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            let html = `<div class="metric"><span class="metric-value">${result.strike_count || 0}</span><span class="metric-label">Strikes Nearby</span></div>`;
            if (result.sources) {
                html += `<div class="finding-card info"><strong>DATA SOURCES</strong><br>${result.sources.join(', ')}</div>`;
            }
            const interp = result.interpretation || [];
            interp.forEach(i => { html += `<div class="finding-card info">${i}</div>`; });
            el.innerHTML = html || '<div class="empty-state">No lightning data available</div>';
        }
    }
}

// ─── HISTORICAL MAPS STANDALONE ──────────────────────
async function loadHistoricalMapsStandalone() {
    const loc = getLocationData();
    const el = document.getElementById('hist-maps-content');
    if (el) el.innerHTML = '<div class="empty-state">Loading map sources...</div>';
    const result = await apiGet(`/api/data/historical-maps?lat=${loc.lat}&lon=${loc.lon}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const sources = result.available_sources || result.sources || [];
            let html = '';
            if (sources.length) {
                sources.forEach(s => {
                    const name = s.name || s.source || 'Map';
                    const url = s.url || s.link || '#';
                    html += `<div class="finding-card info"><strong>${name}</strong><br><a href="${url}" target="_blank" style="color:var(--accent);font-size:11px;">${url.length > 60 ? url.substring(0, 60) + '...' : url}</a></div>`;
                });
            }
            el.innerHTML = html || `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
        }
    }
}

let _lastSignalSpectral = {};

// ─── FFT SPECTRUM ANALYSIS (real NOAA WMM data) ──────
async function loadSpectrumAnalysis() {
    const loc = getLocationData();
    const el = document.getElementById('spectrum-analysis-chart');
    if (el) el.innerHTML = '<div class="empty-state">Fetching magnetic field transect...</div>';
    const result = await apiGet(`/api/signal/fft?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}`);
    _lastSignalSpectral = result || {};
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const fftFreqs = result.fft?.frequencies || [];
            const fftMags = result.fft?.magnitudes || [];
            const dominant = result.dominant_frequencies || [];
            const patterns = result.patterns || {};
            let traces = [];
            if (fftFreqs.length && fftMags.length) {
                traces.push({ x: fftFreqs, y: fftMags, name: 'Spatial Frequency', line: { color: '#00f0ff', width: 1.5 }, fill: 'tozeroy', fillcolor: 'rgba(0,240,255,0.08)' });
            }
            Plotly.newPlot(el, traces, {
                paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#4a5a6a', size: 10 }, margin: { t: 30, r: 40, b: 40, l: 60 },
                xaxis: { title: 'Spatial Frequency (cycles/m)', gridcolor: 'rgba(255,255,255,0.03)' },
                yaxis: { title: 'Magnitude (nT)', gridcolor: 'rgba(255,255,255,0.03)' },
                annotations: dominant.length ? [{
                    text: `Dominant: ${dominant.map(d => d.period_m + 'm period').join(', ')}`,
                    xref: 'paper', yref: 'paper', x: 0.02, y: 0.98,
                    showarrow: false, font: { size: 10, color: '#c8a87c', family: 'JetBrains Mono' },
                    bgcolor: 'rgba(0,0,0,0.6)', borderpad: 4,
                }] : [],
            }, { responsive: true, displayModeBar: false });
            let extra = '';
            if (result.mean_intensity_nt) extra += `<div class="finding-card info"><strong>Mean Intensity:</strong> ${result.mean_intensity_nt} nT</div>`;
            if (result.gradient_nt) extra += `<div class="finding-card info"><strong>Gradient:</strong> ${result.gradient_nt} nT</div>`;
            if (dominant.length) {
                dominant.forEach(d => {
                    extra += `<div class="finding-card info"><strong>Peak:</strong> ${d.period_m}m period (freq ${d.frequency} cycles/m, magnitude ${d.magnitude})</div>`;
                });
            }
            if (result.interpretation) {
                result.interpretation.forEach(i => { extra += `<div class="finding-card info">${i}</div>`; });
            }
            if (extra) el.insertAdjacentHTML('afterend', extra);
        }
    }
}

// ─── EM FIELD MAP (real NOAA WMM magnetic grid) ──────
async function loadEMFieldMap() {
    const loc = getLocationData();
    const el = document.getElementById('em-field-map-chart');
    if (el) el.innerHTML = '<div class="empty-state">Scanning magnetic field grid...</div>';
    const result = await apiPost(`/api/signal/em-field?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&grid_res=10`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const grid = result.field_values || [];
            if (grid.length) {
                Plotly.newPlot(el, [{
                    z: grid, type: 'heatmap', colorscale: [[0, '#010103'], [0.3, '#1a3a5a'], [0.6, '#00f0ff'], [1, '#c8a87c']],
                    colorbar: { title: 'nT', titlefont: { color: '#4a5a6a', size: 10 }, tickfont: { color: '#4a5a6a', size: 10 } },
                }], {
                    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
                    font: { color: '#4a5a6a', size: 10 }, margin: { t: 30, r: 60, b: 40, l: 60 },
                    xaxis: { gridcolor: 'rgba(255,255,255,0.03)', title: 'Longitude Grid' },
                    yaxis: { gridcolor: 'rgba(255,255,255,0.03)', title: 'Latitude Grid' },
                    annotations: [{
                        text: `Hotspots: ${result.hotspot_count || 0} | Range: ${result.min_intensity || 0}-${result.max_intensity || 0} nT`,
                        xref: 'paper', yref: 'paper', x: 0.02, y: 0.98,
                        showarrow: false, font: { size: 10, color: '#c8a87c', family: 'JetBrains Mono' },
                        bgcolor: 'rgba(0,0,0,0.6)', borderpad: 4,
                    }],
                }, { responsive: true, displayModeBar: false });
            }
            let extra = '';
            if (result.hotspots?.length) {
                result.hotspots.forEach(h => {
                    extra += `<div class="finding-card info"><strong>HOTSPOT:</strong> ${h.intensity_nt} nT at (${h.lat.toFixed(4)}, ${h.lon.toFixed(4)})</div>`;
                });
            }
            if (result.interpretation) {
                result.interpretation.forEach(i => { extra += `<div class="finding-card info">${i}</div>`; });
            }
            if (extra) el.insertAdjacentHTML('afterend', extra);
        }
    }
}

// ─── ANOMALY EXPLAIN ─────────────────────────────────
async function explainAnomaly(index) {
    if (!_lastScanData?.anomalies?.[index]) return;
    const anomaly = _lastScanData.anomalies[index];
    const loc = getLocationData();
    const result = await apiPost('/api/gemini/explain-anomaly', { anomaly, context: { scan_target: { lat: loc.lat, lon: loc.lon } } });
    if (result?.error) {
        document.getElementById('anomalies-content').insertAdjacentHTML('beforeend', `<div class="finding-card warning" style="margin-top:8px;">${result.error}</div>`);
    } else {
        const html = `<div class="finding-card info" style="margin-top:8px;border-left-color:#00f0ff;">
            <strong>AI EXPLANATION</strong><br>
            ${formatMarkdown(result?.explanation || result?.text || result?.analysis || JSON.stringify(result))}
        </div>`;
        document.getElementById('anomalies-content').insertAdjacentHTML('beforeend', html);
    }
}

// ─── LIDAR ───────────────────────────────────────────
async function loadLidar() {
    const loc = getLocationData();
    const el = document.getElementById('archdb-content');
    if (el) el.innerHTML += '<div class="finding-card info" style="margin-top:4px;">Loading LIDAR data...</div>';
    const result = await apiGet(`/api/arch/lidar?lat=${loc.lat}&lon=${loc.lon}`);
    if (result) {
        let html = '';
        if (result.available !== undefined) {
            html = `<div class="finding-card info"><strong>LIDAR/SRTM</strong> — ${result.available ? 'Available' : 'Not available'} ${result.resolution ? '(' + result.resolution + ')' : ''}</div>`;
        } else {
            html = `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
        }
        el.insertAdjacentHTML('beforeend', html);
    }
}

// ─── CROSS-REFERENCE ─────────────────────────────────
async function loadCrossref() {
    const loc = getLocationData();
    const el = document.getElementById('archdb-content');
    if (el) el.innerHTML += '<div class="finding-card info" style="margin-top:4px;">Cross-referencing databases...</div>';
    const result = await apiGet(`/api/arch/crossref?lat=${loc.lat}&lon=${loc.lon}&radius_km=50`);
    if (result) {
        let html = '';
        if (result.matches) {
            html = `<div class="finding-card info"><strong>CROSS-REFERENCE</strong> — ${result.matches.length || 0} confirmed matches</div>`;
            (result.matches || []).slice(0, 5).forEach(m => {
                html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;">${m.name || m.title || JSON.stringify(m)}</div>`;
            });
        } else {
            html = `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
        }
        el.insertAdjacentHTML('beforeend', html);
    }
}

// ─── TEMPORAL ARCH ───────────────────────────────────
async function loadTemporalArch() {
    const loc = getLocationData();
    const el = document.getElementById('archdb-content');
    if (el) el.innerHTML += '<div class="finding-card info" style="margin-top:4px;">Loading temporal changes...</div>';
    const result = await apiGet(`/api/arch/temporal?lat=${loc.lat}&lon=${loc.lon}`);
    if (result) {
        let html = `<div class="finding-card info"><strong>TEMPORAL CHANGES</strong></div>`;
        if (result.changes) {
            result.changes.slice(0, 10).forEach(c => {
                html += `<div class="finding-card info" style="margin-left:12px;font-size:11px;">${c.date || c.period || ''} — ${c.description || c.type || JSON.stringify(c)}</div>`;
            });
        } else {
            html += `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
        }
        el.insertAdjacentHTML('beforeend', html);
    }
}

// ─── BATCH SCAN ──────────────────────────────────────
async function runBatchScan() {
    const input = document.getElementById('batch-locations')?.value?.trim();
    const el = document.getElementById('batch-content');
    if (!input) { if (el) el.innerHTML = '<div class="finding-card warning">Enter locations first</div>'; return; }
    if (el) el.innerHTML = '<div class="empty-state">Running batch scan...</div>';
    const lines = input.split('\n').filter(l => l.trim());
    const locations = lines.map(l => {
        const parts = l.split(',').map(s => parseFloat(s.trim()));
        return { lat: parts[0], lon: parts[1], radius_m: parts[2] || 500 };
    });
    const result = await apiPost('/api/arch/batch', locations);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const ranked = result.ranked || result.results || result;
            let html = '';
            if (Array.isArray(ranked)) {
                ranked.sort((a, b) => (b.suitability?.score || b.score || 0) - (a.suitability?.score || a.score || 0));
                ranked.forEach((r, i) => {
                    const score = r.suitability?.score ?? r.score ?? 0;
                    html += `<div class="finding-card info"><strong>#${i + 1}</strong> ${r.lat?.toFixed(4)}, ${r.lon?.toFixed(4)} — Score: ${score}/100</div>`;
                });
            } else {
                html = `<div class="finding-card info"><pre style="white-space:pre-wrap;font-size:11px;">${JSON.stringify(result, null, 2)}</pre></div>`;
            }
            el.innerHTML = html || '<div class="empty-state">No results</div>';
        }
    }
}

// ─── COMPARE SCANS ───────────────────────────────────
async function compareScans() {
    const input = document.getElementById('compare-indices')?.value?.trim();
    const el = document.getElementById('compare-content');
    if (!input) { if (el) el.innerHTML = '<div class="finding-card warning">Enter scan indices</div>'; return; }
    if (el) el.innerHTML = '<div class="empty-state">Comparing scans...</div>';
    const result = await apiGet(`/api/compare?indices=${encodeURIComponent(input)}`);
    if (el && result) {
        if (result.error) {
            el.innerHTML = `<div class="finding-card warning">${result.error}</div>`;
        } else {
            const scans = result.scans || [];
            const best = result.best || {};
            let html = `<div class="metric-row"><div class="metric"><span class="metric-value">${result.count || scans.length}</span><span class="metric-label">Scans Compared</span></div>`;
            html += `<div class="metric"><span class="metric-value">${best.score || 0}%</span><span class="metric-label">Best Score</span></div></div>`;
            scans.forEach(s => {
                const score = s.score || 0;
                const color = score > 70 ? '#c8a87c' : score > 40 ? '#ff8800' : '#4a5a6a';
                html += `<div class="finding-card info"><strong>#${s.index}</strong> ${s.place_name || ''} (${s.lat?.toFixed(4)}, ${s.lon?.toFixed(4)}) — <span style="color:${color}">${score}%</span> | Anomalies: ${s.anomaly_count || 0} | Confidence: ${s.confidence || '?'}</div>`;
            });
            el.innerHTML = html;
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
async function runGeminiAnalysis(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Running AI analysis...';
    const result = await apiPost('/api/gemini/analyze', loc);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        setBtnLoading(btn, false);
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
    setBtnLoading(btn, false);
}

async function runGeminiReport(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Generating field report...';
    const place = document.getElementById('input-place')?.value || '';
    const result = await apiPost(`/api/gemini/report?location_name=${encodeURIComponent(place)}`, loc);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        setBtnLoading(btn, false);
        return;
    }
    const el = document.getElementById('ai-result');
    if (el) {
        el.innerHTML = `<div style="padding:12px;font-size:13px;line-height:1.7;"><h3 style="color:#c8a87c;margin-bottom:12px;">Field Report</h3>${formatMarkdown(result?.report || result?.text || JSON.stringify(result))}</div>`;
    }
    if (status) status.innerHTML = 'Report generated';
    setBtnLoading(btn, false);
}

async function loadHistoricalContext(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Loading historical context...';
    const place = document.getElementById('input-place')?.value || '';
    const result = await apiGet(`/api/gemini/history?lat=${loc.lat}&lon=${loc.lon}&name=${encodeURIComponent(place)}`);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        setBtnLoading(btn, false);
        return;
    }
    const el = document.getElementById('ai-result');
    if (el) {
        el.innerHTML = `<div style="padding:12px;font-size:13px;line-height:1.7;"><h3 style="color:#c8a87c;margin-bottom:12px;">Historical Context</h3>${formatMarkdown(result?.context || result?.text || result?.timeline || JSON.stringify(result))}</div>`;
    }
    if (status) status.innerHTML = 'Context loaded';
    setBtnLoading(btn, false);
}

async function runInvestigationPlan(btn) {
    setBtnLoading(btn, true);
    const loc = getLocationData();
    const status = document.getElementById('ai-status');
    if (status) status.innerHTML = 'Creating investigation plan...';
    const result = await apiPost('/api/gemini/investigate', loc);
    if (result?.error) {
        if (status) status.innerHTML = `<span style="color:#ff4444">${result.error}</span>`;
        setBtnLoading(btn, false);
        return;
    }
    const el = document.getElementById('ai-result');
    if (el) {
        el.innerHTML = `<div style="padding:12px;font-size:13px;line-height:1.7;"><h3 style="color:#c8a87c;margin-bottom:12px;">Investigation Plan</h3>${formatMarkdown(result?.plan || result?.text || JSON.stringify(result))}</div>`;
    }
    if (status) status.innerHTML = 'Plan ready';
    setBtnLoading(btn, false);
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

// ─── AI INTERPRETATION ──────────────────────────────
async function aiInterpretSignal() {
    const el = document.getElementById('spectrum-analysis-chart');
    if (el) el.insertAdjacentHTML('afterend', '<div id="ai-signal-interp" class="finding-card info" style="margin-top:8px;border-left-color:#c8a87c;">AI interpreting signal patterns...</div>');
    const spectral = _lastSignalSpectral || {};
    const result = await apiPost('/api/gemini/interpret-signal', { signal_data: {}, spectral_data: spectral });
    const interpEl = document.getElementById('ai-signal-interp');
    if (result?.error) {
        if (interpEl) interpEl.outerHTML = `<div class="finding-card warning" style="margin-top:8px;">${result.error}</div>`;
    } else {
        const text = result?.interpretation || result?.text || JSON.stringify(result);
        if (interpEl) interpEl.outerHTML = `<div class="finding-card info" style="margin-top:8px;border-left-color:#c8a87c;"><strong>AI SIGNAL INTERPRETATION</strong><br>${formatMarkdown(text)}</div>`;
    }
}

async function aiInterpretEnvironmental() {
    const env = _lastScanData?.environmental || {};
    const el = document.getElementById('env-content');
    if (el) el.insertAdjacentHTML('beforeend', '<div id="ai-env-interp" class="finding-card info" style="margin-top:8px;border-left-color:#c8a87c;">AI interpreting environmental data...</div>');
    const result = await apiPost('/api/gemini/interpret-environmental', env);
    const interpEl = document.getElementById('ai-env-interp');
    if (result?.error) {
        if (interpEl) interpEl.outerHTML = `<div class="finding-card warning" style="margin-top:8px;">${result.error}</div>`;
    } else {
        const text = result?.interpretation || result?.text || JSON.stringify(result);
        if (interpEl) interpEl.outerHTML = `<div class="finding-card info" style="margin-top:8px;border-left-color:#c8a87c;"><strong>AI ENVIRONMENTAL INTERPRETATION</strong><br>${formatMarkdown(text)}</div>`;
    }
}

async function aiSynthesizeCrossref() {
    const arch = _lastScanData?.archaeological_db || {};
    const el = document.getElementById('archdb-content');
    if (el) el.insertAdjacentHTML('beforeend', '<div id="ai-crossref" class="finding-card info" style="margin-top:8px;border-left-color:#c8a87c;">AI cross-referencing databases...</div>');
    const result = await apiPost('/api/gemini/synthesize-crossref', {
        pleiades: arch.pleiades || {},
        wikidata: arch.wikidata || {},
        gbif: arch.gbif || {},
        magnetic: arch.magnetic || {},
        other: { nightlights: arch.nighttime_lights || {}, climate: arch.climate || {}, landcover: arch.land_cover || {} },
    });
    const interpEl = document.getElementById('ai-crossref');
    if (result?.error) {
        if (interpEl) interpEl.outerHTML = `<div class="finding-card warning" style="margin-top:8px;">${result.error}</div>`;
    } else {
        const text = result?.synthesis || result?.text || JSON.stringify(result);
        if (interpEl) interpEl.outerHTML = `<div class="finding-card info" style="margin-top:8px;border-left-color:#c8a87c;"><strong>AI CROSS-REFERENCE SYNTHESIS</strong><br>${formatMarkdown(text)}</div>`;
    }
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
        const latestIdx = result.scans.length - 1;
        viewHistoryScan(latestIdx);
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
        if (btn.dataset.tab === 'signals') {
            loadSignalsPanels(_lastScanData || getLocationData());
            loadSpectrumAnalysis();
            loadEMFieldMap();
        }
    });
});
