const API = '';

(async function initBoot() {
    const boot = document.getElementById('boot');
    const ring = document.getElementById('bootRing');
    const percent = document.getElementById('bootPercent');
    const bootName = document.getElementById('bootName');
    const bootSub = document.getElementById('bootSub');
    const wakeMsg = document.getElementById('boot-wake');
    if (!boot || !ring) return;

    const circumference = 226.2;

    async function pingBackend() {
        try {
            const r = await fetch('/api/health', { method: 'GET' });
            if (r.ok) return true;
        } catch (e) {}
        return false;
    }

    let progress = 0;
    function tickBoot() {
        progress += Math.random() * 3 + 0.5;
        if (progress > 90) progress = 90;
        ring.style.strokeDashoffset = circumference * (1 - progress / 100);
        percent.textContent = Math.floor(progress);
    }

    bootName.classList.add('show');
    setTimeout(() => bootSub.classList.add('show'), 300);

    let awake = false;
    let attempts = 0;
    while (!awake) {
        attempts++;
        tickBoot();
        awake = await pingBackend();
        if (!awake) {
            if (wakeMsg) wakeMsg.style.display = 'block';
            await new Promise(r => setTimeout(r, 2000));
        }
    }

    ring.style.strokeDashoffset = 0;
    percent.textContent = '100';
    if (wakeMsg) wakeMsg.style.display = 'none';
    setTimeout(() => boot.classList.add('done'), 600);
})();

(function initCursor() {
    const dot = document.getElementById('cursorDot');
    const ring = document.getElementById('cursorRing');
    if (!dot || !ring) return;
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

    let mouseX = 0, mouseY = 0;
    let ringX = 0, ringY = 0;

    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;
        dot.style.left = mouseX + 'px';
        dot.style.top = mouseY + 'px';
    });

    function animateRing() {
        ringX += (mouseX - ringX) * 0.15;
        ringY += (mouseY - ringY) * 0.15;
        ring.style.left = ringX + 'px';
        ring.style.top = ringY + 'px';
        requestAnimationFrame(animateRing);
    }
    animateRing();

    // Hover state on interactive elements
    const hoverTargets = 'a, button, .btn-scan, .btn-secondary, .btn-inline, .nav-btn, input, select, .glass-panel';
    document.querySelectorAll(hoverTargets).forEach(el => {
        el.addEventListener('mouseenter', () => ring.classList.add('hover'));
        el.addEventListener('mouseleave', () => ring.classList.remove('hover'));
    });
})();

(function initSpecular() {
    document.addEventListener('mousemove', (e) => {
        document.querySelectorAll('.glass-panel, .panel').forEach(el => {
            const rect = el.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width * 100).toFixed(1);
            const y = ((e.clientY - rect.top) / rect.height * 100).toFixed(1);
            el.style.setProperty('--mouse-x', x + '%');
            el.style.setProperty('--mouse-y', y + '%');
            el.classList.toggle('specular-active',
                e.clientX >= rect.left && e.clientX <= rect.right &&
                e.clientY >= rect.top && e.clientY <= rect.bottom
            );
        });
    });
})();

(function initHeaderScroll() {
    const header = document.getElementById('header');
    if (!header) return;
    window.addEventListener('scroll', () => {
        header.classList.toggle('scrolled', window.scrollY > 50);
    }, { passive: true });
})();

(function initReveals() {
    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });

    document.querySelectorAll('.reveal, .reveal-stagger').forEach(el => observer.observe(el));
})();

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        if (btn.dataset.tab === 'map' && window.map) {
            setTimeout(() => window.map.invalidateSize(), 100);
        }
        if (btn.dataset.tab === 'terrain') {
            setTimeout(() => _ensureTerrainRenderer(), 50);
        }
    });
});

(function initAmbient() {
    const canvas = document.getElementById('ambient-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h;

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    function draw() {
        ctx.clearRect(0, 0, w, h);
        // Subtle dot grid - cyan
        ctx.fillStyle = 'rgba(200,168,124,0.02)';
        const step = 60;
        for (let x = 0; x < w; x += step) {
            for (let y = 0; y < h; y += step) {
                ctx.beginPath();
                ctx.arc(x, y, 0.5, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }
    draw();
    window.addEventListener('resize', draw);
})();

function setStatus(text, type = 'default') {
    const el = document.getElementById('scan-status');
    if (el) el.innerHTML = `<span style="color:${type === 'error' ? 'var(--danger)' : type === 'success' ? 'var(--accent)' : 'var(--text-tertiary)'}">${text}</span>`;
    const dot = document.querySelector('.status-text');
    if (dot) dot.textContent = text || 'Ready';
}

let map, marker, scanCircle;

function initMap() {
    map = L.map('map', {
        center: [28.6139, 77.2090],
        zoom: 13,
        zoomControl: false
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CartoDB &copy; OSM',
        maxZoom: 19
    }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);

    // Coordinate display on mouse move
    const coordDisplay = L.control({ position: 'bottomleft' });
    coordDisplay.onAdd = function() {
        this._div = L.DomUtil.create('div', 'coord-display');
        this._div.style.cssText = 'background:rgba(1,1,3,0.95);color:#c8a87c;padding:4px 10px;font:11px monospace;border-radius:0;pointer-events:none;border:1px solid rgba(200,168,124,0.2);backdrop-filter:blur(12px);';
        this._div.innerHTML = 'Move cursor over map';
        return this._div;
    };
    coordDisplay.addTo(map);
    map.on('mousemove', (e) => {
        coordDisplay._div.innerHTML = e.latlng.lat.toFixed(6) + ', ' + e.latlng.lng.toFixed(6) + ' | zoom ' + map.getZoom();
    });

    map.on('click', (e) => setLocation(e.latlng.lat, e.latlng.lng));
    setLocation(28.6139, 77.2090);
    window.map = map;
}

function setLocation(lat, lon) {
    document.getElementById('input-lat').value = lat.toFixed(6);
    document.getElementById('input-lon').value = lon.toFixed(6);

    if (marker) map.removeLayer(marker);
    if (scanCircle) map.removeLayer(scanCircle);

    marker = L.marker([lat, lon], {
        icon: L.divIcon({
            className: 'chronovisor-marker',
            html: '<div style="width:18px;height:18px;background:rgba(200,168,124,0.9);border-radius:0;border:3px solid #010103;box-shadow:0 0 20px rgba(200,168,124,0.5),0 0 40px rgba(200,168,124,0.15);"></div>',
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        })
    }).addTo(map);
    marker.bindTooltip(lat.toFixed(6) + ', ' + lon.toFixed(6), {permanent: false, direction: 'top', offset: [0, -12], className: 'coord-tooltip'}).openTooltip();

    // Reverse geocode for locality name
    fetch('https://nominatim.openstreetmap.org/reverse?lat=' + lat + '&lon=' + lon + '&format=json&zoom=14')
        .then(r => r.json())
        .then(data => {
            const name = data.display_name ? data.display_name.split(',').slice(0, 3).join(', ') : '';
            if (name) marker.bindTooltip(name + '\n' + lat.toFixed(6) + ', ' + lon.toFixed(6), {permanent: false, direction: 'top', offset: [0, -12], className: 'coord-tooltip'});
        }).catch(() => {});

    const radius = parseInt(document.getElementById('input-radius').value) || 500;
    scanCircle = L.circle([lat, lon], {
        radius: radius,
        color: 'rgba(200,168,124,0.25)',
        fillColor: 'rgba(200,168,124,0.02)',
        fillOpacity: 1,
        weight: 1,
        dashArray: '4,4'
    }).addTo(map);
}

async function apiPost(endpoint, data) {
    setStatus('Scanning...');
    try {
        const resp = await fetch(API + endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
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

function getLocationData() {
    const startDate = document.getElementById('input-start').value || '2017-01-01';
    const year = parseInt(startDate.split('-')[0]);

    // Warn if date is before satellite coverage
    if (year < 2013) {
        const status = document.getElementById('scan-status');
        if (status) status.innerHTML = 'Note: Satellite data starts from 2013. Showing all available data.';
    }

    // Clamp to minimum satellite date
    const clampedDate = year < 2013 ? '2013-03-18' : startDate;

    return {
        lat: parseFloat(document.getElementById('input-lat').value),
        lon: parseFloat(document.getElementById('input-lon').value),
        radius_m: parseInt(document.getElementById('input-radius').value) || 500,
        start_date: clampedDate,
        source: document.getElementById('input-source').value
    };
}

async function runFullScan() {
    const loc = getLocationData();
    const result = await apiGet(
        `/api/full-scan?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&start_date=${loc.start_date}`
    );
    if (!result) return;
    document.querySelector('[data-tab="analysis"]').click();
    displayFullScanResults(result);
}

function displayFullScanResults(data) {
    const summary = data.summary || {};
    const findings = summary.findings || [];
    const conf = summary.confidence || 'low';
    const score = summary.archaeological_potential || 0;
    const suitability = data.archaeological_db?.suitability || {};
    const suitScore = suitability.score || 0;
    const satError = data.satellite?.error;
    const structError = data.structural_analysis?.error;

    // Confidence badge
    const badge = document.getElementById('confidence-badge');
    if (badge) badge.textContent = conf.toUpperCase();

    // Summary
    let summaryHTML = `
        <div class="metric-row">
            <div class="metric">
                <span class="metric-value">${score.toFixed(0)}%</span>
                <span class="metric-label">Archaeological Potential</span>
            </div>
            ${suitScore > 0 ? '<div class="metric"><span class="metric-value" style="color:' + (suitScore > 70 ? '#c8a87c' : suitScore > 50 ? '#ff8800' : '#ff3366') + ';">' + suitScore.toFixed(0) + '%</span><span class="metric-label">Site Suitability</span></div>' : ''}
            <div class="metric">
                <span class="metric-value">${data.satellite?.data_points || 0}</span>
                <span class="metric-label">Data Points</span>
            </div>
            <div class="metric">
                <span class="metric-value">${data.lightning?.strikes || '--'}</span>
                <span class="metric-label">EM Events</span>
            </div>
        </div>
        <div class="score-bar">
            <div class="score-bar-fill ${score > 70 ? 'high' : score > 40 ? 'medium' : ''}" style="width:${score}%"></div>
        </div>
    `;

    if (satError) summaryHTML += `<div class="finding-card warning">Satellite: ${satError}</div>`;
    if (structError) summaryHTML += `<div class="finding-card info">Structural: ${structError}</div>`;

    findings.forEach(f => {
        const cls = f.includes('HIGH') ? 'danger' : f.includes('Moderate') ? 'warning' : 'info';
        summaryHTML += `<div class="finding-card ${cls}">${f}</div>`;
    });

    if (summary.recommendation) {
        summaryHTML += `<div class="finding-card" style="border-left-color:var(--accent);">${summary.recommendation}</div>`;
    }
    document.getElementById('summary-content').innerHTML = summaryHTML;

    // Time series charts — delay to let tab become visible first
    const ts = data.satellite?.timeseries || [];
    if (ts.length > 0) {
        setTimeout(() => plotTimeseries(ts), 300);
    } else {
        const noData = '<div class="finding-card info">No satellite data for this date range. Satellite coverage: Sentinel-2 (2017-present), Landsat 8 (2013-present). Try a more recent date or a different location.</div>';
        const tsChart = document.getElementById('timeseries-chart');
        if (tsChart) tsChart.innerHTML = noData;
        const tsSurf = document.getElementById('timeseries-chart-surface');
        if (tsSurf) tsSurf.innerHTML = noData;
    }

    // Anomalies
    const anomalies = data.anomalies || [];
    let anomalyHTML = '';
    if (anomalies.length === 0) {
        anomalyHTML = '<div class="empty-state">No significant anomalies</div>';
    } else {
        anomalies.forEach(a => {
            const severity = a.deviation > 3 ? 'high' : a.deviation > 2 ? 'medium' : 'low';
            anomalyHTML += `
                <div class="finding-card ${severity === 'high' ? 'danger' : severity === 'medium' ? 'warning' : 'info'}">
                    <span class="anomaly-badge ${severity}">${severity.toUpperCase()}</span>
                    <strong style="color:var(--text)">${a.type.replace(/_/g, ' ').toUpperCase()}</strong> &mdash; ${a.date}<br>
                    Value: ${a.value} | Mean: ${a.mean} | Deviation: ${a.deviation}&sigma;<br>
                    <span style="color:var(--text-tertiary)">${a.interpretation}</span>
                </div>`;
        });
    }
    document.getElementById('anomalies-content').innerHTML = anomalyHTML;

    // Structural analysis
    const structural = data.structural_analysis || {};
    const structScore = structural.structural_probability || 0;
    let structHTML = `
        <div class="metric-row">
            <div class="metric">
                <span class="metric-value">${structScore.toFixed(0)}%</span>
                <span class="metric-label">Structure Probability</span>
            </div>
        </div>
        <div class="score-bar">
            <div class="score-bar-fill ${structScore > 70 ? 'high' : structScore > 40 ? 'medium' : ''}" style="width:${structScore}%"></div>
        </div>
    `;
    (structural.interpretation || []).forEach(i => {
        structHTML += `<div class="finding-card">${i}</div>`;
    });
    document.getElementById('structural-content').innerHTML = structHTML;

    // Historical maps
    const maps = data.historical_maps || [];
    let mapsHTML = '';
    maps.forEach(m => {
        mapsHTML += `<div class="finding-card info">
            <a href="${m.url}" target="_blank" class="map-link">${m.name}</a><br>
            <span style="color:var(--text-tertiary);font-size:10px;">${m.description}</span>
        </div>`;
    });
    document.getElementById('maps-content').innerHTML = mapsHTML || '<div class="finding-card info">Click links above to explore historical maps of this location in a new tab. Sources: Old Maps Online, David Rumsey, USGS Topos, Google Earth Timelapse, NASA Worldview.</div>';

    // Space weather
    const weatherData = data.space_weather || {};
    if (weatherData.error) {
        document.getElementById('weather-content').innerHTML = `<div class="finding-card warning">${weatherData.error}</div>`;
    } else {
        document.getElementById('weather-content').innerHTML =
            (weatherData.interpretation || ['No data']).map(i => `<div class="finding-card info">${i}</div>`).join('');
    }
}

async function runSatelliteAnalysis() {
    const loc = getLocationData();
    const result = await apiPost('/api/satellite/timeseries', loc);
    if (result && result.timeseries && result.timeseries.length > 0) {
        document.querySelector('[data-tab="analysis"]').click();
        setTimeout(() => plotTimeseries(result.timeseries), 100);
    } else {
        const noData = '<div class="finding-card info">No satellite data. Sentinel-2 (2017+), Landsat 8 (2013+).</div>';
        const el = document.getElementById('timeseries-chart');
        if (el) el.innerHTML = noData;
        const el2 = document.getElementById('timeseries-chart-surface');
        if (el2) el2.innerHTML = noData;
    }
}

async function runAnomalyDetection() {
    const loc = getLocationData();
    const result = await apiPost('/api/satellite/anomalies', loc);
    if (!result) return;
    document.querySelector('[data-tab="analysis"]').click();

    const anomalies = result.satellite_anomalies || [];
    let html = '';
    anomalies.forEach(a => {
        html += `<div class="finding-card warning">
            <strong style="color:var(--text)">${a.type.replace(/_/g, ' ').toUpperCase()}</strong> &mdash; ${a.date}<br>
            ${a.interpretation}
        </div>`;
    });
    document.getElementById('anomalies-content').innerHTML = html || '<div class="empty-state">No anomalies detected</div>';

    const s = result.structural_analysis || {};
    let sHTML = `<div class="metric-row"><div class="metric"><span class="metric-value">${(s.structural_probability || 0).toFixed(0)}%</span><span class="metric-label">Structure Probability</span></div></div>`;
    (s.interpretation || []).forEach(i => sHTML += `<div class="finding-card">${i}</div>`);
    document.getElementById('structural-content').innerHTML = sHTML;

    if (result.timeseries?.length > 0) setTimeout(() => plotTimeseries(result.timeseries), 100);
}

const plotlyLayout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#4a5a6a', family: 'JetBrains Mono, monospace', size: 10 },
    margin: { t: 20, r: 30, b: 40, l: 50 },
    xaxis: { gridcolor: 'rgba(200,168,124,0.04)', linecolor: 'rgba(200,168,124,0.1)', zerolinecolor: 'rgba(200,168,124,0.1)' },
    yaxis: { gridcolor: 'rgba(200,168,124,0.04)', linecolor: 'rgba(200,168,124,0.1)', zerolinecolor: 'rgba(200,168,124,0.1)' },
    showlegend: true,
    legend: { font: { size: 10, color: '#4a5a6a' }, bgcolor: 'transparent' }
};

const plotlyConfig = { responsive: true, displayModeBar: false };

// Store last timeseries data globally so charts persist across tab switches
let _lastTimeseriesData = null;
let _renderGen = 0;

function plotTimeseries(data) {
    _lastTimeseriesData = data;
    _renderBioChart(data);
    _renderSurfaceChart(data);
}

function _renderBioChart(data) {
    const el = document.getElementById('timeseries-chart');
    if (!el || !data || data.length === 0) return;

    const gen = ++_renderGen;
    const dates = data.map(d => d.date);
    const ndvi = data.map(d => d.ndvi);
    const savi = data.map(d => d.savi);
    const ndmi = data.map(d => d.ndmi);
    const moisture = data.map(d => d.moisture);

    const traces = [
        { x: dates, y: ndvi, name: 'NDVI', line: { color: '#c8a87c', width: 2 }, type: 'scatter', mode: 'lines', fill: 'tozeroy', fillcolor: 'rgba(200,168,124,0.05)' },
        { x: dates, y: savi, name: 'SAVI', line: { color: '#70a870', width: 1.5, dash: 'dot' }, type: 'scatter', mode: 'lines' },
        { x: dates, y: ndmi, name: 'NDMI', line: { color: '#dbb98f', width: 1.5 }, type: 'scatter', mode: 'lines', yaxis: 'y2' },
        { x: dates, y: moisture, name: 'NDWI', line: { color: '#7090a0', width: 1.5, dash: 'dash' }, type: 'scatter', mode: 'lines', yaxis: 'y2' }
    ];

    Plotly.newPlot('timeseries-chart', traces, {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#4a5a6a', family: 'monospace', size: 10 },
        margin: { t: 30, r: 60, b: 40, l: 60 },
        showlegend: true,
        legend: { font: { size: 9 }, bgcolor: 'rgba(0,0,0,0)', x: 0, y: 1.18, orientation: 'h' },
        xaxis: { gridcolor: 'rgba(200,168,124,0.04)', title: { text: 'Date', font: { size: 9 } } },
        yaxis: { title: { text: 'Vegetation Index', font: { size: 9, color: '#c8a87c' } }, side: 'left', position: 0, gridcolor: 'rgba(200,168,124,0.04)' },
        yaxis2: { title: { text: 'Moisture Index', font: { size: 9, color: '#dbb98f' } }, overlaying: 'y', side: 'right', position: 1, showgrid: false }
    }, { responsive: true, displayModeBar: false });

    setTimeout(() => { if (gen === _renderGen) try { Plotly.Plots.resize(el); } catch(e) {} }, 300);
}

function _renderSurfaceChart(data) {
    const el = document.getElementById('timeseries-chart-surface');
    if (!el || !data || data.length === 0) return;

    const gen = ++_renderGen;
    const dates = data.map(d => d.date);
    const ndbi = data.map(d => d.ndbi);
    const bsi = data.map(d => d.bsi);
    const thermal = data.map(d => d.thermal);

    const traces = [
        { x: dates, y: ndbi, name: 'NDBI (Built-up)', line: { color: '#ff8800', width: 2 }, type: 'scatter', mode: 'lines', fill: 'tozeroy', fillcolor: 'rgba(255,136,0,0.05)' },
        { x: dates, y: bsi, name: 'BSI (Bare Soil)', line: { color: '#ff6644', width: 1.5, dash: 'dot' }, type: 'scatter', mode: 'lines' },
        { x: dates, y: thermal, name: 'Thermal', line: { color: '#ff3366', width: 1.5 }, type: 'scatter', mode: 'lines', yaxis: 'y2' }
    ];

    Plotly.newPlot('timeseries-chart-surface', traces, {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#4a5a6a', family: 'monospace', size: 10 },
        margin: { t: 30, r: 60, b: 40, l: 60 },
        showlegend: true,
        legend: { font: { size: 9 }, bgcolor: 'rgba(0,0,0,0)', x: 0, y: 1.18, orientation: 'h' },
        xaxis: { gridcolor: 'rgba(200,168,124,0.04)', title: { text: 'Date', font: { size: 9 } } },
        yaxis: { title: { text: 'Structure Index', font: { size: 9, color: '#ff8800' } }, side: 'left', position: 0, gridcolor: 'rgba(200,168,124,0.04)' },
        yaxis2: { title: { text: 'Thermal (B11 DN)', font: { size: 9, color: '#ff3366' } }, overlaying: 'y', side: 'right', position: 1, showgrid: false }
    }, { responsive: true, displayModeBar: false });

    setTimeout(() => { if (gen === _renderGen) try { Plotly.Plots.resize(el); } catch(e) {} }, 300);
}

// Re-render both charts when Analysis tab becomes visible
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.dataset.tab === 'analysis' && _lastTimeseriesData) {
            setTimeout(() => {
                _renderBioChart(_lastTimeseriesData);
                _renderSurfaceChart(_lastTimeseriesData);
            }, 100);
        }
    });
});

async function loadMagneticField() {
    const loc = getLocationData();
    const el = document.getElementById('spectrum-chart');
    el.innerHTML = '<div class="empty-state">Loading magnetic field data...</div>';
    const result = await apiGet('/api/signal/magnetic-gradient?lat=' + loc.lat + '&lon=' + loc.lon + '&radius_m=' + loc.radius_m);
    if (!result || result.error) {
        el.innerHTML = '<div class="finding-card warning" style="padding:20px;margin:16px;">' + (result?.error || 'No response') + '</div>';
        return;
    }

    const profile = result.profile || [];
    if (profile.length === 0) {
        el.innerHTML = '<div class="finding-card info">No magnetic data available for this location.</div>';
        return;
    }

    // Plot as bar chart — magnetic intensity at each sample point
    const labels = profile.map(p => '(' + p.offset_x + ',' + p.offset_y + ')');
    const values = profile.map(p => p.total_intensity_nt);
    const meanVal = result.mean_nt || 0;

    Plotly.newPlot('spectrum-chart', [
        {
            x: labels, y: values,
            type: 'bar',
            marker: { color: values.map(v => v > meanVal + result.std_nt ? '#ff8800' : v < meanVal - result.std_nt ? '#ff3366' : '#c8a87c') },
            name: 'Total Intensity (nT)'
        },
        {
            x: [labels[0], labels[labels.length-1]], y: [meanVal, meanVal],
            type: 'scatter', mode: 'lines',
            line: { color: '#4a5a6a', dash: 'dash', width: 1 },
            name: 'Mean (' + meanVal + ' nT)'
        }
    ], {
        ...plotlyLayout,
        xaxis: { ...plotlyLayout.xaxis, title: { text: 'Sample Point (grid offset)', font: { size: 9 } } },
        yaxis: { ...plotlyLayout.yaxis, title: { text: 'Total Intensity (nT)', font: { size: 9 } } },
        margin: { t: 20, r: 20, b: 60, l: 60 }
    }, plotlyConfig);

    // Add interpretation below chart without destroying Plotly canvas
    const interp = result.interpretation || [];
    let infoHTML = '<div style="text-align:center;font-size:11px;color:#4a5a6a;padding:4px;">Gradient: ' + result.gradient_nt + ' nT | Std Dev: ' + result.std_nt + ' nT | Source: NOAA WMM</div>';
    interp.forEach(i => { infoHTML += '<div style="text-align:center;font-size:10px;color:#c8a87c;padding:2px;">' + i + '</div>'; });
    const infoDiv = document.createElement('div');
    infoDiv.innerHTML = infoHTML;
    el.appendChild(infoDiv);
}

async function loadSARBackscatter() {
    const loc = getLocationData();
    const el = document.getElementById('em-field-chart');
    el.innerHTML = '<div class="empty-state">Loading SAR backscatter data...</div>';
    const result = await apiGet('/api/sar/backscatter?lat=' + loc.lat + '&lon=' + loc.lon + '&radius_m=' + loc.radius_m + '&start_date=' + loc.start_date);
    if (!result || result.error) {
        el.innerHTML = '<div class="finding-card warning" style="padding:20px;margin:16px;">' + (result?.error || 'No SAR data available') + '</div>';
        return;
    }

    const ts = result.timeseries || [];
    if (ts.length === 0) {
        el.innerHTML = '<div class="finding-card info">No SAR data for this date range/location.</div>';
        return;
    }

    const dates = ts.map(d => d.date);
    const vv = ts.map(d => d.vv);
    const vh = ts.map(d => d.vh);
    const ratio = ts.map(d => d.ratio);

    Plotly.newPlot('em-field-chart', [
        { x: dates, y: vv, name: 'VV (co-pol)', line: { color: '#c8a87c', width: 2 }, type: 'scatter', mode: 'lines' },
        { x: dates, y: vh, name: 'VH (cross-pol)', line: { color: '#ff8800', width: 1.5 }, type: 'scatter', mode: 'lines' },
        { x: dates, y: ratio, name: 'VV/VH Ratio', line: { color: '#70a870', width: 1.5, dash: 'dot' }, type: 'scatter', mode: 'lines', yaxis: 'y2' }
    ], {
        ...plotlyLayout,
        xaxis: { ...plotlyLayout.xaxis, title: { text: 'Date', font: { size: 9 } } },
        yaxis: { ...plotlyLayout.yaxis, title: { text: 'Backscatter (dB)', font: { size: 9, color: '#c8a87c' } }, side: 'left', gridcolor: 'rgba(200,168,124,0.04)' },
        yaxis2: { title: { text: 'VV/VH Ratio', font: { size: 9, color: '#70a870' } }, overlaying: 'y', side: 'right', showgrid: false },
        margin: { t: 30, r: 60, b: 40, l: 60 }
    }, plotlyConfig);

    const infoDiv = document.createElement('div');
    infoDiv.innerHTML = '<div style="text-align:center;font-size:10px;color:#4a5a6a;padding:4px;">' + result.count + ' SAR observations | Source: Sentinel-1 IW | ' + loc.start_date + ' to present</div>';
    el.appendChild(infoDiv);
}

async function loadRadioData() {
    const loc = getLocationData();
    const result = await apiGet('/api/data/radio-astronomy?freq_mhz=1420&lat=' + loc.lat + '&lon=' + loc.lon);
    if (!result) return;

    if (result.error) {
        document.getElementById('radio-chart').innerHTML =
            `<div class="finding-card warning" style="padding:20px;margin:16px;">${result.error}</div>`;
        return;
    }

    const swData = result.solar_radiation || {};
    const dates = swData.dates || [];
    const values = swData.allsky_sw_dn_wm2 || [];

    if (dates.length === 0) {
        document.getElementById('radio-chart').innerHTML = '<div class="empty-state">No data available</div>';
        return;
    }

    Plotly.newPlot('radio-chart', [{
        x: dates, y: values,
        type: 'scatter', fill: 'tozeroy',
        line: { color: '#c8a87c', width: 1 },
        fillcolor: 'rgba(200,168,124,0.05)',
        name: 'Solar Irradiance'
    }], {
        ...plotlyLayout,
        xaxis: { ...plotlyLayout.xaxis, title: { text: 'Date', font: { size: 9 } } },
        yaxis: { ...plotlyLayout.yaxis, title: { text: 'W/m\u00B2', font: { size: 9 } } }
    }, plotlyConfig);
}

let terrainScene, terrainCamera, terrainRenderer;
let _terrainAnimating = false;

function _ensureTerrainRenderer() {
    const container = document.getElementById('terrain-3d');
    if (!container) return false;

    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w === 0 || h === 0) return false;

    // Create scene + renderer on first call, or resize if container changed
    if (!terrainRenderer) {
        terrainScene = new THREE.Scene();
        terrainScene.background = new THREE.Color(0x050505);

        terrainCamera = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000);
        terrainCamera.position.set(0, 5, 8);
        terrainCamera.lookAt(0, 0, 0);

        terrainRenderer = new THREE.WebGLRenderer({ antialias: true });
        terrainRenderer.setSize(w, h);
        terrainRenderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(terrainRenderer.domElement);

        terrainScene.add(new THREE.AmbientLight(0x222222));
        const pt = new THREE.PointLight(0xc8a87c, 1.5, 100);
        pt.position.set(5, 10, 5);
        terrainScene.add(pt);
        terrainScene.add(new THREE.GridHelper(10, 20, 0x111111, 0x111111));

        if (!_terrainAnimating) {
            _terrainAnimating = true;
            (function loop() {
                requestAnimationFrame(loop);
                if (terrainRenderer && terrainScene && terrainCamera) {
                    terrainRenderer.render(terrainScene, terrainCamera);
                }
            })();
        }
    } else {
        // Container may have resized (tab switch) — update renderer + camera
        terrainRenderer.setSize(w, h);
        terrainCamera.aspect = w / h;
        terrainCamera.updateProjectionMatrix();
    }
    return true;
}

async function generateTerrain() {
    const loc = getLocationData();
    const info = document.getElementById('terrain-info');
    if (info) info.innerHTML = '<div style="color:#666;">Loading elevation data...</div>';

    const result = await apiPost(`/api/ai/terrain?lat=${loc.lat}&lon=${loc.lon}&grid_size=20`, {});
    if (!result) { if (info) info.innerHTML = '<div class="finding-card danger">No response</div>'; return; }

    if (result.error) {
        if (info) info.innerHTML = '<div class="finding-card danger">' + result.error + '</div>';
        return;
    }

    // Init or resize renderer (tab is visible now so container has real dimensions)
    if (!_ensureTerrainRenderer()) {
        if (info) info.innerHTML = '<div class="finding-card danger">Terrain container has no dimensions</div>';
        return;
    }

    // Remove old terrain meshes, keep lights/grid
    terrainScene.children = terrainScene.children.filter(c => !c.isMesh);

    const elevation = result.elevation || [];
    if (elevation.length === 0) {
        if (info) info.innerHTML = '<div class="finding-card warning">Empty elevation data</div>';
        return;
    }

    const size = elevation.length;

    // Normalize elevation relative to min so terrain sits on the grid plane
    let minElev = Infinity;
    for (let i = 0; i < size; i++)
        for (let j = 0; j < size; j++)
            if (elevation[i][j] < minElev) minElev = elevation[i][j];

    const geometry = new THREE.PlaneGeometry(10, 10, size - 1, size - 1);
    const positions = geometry.attributes.position;
    const heightScale = 0.15; // exaggerate subtle terrain

    for (let i = 0; i < size; i++) {
        for (let j = 0; j < size; j++) {
            const idx = i * size + j;
            positions.setZ(idx, (elevation[i][j] - minElev) * heightScale);
        }
    }
    geometry.computeVertexNormals();

    const material = new THREE.MeshPhongMaterial({
        color: 0xc8a87c,
        wireframe: false,
        flatShading: true,
        transparent: true,
        opacity: 0.85
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 2;
    terrainScene.add(mesh);

    const wireMaterial = new THREE.MeshBasicMaterial({
        color: 0xc8a87c, wireframe: true, transparent: true, opacity: 0.08
    });
    const wireMesh = new THREE.Mesh(geometry.clone(), wireMaterial);
    wireMesh.rotation.x = -Math.PI / 2;
    wireMesh.position.y = 0.01;
    terrainScene.add(wireMesh);

    if (info) info.innerHTML = `
        <div class="metric-row">
            <div class="metric"><span class="metric-value">${result.min_elevation}m</span><span class="metric-label">Min</span></div>
            <div class="metric"><span class="metric-value">${result.max_elevation}m</span><span class="metric-label">Max</span></div>
            <div class="metric"><span class="metric-value">${result.anomaly_points || 0}</span><span class="metric-label">Anomalies</span></div>
        </div>
        <div class="finding-card info">Grid: ${size}x${size} | Ridges: ${result.ridge_points} | Valleys: ${result.valley_points}</div>
    `;
}

async function loadSpaceWeather() {
    const result = await apiGet('/api/data/space-weather?days=3');
    if (!result) return;

    const solarError = result.solar_wind?.error;
    const kpError = result.geomagnetic?.error;
    const interp = result.solar_wind?.interpretation || result.geomagnetic?.interpretation || [];

    if (solarError && kpError) {
        document.getElementById('weather-content').innerHTML =
            `<div class="finding-card warning">${solarError}</div>`;
    } else {
        document.getElementById('weather-content').innerHTML =
            interp.map(i => `<div class="finding-card info">${i}</div>`).join('') ||
            '<div class="empty-state">No data</div>';
    }
}


async function loadHistory() {
    const result = await apiGet('/api/history');
    if (!result) return;
    const el = document.getElementById('history-content');
    if (!el) return;

    if (!result.scans || result.scans.length === 0) {
        el.innerHTML = '<div class="empty-state">No scans yet. Run a scan to populate history.</div>';
        return;
    }

    let html = '<div style="margin-bottom:12px;font-size:11px;color:#666;">' + result.count + ' scan(s) in history. Click a scan to view details.</div>';
    result.scans.forEach((s, i) => {
        const score = s.structural_probability || 0;
        const color = score > 70 ? '#c8a87c' : score > 40 ? '#ff8800' : '#4a5a6a';
        const type = s.type === 'mega' ? 'MEGA' : 'SAT';
        html += '<div class="finding-card" style="cursor:pointer;" onclick="viewHistoryScan(' + i + ')">';
        html += '<strong>#' + i + ' [' + type + ']</strong> ';
        html += (s.place_name || '') + ' (' + s.lat?.toFixed(4) + ', ' + s.lon?.toFixed(4) + ') ';
        html += '<span style="color:' + color + ';">Score: ' + score.toFixed(0) + '%</span> ';
        html += '| Anomalies: ' + (s.anomaly_count || 0) + ' | Points: ' + (s.data_points || 0);
        html += '</div>';
    });
    el.innerHTML = html;
}

async function viewHistoryScan(index) {
    const result = await apiGet('/api/history/' + index);
    if (!result || result.error) return;
    document.querySelector('[data-tab="analysis"]').click();
    displayFullScanResults(result);
}

// Load history on tab click
document.querySelectorAll('.nav-btn').forEach(btn => {
    if (btn.dataset.tab === 'history') {
        btn.addEventListener('click', () => loadHistory());
    }
});


async function searchPlace() {
    const query = document.getElementById('input-place').value.trim();
    if (!query) return;
    const status = document.getElementById('scan-status');
    if (status) status.innerHTML = 'Searching...';
    const result = await apiGet('/api/geocode?q=' + encodeURIComponent(query));
    if (!result || result.error) {
        if (status) status.innerHTML = result?.error || 'No results';
        return;
    }
    if (result.results && result.results.length > 0) {
        const place = result.results[0];
        setLocation(place.lat, place.lon);
        map.setView([place.lat, place.lon], 13);
        if (status) status.innerHTML = 'Found: ' + place.name.split(',').slice(0, 2).join(',');
        setTimeout(() => { if (status) status.innerHTML = ''; }, 3000);
    } else {
        if (status) status.innerHTML = 'No results for: ' + query;
    }
}


async function runGeminiAnalysis() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status') || document.getElementById('scan-status');
    if (status) status.innerHTML = 'Running AI analysis...';
    const result = await apiPost('/api/gemini/analyze', loc);
    if (!result) { if (status) status.innerHTML = 'Error'; return; }
    if (result.error) { if (status) status.innerHTML = result.error; return; }
    document.querySelector('[data-tab="ai"]')?.click();
    const ai = result.ai_analysis || {};
    const scan = result.scan || {};
    const summary = scan.summary || {};
    const score = summary.archaeological_potential || 0;
    let html = '<div style="padding:12px;font-size:13px;line-height:1.7;white-space:pre-wrap;">';
    html += '<h3 style="color:var(--accent);margin-bottom:12px;">AI Analysis</h3>';
    if (ai.analysis) html += formatMarkdown(ai.analysis);
    html += '<div style="margin-top:16px;">';
    html += '<span class="metric"><span class="value">' + score.toFixed(0) + '%</span><span class="label">Potential</span></span>';
    html += '<span class="metric"><span class="value">' + (summary.confidence || 'N/A').toUpperCase() + '</span><span class="label">Confidence</span></span>';
    html += '</div></div>';
    const el = document.getElementById('ai-result');
    if (el) el.innerHTML = html;
    if (status) status.innerHTML = 'AI analysis complete';
}

async function runGeminiReport() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status') || document.getElementById('scan-status');
    if (status) status.innerHTML = 'Generating report...';
    const result = await apiPost('/api/gemini/report', loc);
    if (!result) { if (status) status.innerHTML = 'Error'; return; }
    if (result.error) { if (status) status.innerHTML = result.error; return; }
    document.querySelector('[data-tab="ai"]')?.click();
    const el = document.getElementById('ai-result');
    if (el) el.innerHTML = '<div style="padding:12px;font-size:13px;line-height:1.7;white-space:pre-wrap;"><h3 style="color:var(--accent);">Archaeological Report</h3>' + formatMarkdown(result.report || 'No report') + '</div>';
    if (status) status.innerHTML = 'Report generated';
}

async function loadHistoricalContext() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status') || document.getElementById('scan-status');
    if (status) status.innerHTML = 'Loading history...';
    const result = await apiGet('/api/gemini/history?lat=' + loc.lat + '&lon=' + loc.lon);
    if (!result) { if (status) status.innerHTML = 'Error'; return; }
    if (result.error) { if (status) status.innerHTML = result.error; return; }
    document.querySelector('[data-tab="ai"]')?.click();
    const el = document.getElementById('ai-result');
    if (el) el.innerHTML = '<div style="padding:12px;font-size:13px;line-height:1.7;white-space:pre-wrap;"><h3 style="color:var(--accent);">Historical Context</h3>' + formatMarkdown(result.history || 'No data') + '</div>';
    if (status) status.innerHTML = 'History loaded';
}

async function runInvestigationPlan() {
    const loc = getLocationData();
    const status = document.getElementById('ai-status') || document.getElementById('scan-status');
    if (status) status.innerHTML = 'Planning investigation...';
    const result = await apiPost('/api/gemini/investigate', loc);
    if (!result) { if (status) status.innerHTML = 'Error'; return; }
    if (result.error) { if (status) status.innerHTML = result.error; return; }
    document.querySelector('[data-tab="ai"]')?.click();
    const el = document.getElementById('ai-result');
    if (el) el.innerHTML = '<div style="padding:12px;font-size:13px;line-height:1.7;white-space:pre-wrap;"><h3 style="color:var(--accent);">Investigation Plan</h3>' + formatMarkdown(result.plan || 'No plan') + '</div>';
    if (status) status.innerHTML = 'Plan ready';
}

async function sendChat() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;
    const messages = document.getElementById('chat-messages');
    messages.innerHTML += '<div style="margin-bottom:12px;text-align:right;"><div style="font-size:9px;color:#5a524a;text-transform:uppercase;letter-spacing:1px;">OPERATOR</div><div style="background:rgba(200,168,124,0.06);border:1px solid rgba(200,168,124,0.15);padding:10px 14px;display:inline-block;max-width:80%;text-align:left;font-size:13px;color:var(--accent);">' + escapeHtml(message) + '</div></div>';
    const loadingId = 'ld-' + Date.now();
    messages.innerHTML += '<div style="margin-bottom:12px;" id="' + loadingId + '"><div style="font-size:9px;color:#5a524a;text-transform:uppercase;letter-spacing:1px;">CHRONOVISOR</div><div style="background:rgba(0,0,0,0.3);border:1px solid rgba(200,168,124,0.15);padding:10px 14px;display:inline-block;max-width:80%;font-size:13px;border-left:3px solid #c8a87c;">PROCESSING...</div></div>';
    messages.scrollTop = messages.scrollHeight;
    input.value = '';
    // Backend auto-attaches latest scan data when available
    const result = await apiPost('/api/gemini/chat', { message: message, session_id: 'web-session' });
    const loadingEl = document.getElementById(loadingId);
    if (loadingEl) loadingEl.remove();
    if (result && result.reply) {
        messages.innerHTML += '<div style="margin-bottom:12px;"><div style="font-size:9px;color:#5a524a;text-transform:uppercase;letter-spacing:1px;">CHRONOVISOR</div><div style="background:rgba(0,0,0,0.3);border:1px solid rgba(200,168,124,0.15);padding:10px 14px;display:inline-block;max-width:85%;font-size:13px;line-height:1.7;border-left:3px solid #c8a87c;">' + formatMarkdown(result.reply) + '</div></div>';
    } else {
        messages.innerHTML += '<div style="margin-bottom:12px;"><div style="font-size:9px;color:#666;">Chronovisor</div><div style="color:#ff4444;font-size:13px;">Error: ' + (result?.error || 'Unknown') + '</div></div>';
    }
    messages.scrollTop = messages.scrollHeight;
}

async function runMegaScan() {
    const loc = getLocationData();
    const status = document.getElementById('scan-status');
    if (status) status.innerHTML = 'Running MEGA SCAN (all systems)...';
    const place = prompt('Place name (optional, improves results):') || '';
    const result = await apiGet('/api/mega-scan?lat=' + loc.lat + '&lon=' + loc.lon + '&radius_m=' + loc.radius_m + '&start_date=' + loc.start_date + '&place_name=' + encodeURIComponent(place));
    if (!result) { if (status) status.innerHTML = 'Error'; return; }
    document.querySelector('[data-tab="analysis"]')?.click();
    displayFullScanResults(result);
    if (result.environmental) displayEnvironmental(result.environmental);
    if (result.historical_web) displayWebArchives(result.historical_web);
    if (result.archaeological_db) displayArchDB(result.archaeological_db);
    if (status) status.innerHTML = 'MEGA SCAN complete';
}

async function runEnvironmentalScan() {
    const loc = getLocationData();
    const status = document.getElementById('scan-status');
    if (status) status.innerHTML = 'Fetching environmental data...';
    const result = await apiGet('/api/env/full?lat=' + loc.lat + '&lon=' + loc.lon);
    if (!result) { if (status) status.innerHTML = 'Error'; return; }
    document.querySelector('[data-tab="analysis"]')?.click();
    displayEnvironmental(result);
    if (status) status.innerHTML = 'Environmental data loaded';
}

function displayEnvironmental(env) {
    let html = '';
    const soil = env.soil || {};
    if (soil.properties) {
        html += '<div class="finding-card info"><strong>SOIL (ISRIC SoilGrids)</strong></div>';
        for (const [k, v] of Object.entries(soil.properties)) {
            html += '<span class="metric"><span class="value">' + v.value + '</span><span class="label">' + k + ' (' + v.unit + ')</span></span>';
        }
        (soil.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }
    const faults = env.faults || {};
    if (faults.count !== undefined) {
        html += '<div class="finding-card info"><strong>SEISMIC (USGS)</strong> - ' + faults.count + ' earthquakes, activity: ' + faults.fault_activity + '</div>';
        (faults.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }
    const water = env.water_table || {};
    if (water.water_table) {
        html += '<div class="finding-card info"><strong>WATER TABLE</strong> - ' + water.water_table + ' (elev: ' + water.elevation_m + 'm)</div>';
        (water.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }
    const el = document.getElementById('env-content');
    if (el) el.innerHTML = html || '<div class="empty-state">No environmental data</div>';
}

async function runHistoricalWeb() {
    const loc = getLocationData();
    const status = document.getElementById('scan-status');
    if (status) status.innerHTML = 'Searching web archives...';
    const place = prompt('Place name (for Wayback search):') || '';
    const result = await apiGet('/api/web/full?lat=' + loc.lat + '&lon=' + loc.lon + '&place_name=' + encodeURIComponent(place));
    if (!result) { if (status) status.innerHTML = 'Error'; return; }
    document.querySelector('[data-tab="analysis"]')?.click();
    displayWebArchives(result);
    if (status) status.innerHTML = 'Web archives loaded';
}

function displayWebArchives(web) {
    let html = '';
    const wb = web.wayback || {};
    if (wb.archives && wb.archives.length > 0) {
        html += '<div class="finding-card info"><strong>WAYBACK MACHINE</strong> - ' + wb.count + ' archived pages</div>';
        wb.archives.slice(0, 10).forEach(a => {
            const yr = a.timestamp ? a.timestamp.substring(0, 4) : '?';
            html += '<div class="finding-card"><a href="' + a.archived + '" target="_blank" style="color:var(--accent);">[' + yr + '] ' + a.url.substring(0, 80) + '...</a></div>';
        });
    }
    const osm = web.osm || {};
    if (osm.total !== undefined) {
        html += '<div class="finding-card info"><strong>OPENSTREETMAP</strong> - ' + osm.total + ' features, ' + (osm.historic ? osm.historic.length : 0) + ' historic</div>';
        (osm.historic || []).slice(0, 5).forEach(h => {
            html += '<div class="finding-card">' + (h.name || 'Unnamed') + ' (' + (h.historic || h.heritage || 'historic') + ')</div>';
        });
    }
    const el = document.getElementById('webarchive-content');
    if (el) el.innerHTML = html || '<div class="empty-state">No web archive data</div>';
}

function displayArchDB(db) {
    let html = '';

    // Pleiades
    const pleiades = db.pleiades || {};
    if (pleiades.places && pleiades.places.length > 0) {
        html += '<div class="finding-card info"><strong>PLEIADES + WIKIDATA</strong> - ' + pleiades.count + ' ancient/monumental sites</div>';
        pleiades.places.slice(0, 8).forEach(p => {
            html += '<div class="finding-card">' + (p.title || 'Unnamed') + ' (' + (p.distance_km || '?') + 'km)</div>';
        });
    }

    // Wikidata
    const wiki = db.wikidata || {};
    if (wiki.sites && wiki.sites.length > 0) {
        html += '<div class="finding-card info"><strong>WIKIDATA</strong> - ' + wiki.count + ' archaeological sites</div>';
        wiki.sites.slice(0, 5).forEach(s => {
            html += '<div class="finding-card">' + s.name + ' (' + s.distance_km + 'km away)</div>';
        });
    }

    // Magnetic
    const mag = db.magnetic || {};
    if (mag.total_intensity_nt) {
        html += '<div class="finding-card info"><strong>MAGNETIC FIELD (NOAA WMM)</strong> - ' + mag.total_intensity_nt + ' nT</div>';
        (mag.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }

    // Nighttime lights
    const night = db.nighttime_lights || {};
    if (night.granules !== undefined) {
        html += '<div class="finding-card info"><strong>NIGHTTIME LIGHTS (VIIRS)</strong> - ' + night.granules + ' granules</div>';
        (night.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }

    // Climate
    const climate = db.climate || {};
    if (climate.temperature) {
        html += '<div class="finding-card info"><strong>CLIMATE (' + (climate.source || '') + ')</strong></div>';
        if (climate.temperature.mean_c !== null) html += '<span class="metric"><span class="value">' + climate.temperature.mean_c + '°C</span><span class="label">Mean Temp</span></span>';
        if (climate.precipitation && climate.precipitation.total_mm !== null) html += '<span class="metric"><span class="value">' + climate.precipitation.total_mm + 'mm</span><span class="label">Annual Rain</span></span>';
        (climate.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }

    // Land cover
    const lc = db.land_cover || {};
    if (lc.available !== undefined) {
        html += '<div class="finding-card info"><strong>LAND COVER</strong> - ' + (lc.available ? 'Available' : 'Not available') + '</div>';
        (lc.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }

    // Suitability
    const suit = db.suitability || {};
    if (suit.score !== undefined) {
        const color = suit.score > 70 ? 'var(--accent)' : suit.score > 50 ? '#ff8800' : '#ff3366';
        html += '<div class="finding-card" style="border-left-color:' + color + ';"><strong>SITE SUITABILITY</strong></div>';
        html += '<span class="metric"><span class="value" style="color:' + color + ';">' + suit.score + '%</span><span class="label">Suitability</span></span>';
        (suit.interpretation || []).forEach(i => html += '<div class="finding-card">' + i + '</div>');
    }

    const el = document.getElementById('archdb-content');
    if (el) el.innerHTML = html || '<div class="empty-state">No archaeological database data</div>';
}

async function exportReport() {
    const loc = getLocationData();
    const place = prompt('Place name for report:') || '';
    window.open('/api/export/report?lat=' + loc.lat + '&lon=' + loc.lon + '&place_name=' + encodeURIComponent(place), '_blank');
}

function exportJSON() {
    const loc = getLocationData();
    window.open('/api/export/json?lat=' + loc.lat + '&lon=' + loc.lon, '_blank');
}

function exportCSV() {
    const loc = getLocationData();
    window.open('/api/export/csv?lat=' + loc.lat + '&lon=' + loc.lon, '_blank');
}

function formatMarkdown(text) {
    if (!text) return '';
    let h = escapeHtml(text);
    h = h.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\*(.*?)\*/g, '<em>$1</em>');
    h = h.replace(/^### (.*?)$/gm, '<h4 style="color:var(--accent);margin:12px 0 4px;">$1</h4>');
    h = h.replace(/^## (.*?)$/gm, '<h3 style="color:var(--accent);margin:16px 0 6px;">$1</h3>');
    h = h.replace(/^# (.*?)$/gm, '<h2 style="color:var(--accent);margin:20px 0 8px;">$1</h2>');
    h = h.replace(/^- (.*?)$/gm, '&bull; $1');
    h = h.replace(/\n/g, '<br>');
    return h;
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}


async function loadNDVIChange() {
    const loc = getLocationData();
    const el = document.getElementById('ndvi-change-content');
    el.innerHTML = '<div class="empty-state">Comparing NDVI periods...</div>';
    const result = await apiGet(`/api/site/ndvi-change?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&p1_start=2018-01-01&p1_end=2018-12-31&p2_start=2024-01-01&p2_end=2024-12-31`);
    if (!result || result.error) { el.innerHTML = '<div class="finding-card warning">' + (result?.error || 'No response') + '</div>'; return; }

    const p1 = result.period1 || {};
    const p2 = result.period2 || {};
    const changeColor = result.change < -0.02 ? 'var(--danger)' : result.change > 0.02 ? 'var(--accent)' : 'var(--info)';
    let html = `
        <div class="metric-row">
            <div class="metric"><span class="metric-value">${(p1.ndvi || 0).toFixed(3)}</span><span class="metric-label">${p1.start?.substring(0,4)} NDVI (${p1.images} imgs)</span></div>
            <div class="metric"><span class="metric-value">${(p2.ndvi || 0).toFixed(3)}</span><span class="metric-label">${p2.start?.substring(0,4)} NDVI (${p2.images} imgs)</span></div>
            <div class="metric"><span class="metric-value" style="color:${changeColor};">${(result.pct_change || 0) > 0 ? '+' : ''}${(result.pct_change || 0).toFixed(1)}%</span><span class="metric-label">Change</span></div>
        </div>`;
    (result.interpretation || []).forEach(i => { html += `<div class="finding-card">${i}</div>`; });
    el.innerHTML = html;
}

async function loadElevationProfile() {
    const loc = getLocationData();
    const dir = document.getElementById('elev-direction').value;
    const el = document.getElementById('elev-profile-chart');
    el.innerHTML = '<div class="empty-state">Loading elevation transect...</div>';
    const result = await apiGet(`/api/site/elevation-profile?lat=${loc.lat}&lon=${loc.lon}&radius_m=${loc.radius_m}&direction=${dir}`);
    if (!result || result.error) { el.innerHTML = '<div class="finding-card warning">' + (result?.error || 'No response') + '</div>'; return; }

    const dists = result.distances_m || [];
    const elevs = result.elevations || [];
    const anomalyDists = result.anomaly_distances || [];

    // Find closest distance match for anomaly markers (float precision fix)
    function findClosestIdx(target) {
        let best = 0, bestDiff = Infinity;
        for (let i = 0; i < dists.length; i++) {
            const diff = Math.abs(dists[i] - target);
            if (diff < bestDiff) { bestDiff = diff; best = i; }
        }
        return best;
    }

    const traces = [{
        x: dists.map(d => (d / 1000).toFixed(2)),
        y: elevs,
        type: 'scatter', mode: 'lines+markers',
        line: { color: '#c8a87c', width: 2 },
        marker: { size: 4, color: '#c8a87c' },
        fill: 'tozeroy', fillcolor: 'rgba(200,168,124,0.05)',
        name: 'Elevation'
    }];

    if (anomalyDists.length > 0) {
        const aX = [], aY = [];
        anomalyDists.forEach(d => {
            const idx = findClosestIdx(d);
            aX.push((dists[idx] / 1000).toFixed(2));
            aY.push(elevs[idx]);
        });
        traces.push({
            x: aX, y: aY,
            type: 'scatter', mode: 'markers',
            marker: { size: 10, color: '#ff3366', symbol: 'diamond' },
            name: 'Anomaly'
        });
    }

    Plotly.newPlot('elev-profile-chart', traces, {
        ...plotlyLayout,
        xaxis: { ...plotlyLayout.xaxis, title: { text: 'Distance (km) — ' + dir, font: { size: 9 } } },
        yaxis: { ...plotlyLayout.yaxis, title: { text: 'Elevation (m)', font: { size: 9 } } },
        margin: { t: 20, r: 20, b: 50, l: 60 },
        showlegend: true,
        legend: { font: { size: 9 }, bgcolor: 'rgba(0,0,0,0)', x: 0, y: 1.15, orientation: 'h' }
    }, plotlyConfig);

    // Append info below chart without destroying Plotly canvas
    let info = `<div style="text-align:center;font-size:10px;color:#4a5a6a;padding:4px;">Range: ${result.elevation_range}m | Anomalies: ${result.anomaly_points} | Source: ${result.source}</div>`;
    (result.interpretation || []).forEach(i => { info += `<div style="text-align:center;font-size:10px;color:#c8a87c;padding:2px;">${i}</div>`; });
    const infoDiv = document.createElement('div');
    infoDiv.innerHTML = info;
    el.appendChild(infoDiv);
}

async function loadWaterProximity() {
    const loc = getLocationData();
    const el = document.getElementById('water-content');
    el.innerHTML = '<div class="empty-state">Searching for water sources...</div>';
    const result = await apiGet(`/api/site/water?lat=${loc.lat}&lon=${loc.lon}&radius_m=2000`);
    if (!result || result.error) { el.innerHTML = '<div class="finding-card warning">' + (result?.error || 'No response') + '</div>'; return; }

    const features = result.features || [];
    let html = '';
    if (result.nearest_water_m !== null && result.nearest_water_m !== undefined) {
        const distColor = result.nearest_water_m < 200 ? 'var(--accent)' : result.nearest_water_m < 500 ? '#ff8800' : 'var(--text)';
        html += `<div class="metric-row"><div class="metric"><span class="metric-value" style="color:${distColor};">${result.nearest_water_m}m</span><span class="metric-label">Nearest Water</span></div><div class="metric"><span class="metric-value">${result.features_found}</span><span class="metric-label">Sources Found</span></div></div>`;
    }
    features.slice(0, 8).forEach(f => {
        const name = f.name || f.type;
        html += `<div class="finding-card info">${name} — ${f.distance_m}m away</div>`;
    });
    (result.interpretation || []).forEach(i => { html += `<div class="finding-card">${i}</div>`; });
    el.innerHTML = html || '<div class="finding-card info">No water features found</div>';
}

async function loadGeology() {
    const loc = getLocationData();
    const el = document.getElementById('geology-content');
    el.innerHTML = '<div class="empty-state">Loading geological data...</div>';
    const result = await apiGet(`/api/site/geology?lat=${loc.lat}&lon=${loc.lon}`);
    if (!result || result.error) { el.innerHTML = '<div class="finding-card warning">' + (result?.error || 'No response') + '</div>'; return; }

    const units = result.units || [];
    let html = '';
    units.forEach(u => {
        const color = u.color ? '#' + u.color : 'var(--accent)';
        html += `<div class="finding-card" style="border-left-color:${color};"><strong>${u.name}</strong>${u.age ? ' — ' + u.age : ''}<br><span style="color:var(--text-tertiary);font-size:10px;">${u.lith || ''}${u.descrip ? ' · ' + u.descrip : ''}</span></div>`;
    });
    (result.interpretation || []).forEach(i => { html += `<div class="finding-card info">${i}</div>`; });
    el.innerHTML = html || '<div class="finding-card info">No geological data</div>';
}

async function loadNearbyPlaces() {
    const loc = getLocationData();
    const el = document.getElementById('places-content');
    el.innerHTML = '<div class="empty-state">Finding nearby places...</div>';
    const result = await apiGet(`/api/site/places?lat=${loc.lat}&lon=${loc.lon}&radius_km=50`);
    if (!result || result.error) { el.innerHTML = '<div class="finding-card warning">' + (result?.error || 'No response') + '</div>'; return; }

    const places = result.places || [];
    let html = `<div class="metric-row"><div class="metric"><span class="metric-value">${result.count}</span><span class="metric-label">Places Found</span></div></div>`;
    places.slice(0, 10).forEach(p => {
        const pop = p.population > 0 ? ` (pop: ${p.population.toLocaleString()})` : '';
        html += `<div class="finding-card info"><strong>${p.name}</strong>${p.country ? ', ' + p.country : ''} — ${p.distance_km}km${pop}</div>`;
    });
    (result.interpretation || []).forEach(i => { html += `<div class="finding-card">${i}</div>`; });
    el.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    loadSpaceWeather();
    initPremiumInteractions();
});

function initPremiumInteractions() {
    // Scroll progress bar
    const scrollBars = document.querySelectorAll('.analysis-layout, .sidebar, .panel-body, #chat-messages, .ai-sidebar');
    scrollBars.forEach(el => {
        el.addEventListener('scroll', () => {
            const bar = document.getElementById('scrollProgress');
            if (!bar) return;
            const scrollTop = el.scrollTop || document.documentElement.scrollTop;
            const scrollHeight = el.scrollHeight - el.clientHeight || document.documentElement.scrollHeight - document.documentElement.clientHeight;
            const progress = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0;
            bar.style.width = progress + '%';
        }, { passive: true });
    });

    // Global scroll progress
    window.addEventListener('scroll', () => {
        const bar = document.getElementById('scrollProgress');
        if (!bar) return;
        const scrollTop = window.scrollY;
        const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
        bar.style.width = (scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0) + '%';
    }, { passive: true });

    // Magnetic buttons
    document.querySelectorAll('.btn-scan, .btn-secondary').forEach(btn => {
        btn.addEventListener('mousemove', (e) => {
            const rect = btn.getBoundingClientRect();
            const x = e.clientX - rect.left - rect.width / 2;
            const y = e.clientY - rect.top - rect.height / 2;
            btn.style.transform = `translate(${x * 0.15}px, ${y * 0.15}px)`;
        });
        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'translate(0, 0)';
        });
    });

    // 3D tilt on glass panels (analysis tab)
    document.querySelectorAll('.panel.glass-panel').forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;
            card.style.transform = `perspective(800px) rotateX(${y * -6}deg) rotateY(${x * 6}deg) scale3d(1.01, 1.01, 1.01)`;
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'perspective(800px) rotateX(0) rotateY(0) scale3d(1, 1, 1)';
        });
    });

    // Border beam mouse tracking on glass panels
    document.querySelectorAll('.glass-panel').forEach(panel => {
        panel.addEventListener('mousemove', (e) => {
            const rect = panel.getBoundingClientRect();
            const mouseX = e.clientX - rect.left - rect.width / 2;
            const mouseY = e.clientY - rect.top - rect.height / 2;
            let angle = Math.atan2(mouseY, mouseX) * (180 / Math.PI);
            angle = (angle + 360) % 360;
            panel.style.setProperty('--beam-angle', angle + 'deg');
        });
    });

    // GSAP scroll reveals (if GSAP loaded)
    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
        gsap.registerPlugin(ScrollTrigger);

        gsap.utils.toArray('.panel.glass-panel').forEach(panel => {
            gsap.from(panel, {
                scrollTrigger: {
                    trigger: panel,
                    start: 'top 90%',
                    toggleActions: 'play none none none'
                },
                y: 20,
                opacity: 0,
                duration: 0.6,
                ease: 'power2.out',
                clearProps: 'transform,opacity'
            });
        });

        // Stagger metrics
        gsap.utils.toArray('.metric-row').forEach(row => {
            gsap.from(row.children, {
                scrollTrigger: {
                    trigger: row,
                    start: 'top 90%',
                    toggleActions: 'play none none none'
                },
                y: 15,
                opacity: 0,
                duration: 0.4,
                stagger: 0.06,
                ease: 'power2.out',
                clearProps: 'transform,opacity'
            });
        });
    }
}

(function initGlitchText() {
    const glitchElements = document.querySelectorAll('.boot-name, .logo-text h1');
    
    glitchElements.forEach(el => {
        let isGlitching = false;
        
        setInterval(() => {
            if (Math.random() > 0.95 && !isGlitching) {
                isGlitching = true;
                el.style.animation = 'glitch 0.3s linear';
                setTimeout(() => {
                    el.style.animation = '';
                    isGlitching = false;
                }, 300);
            }
        }, 2000);
    });
})();

(function initCircuitTraces() {
    const panels = document.querySelectorAll('.panel.glass-panel');
    
    panels.forEach(panel => {
        const trace = document.createElement('div');
        trace.className = 'circuit-line';
        trace.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(200, 168, 124, 0.3), transparent);
            animation: circuit-flow 4s linear infinite;
            pointer-events: none;
            z-index: 10;
        `;
        panel.appendChild(trace);
    });
})();

(function initPulsingIndicators() {
    const statusDot = document.querySelector('.status-dot');
    if (statusDot) {
        setInterval(() => {
            statusDot.style.boxShadow = '0 0 15px rgba(200, 168, 124, 0.8)';
            setTimeout(() => {
                statusDot.style.boxShadow = '0 0 8px rgba(200, 168, 124, 0.4)';
            }, 200);
        }, 3000);
    }
})();

(function initDataStream() {
    const bootSub = document.querySelector('.boot-sub');
    if (!bootSub) return;
    
    const chars = '0123456789ABCDEF';
    let streamInterval;
    
    function startStream() {
        let stream = '';
        for (let i = 0; i < 32; i++) {
            stream += chars[Math.floor(Math.random() * chars.length)];
        }
        bootSub.textContent = stream;
    }
    
    streamInterval = setInterval(startStream, 100);
    
    setTimeout(() => {
        clearInterval(streamInterval);
        bootSub.textContent = 'Temporal Archaeology Engine';
    }, 2000);
})();

(function initPanelGlow() {
    document.querySelectorAll('.panel.glass-panel').forEach(panel => {
        panel.addEventListener('mouseenter', () => {
            panel.style.boxShadow = '0 0 40px rgba(200, 168, 124, 0.08), inset 0 0 40px rgba(200, 168, 124, 0.02)';
        });
        panel.addEventListener('mouseleave', () => {
            panel.style.boxShadow = '';
        });
    });
})();
