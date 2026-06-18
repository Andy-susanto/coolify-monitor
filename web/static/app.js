/* ─── Coolify Monitor — Frontend JS v2 ─────────── */

let refreshTimer = null;
let REFRESH_INTERVAL = window.__REFRESH_INTERVAL__ || 5000;
let currentData = null;
let pendingAction = null;
let currentAlerts = [];
let dismissedAlerts = new Set();
let alertPanelOpen = false;
let kbdHelpOpen = false;

document.addEventListener('DOMContentLoaded', () => {
    fetchData();
    startAutoRefresh();
    document.getElementById('autoRefresh').addEventListener('change', (e) => {
        e.target.checked ? startAutoRefresh() : stopAutoRefresh();
    });

    // Search input handler
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', () => {
        applyFilter(searchInput.value);
        document.getElementById('searchClear').style.display = searchInput.value ? 'block' : 'none';
    });
});

// ─── Fetch ───────────────────────────────────────
async function fetchData() {
    try {
        const resp = await fetch('/api/status');
        if (resp.status === 401) { window.location.href = '/login'; return; }
        const data = await resp.json();
        if (!data.ok) { showError(data.error || 'Unknown error'); return; }
        hideError();
        currentData = data;
        renderAll(data);
        updateTimestamp(data.ts);
        setFooter(true, 'Connected');
        fetchResources();
        detectAndRenderAlerts(data);
    } catch (err) {
        showError('Cannot connect to backend: ' + err.message);
        setFooter(false, 'Disconnected');
    }
}

function startAutoRefresh() { stopAutoRefresh(); refreshTimer = setInterval(fetchData, REFRESH_INTERVAL); }
function stopAutoRefresh() { if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; } }

// ─── Status Helpers ──────────────────────────────
function normSt(s) {
    if (!s) return { m: 'unknown', sub: '' };
    const p = s.toLowerCase().trim().split(':');
    return { m: p[0], sub: p[1] || '' };
}
function isUp(s) { const { m } = normSt(s); return ['running','started','healthy'].includes(m); }
function isDown(s) { const { m } = normSt(s); return ['stopped','exited','dead','failed'].includes(m); }
function isUnhealthy(s) {
    const { m, sub } = normSt(s);
    return (m === 'running' && sub === 'unhealthy') || m === 'unhealthy';
}

function badge(status) {
    const { m, sub } = normSt(status);
    const txt = status || 'unknown';
    let cls;
    if (m === 'running' && sub === 'unhealthy') cls = 'starting';
    else if (['running','started','healthy'].includes(m)) cls = 'running';
    else if (['stopped','exited','dead','failed'].includes(m)) cls = 'stopped';
    else if (['starting','restarting','deploying','queued'].includes(m)) cls = 'starting';
    else cls = 'unknown';
    return `<span class="st st-${cls}"><span class="st-dot"></span>${esc(txt)}</span>`;
}

// ─── Render All ──────────────────────────────────
function renderAll(d) {
    const all = [...d.applications, ...d.services, ...d.databases];
    const running = all.filter(r => isUp(r.status)).length;

    document.getElementById('statServers').textContent = d.servers.length;
    document.getElementById('statProjects').textContent = d.projects.length;
    document.getElementById('statApps').textContent = d.applications.length;
    document.getElementById('statServices').textContent = d.services.length;
    document.getElementById('statDatabases').textContent = d.databases.length;
    document.getElementById('statRunning').textContent = running;

    document.getElementById('tabApps').textContent = d.applications.length;
    document.getElementById('tabSvcs').textContent = d.services.length;
    document.getElementById('tabDbs').textContent = d.databases.length;
    document.getElementById('tabProjs').textContent = d.projects.length;
    document.getElementById('tabSrvs').textContent = d.servers.length;

    renderApps(d.applications);
    renderSvcs(d.services);
    renderDbs(d.databases);
    renderProjs(d.projects);
    renderSrvs(d.servers);

    const empty = !d.applications.length && !d.services.length && !d.databases.length && !d.projects.length;
    document.getElementById('emptyState').style.display = empty ? 'block' : 'none';

    // Reapply filter if active
    const searchVal = document.getElementById('searchInput').value;
    if (searchVal) applyFilter(searchVal);
}

// ─── Applications ────────────────────────────────
function renderApps(apps) {
    const tb = document.querySelector('#tbl-applications tbody');
    if (!apps.length) { tb.innerHTML = emptyRow(6); return; }
    tb.innerHTML = apps.map(a => {
        const url = a.fqdn || '';
        const urlH = url ? `<a href="${esc(url)}" target="_blank" class="c-url">${esc(trunc(url, 44))}</a>` : '<span class="c-dim">—</span>';
        const build = a.build_pack ? `<span class="c-tag">${esc(a.build_pack)}</span>` : '<span class="c-dim">—</span>';
        const branch = a.git_branch ? `<span class="c-tag">${esc(a.git_branch)}</span>` : '<span class="c-dim">—</span>';
        const running = isUp(a.status);
        const stopped = isDown(a.status);
        const alertClass = (stopped || isUnhealthy(a.status)) ? ' row-alert' : '';
        return `<tr class="data-row${alertClass}" data-search="${esc((a.name || a.uuid || '') + ' ' + (a.status || '') + ' ' + (a.build_pack || '') + ' ' + (a.git_branch || ''))}">
            <td class="c-name">${esc(a.name || a.uuid?.slice(0,8) || '?')}</td>
            <td>${badge(a.status)}</td>
            <td>${urlH}</td>
            <td>${build}</td>
            <td>${branch}</td>
            <td><div class="actions-cell">
                ${stopped ? `<button class="act-btn act-btn-start" onclick="doAction('app','${a.uuid}','start','${esc(a.name)}')">▶ Start</button>` : ''}
                ${running ? `<button class="act-btn act-btn-stop" onclick="doAction('app','${a.uuid}','stop','${esc(a.name)}')">■ Stop</button>` : ''}
                ${running ? `<button class="act-btn act-btn-restart" onclick="doAction('app','${a.uuid}','restart','${esc(a.name)}')">↻ Restart</button>` : ''}
                <button class="act-btn" onclick="openLogs('${a.uuid}','${esc(a.name||'')}')">📋</button>
                <button class="act-btn" onclick="openDetail('${a.uuid}','${esc(a.name||'')}')" title="Process detail">🔍</button>
            </div></td>
        </tr>`;
    }).join('');
}

// ─── Services ────────────────────────────────────
function renderSvcs(svcs) {
    const tb = document.querySelector('#tbl-services tbody');
    if (!svcs.length) { tb.innerHTML = emptyRow(5); return; }
    tb.innerHTML = svcs.map(s => {
        const url = s.fqdn || '';
        const urlH = url ? `<a href="${esc(url)}" target="_blank" class="c-url">${esc(trunc(url, 44))}</a>` : '<span class="c-dim">—</span>';
        const running = isUp(s.status);
        const stopped = isDown(s.status);
        const alertClass = (stopped || isUnhealthy(s.status)) ? ' row-alert' : '';
        return `<tr class="data-row${alertClass}" data-search="${esc((s.name || s.uuid || '') + ' ' + (s.status || '') + ' ' + (s.service_type || s.type || ''))}">
            <td class="c-name">${esc(s.name || s.uuid?.slice(0,8) || '?')}</td>
            <td>${badge(s.status)}</td>
            <td><span class="c-tag">${esc(s.service_type || s.type || '—')}</span></td>
            <td>${urlH}</td>
            <td><div class="actions-cell">
                ${stopped ? `<button class="act-btn act-btn-start" onclick="doAction('service','${s.uuid}','start','${esc(s.name)}')">▶ Start</button>` : ''}
                ${running ? `<button class="act-btn act-btn-stop" onclick="doAction('service','${s.uuid}','stop','${esc(s.name)}')">■ Stop</button>` : ''}
                ${running ? `<button class="act-btn act-btn-restart" onclick="doAction('service','${s.uuid}','restart','${esc(s.name)}')">↻ Restart</button>` : ''}
                <button class="act-btn" onclick="openDetail('${s.uuid}','${esc(s.name||'')}')" title="Process detail">🔍</button>
            </div></td>
        </tr>`;
    }).join('');
}

// ─── Databases ───────────────────────────────────
function renderDbs(dbs) {
    const tb = document.querySelector('#tbl-databases tbody');
    if (!dbs.length) { tb.innerHTML = emptyRow(6); return; }
    tb.innerHTML = dbs.map(db => {
        const host = db.host || '—';
        const port = db.public_port || db.port || '';
        const hp = port ? `${host}:${port}` : host;
        const running = isUp(db.status);
        const stopped = isDown(db.status);
        const alertClass = (stopped || isUnhealthy(db.status)) ? ' row-alert' : '';
        return `<tr class="data-row${alertClass}" data-search="${esc((db.name || db.uuid || '') + ' ' + (db.status || '') + ' ' + (db.database_type || db.type || '') + ' ' + hp)}">
            <td class="c-name">${esc(db.name || db.uuid?.slice(0,8) || '?')}</td>
            <td>${badge(db.status)}</td>
            <td><span class="c-tag">${esc(db.database_type || db.type || '—')}</span></td>
            <td class="c-dim">${esc(db.version || '—')}</td>
            <td class="c-dim">${esc(hp)}</td>
            <td><div class="actions-cell">
                ${stopped ? `<button class="act-btn act-btn-start" onclick="doAction('db','${db.uuid}','start','${esc(db.name)}')">▶ Start</button>` : ''}
                ${running ? `<button class="act-btn act-btn-stop" onclick="doAction('db','${db.uuid}','stop','${esc(db.name)}')">■ Stop</button>` : ''}
                ${running ? `<button class="act-btn act-btn-restart" onclick="doAction('db','${db.uuid}','restart','${esc(db.name)}')">↻ Restart</button>` : ''}
                <button class="act-btn" onclick="openDetail('${db.uuid}','${esc(db.name||'')}')" title="Process detail">🔍</button>
            </div></td>
        </tr>`;
    }).join('');
}

// ─── Projects ────────────────────────────────────
function renderProjs(projs) {
    const tb = document.querySelector('#tbl-projects tbody');
    if (!projs.length) { tb.innerHTML = emptyRow(3); return; }
    tb.innerHTML = projs.map(p => {
        const desc = p.description ? esc(trunc(p.description, 60)) : '<span class="c-dim">—</span>';
        return `<tr class="data-row" data-search="${esc((p.name || p.uuid || '') + ' ' + (p.description || ''))}">
            <td class="c-name">${esc(p.name || p.uuid?.slice(0,8) || '?')}</td>
            <td class="c-dim">${esc(p.uuid?.slice(0,12) || '—')}</td>
            <td>${desc}</td>
        </tr>`;
    }).join('');
}

// ─── Servers ─────────────────────────────────────
function renderSrvs(srvs) {
    const tb = document.querySelector('#tbl-servers tbody');
    if (!srvs.length) { tb.innerHTML = emptyRow(5); return; }
    tb.innerHTML = srvs.map(s => {
        const ok = s.is_reachable ?? s.settings?.is_reachable ?? null;
        const st = ok === true ? 'healthy' : ok === false ? 'unreachable' : 'unknown';
        const usable = s.is_usable ?? s.settings?.is_usable ?? false;
        const alertClass = ok === false ? ' row-alert' : '';
        return `<tr class="data-row${alertClass}" data-search="${esc((s.name || s.uuid || '') + ' ' + st + ' ' + (s.ip || s.fqdn || ''))}">
            <td class="c-name">${esc(s.name || s.uuid?.slice(0,8) || '?')}</td>
            <td>${badge(st)}</td>
            <td class="c-dim">${esc(s.ip || s.fqdn || '—')}</td>
            <td class="c-dim">${esc(String(s.port || '—'))}</td>
            <td>${usable ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--red)">✗</span>'}</td>
        </tr>`;
    }).join('');
}

// ─── Actions ─────────────────────────────────────
function doAction(type, uuid, action, name) {
    const icons = { start: '▶️', stop: '⏹️', restart: '🔄' };
    const labels = { start: 'Start', stop: 'Stop', restart: 'Restart' };

    pendingAction = { type, uuid, action, name };

    document.getElementById('confirmIcon').textContent = icons[action] || '⚠️';
    document.getElementById('confirmTitle').textContent = `${labels[action]} ${name}?`;
    document.getElementById('confirmDesc').textContent =
        action === 'stop' ? `This will stop "${name}" and it will become unavailable.` :
        action === 'start' ? `This will start/deploy "${name}".` :
        `This will restart "${name}". There may be a brief downtime.`;

    const okBtn = document.getElementById('confirmOk');
    okBtn.textContent = labels[action];
    okBtn.className = `btn-ctrl ${action === 'stop' ? 'btn-danger' : ''}`;

    document.getElementById('confirmOverlay').classList.add('open');
}

function confirmCancel() {
    document.getElementById('confirmOverlay').classList.remove('open');
    pendingAction = null;
}

async function confirmExecute() {
    if (!pendingAction) return;
    const { type, uuid, action, name } = pendingAction;
    document.getElementById('confirmOverlay').classList.remove('open');

    const apiType = type === 'app' ? 'app' : type === 'service' ? 'service' : 'db';
    const url = `/api/${apiType}/${uuid}/${action}`;

    toast('info', `${action === 'stop' ? 'Stopping' : action === 'start' ? 'Starting' : 'Restarting'} ${name}...`);

    try {
        const resp = await fetch(url, { method: 'POST' });
        const data = await resp.json();

        if (data.ok || resp.status === 200) {
            toast('success', data.message || `${action} berhasil`);
            setTimeout(fetchData, 2000);
            setTimeout(fetchData, 5000);
        } else {
            toast('error', data.message || data.error || `Action failed (${resp.status})`);
        }
    } catch (err) {
        toast('error', `Request failed: ${err.message}`);
    }

    pendingAction = null;
}

// ─── Keyboard Shortcuts ──────────────────────────
document.addEventListener('keydown', e => {
    // Don't trigger shortcuts when typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        if (e.key === 'Escape') {
            e.target.blur();
            clearSearch();
        }
        return;
    }

    if (e.key === 'Escape') {
        if (document.getElementById('confirmOverlay').classList.contains('open')) {
            confirmCancel();
        } else if (document.getElementById('detailModal').classList.contains('open')) {
            closeDetailModal();
        } else if (document.getElementById('logsModal').classList.contains('open')) {
            closeLogsModal();
        } else if (alertPanelOpen) {
            toggleAlertPanel();
        } else if (kbdHelpOpen) {
            toggleKbdHelp();
        }
        return;
    }

    if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        fetchData();
        return;
    }

    if (e.key === '/') {
        e.preventDefault();
        document.getElementById('searchInput').focus();
        return;
    }

    if (e.key === 'b' || e.key === 'B') {
        toggleAlertPanel();
        return;
    }

    if (e.key === '?') {
        toggleKbdHelp();
        return;
    }

    // Tab shortcuts: 1-6
    const tabMap = { '1': 'applications', '2': 'services', '3': 'databases', '4': 'projects', '5': 'resources', '6': 'servers', '7': 'uptime' };
    if (tabMap[e.key]) {
        e.preventDefault();
        switchTab(tabMap[e.key]);
    }
});

// ─── Logs Modal ──────────────────────────────────
async function openLogs(uuid, name) {
    document.getElementById('logsModal').classList.add('open');
    document.getElementById('modalTitle').textContent = `Logs — ${name || uuid}`;
    document.getElementById('logsContent').innerHTML = '<div class="spinner"></div> Loading logs…';
    try {
        const resp = await fetch(`/api/logs/${uuid}?lines=200`);
        const data = await resp.json();
        document.getElementById('logsContent').textContent = data.ok ? (data.logs || '(empty)') : `Error: ${data.error}`;
    } catch (err) {
        document.getElementById('logsContent').textContent = `Error: ${err.message}`;
    }
}
function closeLogsModal() { document.getElementById('logsModal').classList.remove('open'); }

// ─── Detail Modal ──────────────────────────────
let detailData = null;

async function openDetail(uuid, name) {
    document.getElementById('detailModal').classList.add('open');
    document.getElementById('detailTitle').textContent = name || 'Container Detail';
    document.getElementById('detailContainerName').textContent = uuid;
    document.getElementById('dpanel-processes').innerHTML = '<div class="spinner"></div> Loading processes…';
    document.getElementById('dpanel-config').innerHTML = '<div class="spinner"></div> Loading config…';
    document.getElementById('detailLogsContent').textContent = 'Loading logs…';
    switchDetailTab('processes');

    try {
        const resp = await fetch(`/api/container/${uuid}/detail`);
        const data = await resp.json();
        detailData = data;

        document.getElementById('detailContainerName').textContent = data.container_name || uuid;

        // Render processes
        renderDetailProcesses(data);

        // Render config
        renderDetailConfig(data);

        // Render logs
        renderDetailLogs(data);
    } catch (err) {
        document.getElementById('dpanel-processes').innerHTML = `<div style="color:var(--red);padding:20px">Error: ${esc(err.message)}</div>`;
    }
}

function closeDetailModal() {
    document.getElementById('detailModal').classList.remove('open');
    detailData = null;
}

function switchDetailTab(tab) {
    document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.detail-panel').forEach(p => p.classList.remove('active'));
    document.querySelector(`[data-dtab="${tab}"]`).classList.add('active');
    document.getElementById(`dpanel-${tab}`).classList.add('active');
}

function renderDetailProcesses(data) {
    const panel = document.getElementById('dpanel-processes');
    const procs = data.processes || [];
    if (data.processes_error) {
        panel.innerHTML = `<div style="color:var(--red);padding:20px">Error: ${esc(data.processes_error)}</div>`;
        return;
    }
    if (!procs.length) {
        panel.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">No running processes</div>';
        return;
    }
    panel.innerHTML = `
        <div style="padding:4px 0 8px;color:var(--text-muted);font-size:12px">${procs.length} process(es) running</div>
        <table class="proc-table">
            <thead><tr>
                <th>PID</th><th>User</th><th>CPU%</th><th>MEM%</th><th>RSS</th><th>Stat</th><th>Command</th>
            </tr></thead>
            <tbody>${procs.map(p => `<tr>
                <td>${esc(p.pid || '—')}</td>
                <td>${esc(p.user || '—')}</td>
                <td>${esc(p.cpu || '—')}</td>
                <td>${esc(p.mem || '—')}</td>
                <td>${esc(p.rss || '—')}</td>
                <td>${esc(p.stat || '—')}</td>
                <td class="proc-cmd" title="${esc(p.command || '')}">${esc(trunc(p.command || '—', 80))}</td>
            </tr>`).join('')}</tbody>
        </table>`;
}

function renderDetailConfig(data) {
    const panel = document.getElementById('dpanel-config');
    const ins = data.inspect || {};
    if (data.inspect_error) {
        panel.innerHTML = `<div style="color:var(--red);padding:20px">Error: ${esc(data.inspect_error)}</div>`;
        return;
    }
    if (!Object.keys(ins).length) {
        panel.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">No config data available</div>';
        return;
    }

    let html = '<div class="inspect-grid">';

    // Basic info
    html += '<div class="inspect-section">Container Info</div>';
    if (ins.name) html += kv('Name', ins.name);
    if (ins.resource_type) html += kv('Type', ins.resource_type);
    if (ins.image) html += kv('Image', ins.image);
    if (ins.status) html += kv('Status', ins.status);
    if (ins.fqdn) html += kv('URL', ins.fqdn);
    if (ins.created) html += kv('Created', new Date(ins.created).toLocaleString());

    // Build config
    if (ins.git_repository || ins.build_pack) {
        html += '<div class="inspect-section">Build</div>';
        if (ins.git_repository) html += kv('Repository', ins.git_repository);
        if (ins.git_branch) html += kv('Branch', ins.git_branch);
        if (ins.build_pack) html += kv('Build Pack', ins.build_pack);
    }

    // Docker info
    if (ins.entrypoint || ins.cmd) {
        html += '<div class="inspect-section">Command</div>';
        if (ins.entrypoint) html += kv('Entrypoint', Array.isArray(ins.entrypoint) ? ins.entrypoint.join(' ') : ins.entrypoint);
        if (ins.cmd) html += kv('CMD', Array.isArray(ins.cmd) ? ins.cmd.join(' ') : ins.cmd);
    }

    // Limits
    if (ins.limits) {
        const l = ins.limits;
        if (l.memory || l.cpu || l.cpus) {
            html += '<div class="inspect-section">Resource Limits</div>';
            if (l.memory) html += kv('Memory', l.memory + ' MB');
            if (l.memory_swap) html += kv('Memory Swap', l.memory_swap + ' MB');
            if (l.cpu) html += kv('CPU Shares', l.cpu);
            if (l.cpus) html += kv('CPUs', l.cpus);
        }
    }

    // Restart policy
    if (ins.restart_policy) {
        html += '<div class="inspect-section">Restart Policy</div>';
        html += kv('Policy', typeof ins.restart_policy === 'object' ? ins.restart_policy.Name || '—' : ins.restart_policy);
    }

    // Networks
    if (ins.networks && ins.networks.length) {
        html += '<div class="inspect-section">Networks</div>';
        html += `<div class="inspect-val" style="grid-column:1/-1">${ins.networks.map(n => `<span class="inspect-badge">${esc(typeof n === 'string' ? n : n.name || JSON.stringify(n))}</span>`).join('')}</div>`;
    }

    // Ports
    if (ins.ports && ins.ports.length) {
        html += '<div class="inspect-section">Ports</div>';
        ins.ports.forEach(p => html += kv('Port', typeof p === 'string' ? p : JSON.stringify(p)));
    }

    // Healthcheck
    if (ins.healthcheck && Object.keys(ins.healthcheck).length) {
        html += '<div class="inspect-section">Healthcheck</div>';
        const hc = ins.healthcheck;
        if (hc.enabled !== undefined) html += kv('Enabled', hc.enabled ? '✓ Yes' : '✗ No');
        if (hc.path) html += kv('Path', hc.path);
        if (hc.port) html += kv('Port', hc.port);
        if (hc.interval) html += kv('Interval', hc.interval + 's');
        if (hc.timeout) html += kv('Timeout', hc.timeout + 's');
        if (hc.retries) html += kv('Retries', hc.retries);
    }

    // Mounts
    if (ins.mounts && ins.mounts.length) {
        html += '<div class="inspect-section">Volumes</div>';
        ins.mounts.forEach(m => html += kv(m.dest || m.target || '—', `${m.source || m.host_path || '—'} ${m.mode ? '(' + m.mode + ')' : ''}`));
    }

    // Labels
    if (ins.labels && Object.keys(ins.labels).length) {
        html += '<div class="inspect-section">Labels</div>';
        for (const [k, v] of Object.entries(ins.labels)) {
            html += kv(k, v);
        }
    }
    if (ins.custom_labels) {
        html += '<div class="inspect-section">Custom Labels</div>';
        html += `<div class="inspect-val" style="grid-column:1/-1;font-size:11px;word-break:break-all">${esc(ins.custom_labels)}</div>`;
    }

    // Environment variables count
    if (ins.env_count) {
        html += '<div class="inspect-section">Environment</div>';
        html += kv('Variables', `${ins.env_count} env vars`);
    }

    html += '</div>';
    panel.innerHTML = html;
}

function kv(key, val) {
    return `<div class="inspect-key">${esc(key)}</div><div class="inspect-val">${esc(String(val ?? '—'))}</div>`;
}

function renderDetailLogs(data) {
    const el = document.getElementById('detailLogsContent');
    const logs = data.logs || [];
    if (data.logs_error) {
        el.textContent = `Error: ${data.logs_error}`;
        return;
    }
    el.textContent = logs.length ? logs.join('\n') : '(no logs)';
}

// ─── Tabs ────────────────────────────────────────
function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`panel-${tab}`).classList.add('active');
    if (tab === 'uptime') fetchUptime();
}

// ─── Uptime Tracking ─────────────────────────────
let uptimeWindow = 24;

function setUptimeWindow(hours) {
    uptimeWindow = hours;
    document.querySelectorAll('.uptime-win-btn').forEach(b => {
        b.classList.toggle('active', Number(b.getAttribute('data-win')) === hours);
    });
    fetchUptime();
}

async function fetchUptime() {
    const tb = document.querySelector('#tbl-uptime tbody');
    try {
        const resp = await fetch(`/api/uptime?hours=${uptimeWindow}`);
        const data = await resp.json();
        if (!data.ok) {
            tb.innerHTML = `<tr><td colspan="6" class="c-dim" style="text-align:center;padding:28px">Error: ${esc(data.error || 'unknown')}</td></tr>`;
            return;
        }
        renderUptime(data.resources);
    } catch (err) {
        tb.innerHTML = `<tr><td colspan="6" class="c-dim" style="text-align:center;padding:28px">Gagal memuat: ${esc(err.message)}</td></tr>`;
    }
}

function uptimeClass(pct) {
    if (pct >= 99.5) return 'up-excellent';
    if (pct >= 99) return 'up-good';
    if (pct >= 95) return 'up-fair';
    return 'up-poor';
}

function fmtDuration(seconds) {
    if (!seconds || seconds < 1) return '0s';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}h ${h}j`;
    if (h > 0) return `${h}j ${m}m`;
    if (m > 0) return `${m}m`;
    return `${Math.round(seconds)}s`;
}

function renderUptime(resources) {
    const tb = document.querySelector('#tbl-uptime tbody');
    document.getElementById('tabUptime').textContent = resources.length;

    if (!resources.length) {
        tb.innerHTML = `<tr><td colspan="6" class="c-dim" style="text-align:center;padding:28px">Belum ada data uptime. Monitor sedang mengumpulkan — cek lagi nanti.</td></tr>`;
        return;
    }

    tb.innerHTML = resources.map(r => {
        const pct = r.uptime_pct;
        const cls = uptimeClass(pct);
        const dotCls = r.current_up ? 'st-running' : 'st-stopped';
        const statusTxt = r.current_up ? 'up' : 'down';
        return `<tr class="data-row" data-search="${esc((r.name || '') + ' ' + (r.type || ''))}">
            <td class="c-name">${esc(r.name || r.uuid?.slice(0,8) || '?')}</td>
            <td><span class="c-tag">${esc(r.type || '—')}</span></td>
            <td>
                <div class="uptime-cell">
                    <span class="uptime-pct ${cls}">${pct.toFixed(2)}%</span>
                    <div class="uptime-bar-wrap"><div class="uptime-bar ${cls}" style="width:${pct}%"></div></div>
                </div>
            </td>
            <td><span class="st st-${dotCls.replace('st-','')}"><span class="st-dot"></span>${statusTxt}</span></td>
            <td class="c-dim">${fmtDuration(r.down_seconds)}</td>
            <td class="c-dim">${fmtDuration(r.measured_seconds)}</td>
        </tr>`;
    }).join('');
}

// ─── Search / Filter ─────────────────────────────
function applyFilter(query) {
    if (!query) {
        document.querySelectorAll('.data-row').forEach(r => r.classList.remove('filtered-out'));
        return;
    }
    const q = query.toLowerCase();
    document.querySelectorAll('.data-row').forEach(row => {
        const searchable = (row.getAttribute('data-search') || '').toLowerCase();
        row.classList.toggle('filtered-out', !searchable.includes(q));
    });
}

function clearSearch() {
    const input = document.getElementById('searchInput');
    input.value = '';
    document.getElementById('searchClear').style.display = 'none';
    applyFilter('');
}

// ─── Alert System ────────────────────────────────
function detectAndRenderAlerts(data) {
    const alerts = [];
    const all = [...(data.applications || []), ...(data.services || []), ...(data.databases || [])];

    // Detect stopped/exited/dead containers
    all.forEach(item => {
        const { m, sub } = normSt(item.status);
        const name = item.name || item.uuid?.slice(0, 8) || 'Unknown';
        const type = item.database_type ? 'database' : item.service_type ? 'service' : 'application';

        if (['stopped', 'exited', 'dead', 'failed'].includes(m)) {
            alerts.push({
                id: `down-${item.uuid}`,
                severity: 'critical',
                message: `${name} is ${m}`,
                detail: `${type} · Status: ${item.status}`,
                tab: type === 'database' ? 'databases' : type === 'service' ? 'services' : 'applications'
            });
        }

        if (m === 'running' && sub === 'unhealthy') {
            alerts.push({
                id: `unhealthy-${item.uuid}`,
                severity: 'warning',
                message: `${name} is unhealthy`,
                detail: `${type} · Running but health check failing`,
                tab: type === 'database' ? 'databases' : type === 'service' ? 'services' : 'applications'
            });
        }
    });

    // Detect servers unreachable
    (data.servers || []).forEach(s => {
        const ok = s.is_reachable ?? s.settings?.is_reachable ?? null;
        if (ok === false) {
            alerts.push({
                id: `server-${s.uuid}`,
                severity: 'critical',
                message: `Server ${s.name || s.uuid?.slice(0, 8)} unreachable`,
                detail: `${s.ip || s.fqdn || 'unknown'}:${s.port || '—'}`,
                tab: 'servers'
            });
        }
    });

    // Filter out dismissed
    currentAlerts = alerts.filter(a => !dismissedAlerts.has(a.id));
    renderAlertPanel();
    updateAlertBadge();
}

function renderAlertPanel() {
    const list = document.getElementById('alertList');
    if (!currentAlerts.length) {
        list.innerHTML = '<div class="alert-empty">✓ No active alerts</div>';
        return;
    }

    list.innerHTML = currentAlerts.map(a => `
        <div class="alert-card alert-card-${a.severity}" onclick="alertNavigate('${a.tab}')">
            <span class="alert-card-icon">${a.severity === 'critical' ? '🔴' : '🟡'}</span>
            <div class="alert-card-body">
                <div class="alert-card-msg">${esc(a.message)}</div>
                <div class="alert-card-detail">${esc(a.detail)}</div>
            </div>
            <button class="alert-card-dismiss" onclick="dismissAlert('${a.id}', event)" title="Dismiss">×</button>
        </div>
    `).join('');
}

function updateAlertBadge() {
    const badge = document.getElementById('alertBadge');
    const bell = document.getElementById('alertBellBtn');
    const count = currentAlerts.length;

    if (count > 0) {
        badge.style.display = 'flex';
        badge.textContent = count > 9 ? '9+' : count;
        bell.classList.add('has-alerts');
    } else {
        badge.style.display = 'none';
        bell.classList.remove('has-alerts');
    }
}

function toggleAlertPanel() {
    const panel = document.getElementById('alertPanel');
    alertPanelOpen = !alertPanelOpen;
    panel.style.display = alertPanelOpen ? 'block' : 'none';
}

function alertNavigate(tab) {
    switchTab(tab);
    toggleAlertPanel();
}

function dismissAlert(id, event) {
    event.stopPropagation();
    dismissedAlerts.add(id);
    currentAlerts = currentAlerts.filter(a => a.id !== id);
    renderAlertPanel();
    updateAlertBadge();
}

// ─── Keyboard Help ───────────────────────────────
function toggleKbdHelp() {
    kbdHelpOpen = !kbdHelpOpen;
    document.getElementById('kbdHelp').style.display = kbdHelpOpen ? 'block' : 'none';
}

// ─── Toast ───────────────────────────────────────
function toast(type, message) {
    const container = document.getElementById('toastContainer');
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    const icons = { success: '✓', error: '✗', info: '●' };
    el.innerHTML = `<span>${icons[type] || '●'}</span> <span>${esc(message)}</span>`;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = '0.3s'; setTimeout(() => el.remove(), 300); }, 4000);
}

// ─── Helpers ─────────────────────────────────────
function trunc(s, n) { return !s ? '' : s.length > n ? s.slice(0, n) + '…' : s; }
function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function emptyRow(cols) { return `<tr><td colspan="${cols}" class="c-dim" style="text-align:center;padding:28px">Tidak ada data</td></tr>`; }

function updateTimestamp(ts) {
    if (!ts) { document.getElementById('lastUpdate').textContent = '—'; return; }
    document.getElementById('lastUpdate').textContent = timeAgo(new Date(ts));
}

function timeAgo(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 5) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}d ago`;
}

function setFooter(ok, msg) {
    const f = document.getElementById('footer');
    f.className = ok ? 'foot foot-ok' : 'foot foot-err';
    document.getElementById('footerStatus').textContent = msg;
}
function showError(msg) { const b = document.getElementById('errorBar'); b.classList.add('show'); document.getElementById('errorText').textContent = msg; }
function hideError() { document.getElementById('errorBar').classList.remove('show'); }

// ─── Resource Monitoring ─────────────────────────
let cpuHistory = {};
let memHistory = {};

async function fetchResources() {
    try {
        const resp = await fetch('/api/resources');
        if (resp.status === 401) { window.location.href = '/login'; return; }
        const data = await resp.json();
        if (!data.ok) {
            document.getElementById('tabRes').textContent = '✗';
            return;
        }
        renderResources(data);
    } catch (err) {
        document.getElementById('tabRes').textContent = '✗';
    }
}

function renderResources(data) {
    const { server, stats, containers } = data;

    document.getElementById('tabRes').textContent = (stats || []).length;

    const grid = document.getElementById('resGrid');
    if (server) {
        const memPerc = server.mem_total ? ((server.mem_used / server.mem_total) * 100).toFixed(1) : 0;
        const diskPerc = server.disk_total ? ((server.disk_used / server.disk_total) * 100).toFixed(1) : 0;

        // Track CPU load history for sparkline
        if (!cpuHistory['_server']) cpuHistory['_server'] = [];
        cpuHistory['_server'].push(server.load_1m || 0);
        if (cpuHistory['_server'].length > 20) cpuHistory['_server'].shift();

        const maxLoad = Math.max(...cpuHistory['_server'], 1);
        const sparklineHTML = cpuHistory['_server'].map(v =>
            `<div class="sparkline-bar" style="height:${Math.max(4, (v / maxLoad) * 100)}%"></div>`
        ).join('');

        grid.innerHTML = `
            <div class="res-card">
                <div class="res-card-title">CPU Load</div>
                <div class="res-card-sparkline">${sparklineHTML}</div>
                <div class="res-card-val">${server.load_1m?.toFixed(2) || '—'}</div>
                <div class="res-card-sub">${server.cpu_cores || 0} cores · 5m: ${server.load_5m?.toFixed(2) || '—'} · 15m: ${server.load_15m?.toFixed(2) || '—'}</div>
            </div>
            <div class="res-card">
                <div class="res-card-title">Memory</div>
                <div class="res-bar-wrap"><div class="res-bar ${barColor(memPerc)}" style="width:${memPerc}%"></div></div>
                <div class="res-card-val">${memPerc}%</div>
                <div class="res-card-sub">${formatBytes(server.mem_used)} / ${formatBytes(server.mem_total)}</div>
            </div>
            <div class="res-card">
                <div class="res-card-title">Disk</div>
                <div class="res-bar-wrap"><div class="res-bar ${barColor(diskPerc)}" style="width:${diskPerc}%"></div></div>
                <div class="res-card-val">${diskPerc}%</div>
                <div class="res-card-sub">${formatBytes(server.disk_used)} / ${formatBytes(server.disk_total)}</div>
            </div>
            <div class="res-card">
                <div class="res-card-title">Running Containers</div>
                <div class="res-card-val">${(stats || []).length}</div>
                <div class="res-card-sub">${(containers || []).filter(c => c.state === 'running').length} running / ${(containers || []).length} total</div>
            </div>
        `;
    } else {
        grid.innerHTML = '<div class="res-card" style="grid-column:1/-1;text-align:center;color:var(--text-muted)">Server info not available</div>';
    }

    // Container stats table
    const tb = document.querySelector('#tbl-resources tbody');
    if (!stats || !stats.length) {
        tb.innerHTML = '<tr><td colspan="7" class="c-dim" style="text-align:center;padding:28px">No container stats available. Deploy the monitor-agent first.</td></tr>';
        return;
    }

    stats.sort((a, b) => (b.cpu_percent || 0) - (a.cpu_percent || 0));

    // Detect CPU/memory alerts from container stats
    const resourceAlerts = [];
    stats.forEach(s => {
        const cpu = s.cpu_percent || 0;
        const mem = s.mem_percent || 0;
        const name = s.label || s.name || 'container';

        if (cpu > 80) {
            resourceAlerts.push({
                id: `cpu-${s.name}`,
                severity: cpu > 95 ? 'critical' : 'warning',
                message: `High CPU: ${name}`,
                detail: `CPU usage at ${cpu.toFixed(1)}%`,
                tab: 'resources'
            });
        }
        if (mem > 80) {
            resourceAlerts.push({
                id: `mem-${s.name}`,
                severity: mem > 95 ? 'critical' : 'warning',
                message: `High Memory: ${name}`,
                detail: `Memory usage at ${mem.toFixed(1)}%`,
                tab: 'resources'
            });
        }
    });

    // Merge resource alerts with current alerts (avoid duplicates)
    const existingIds = new Set(currentAlerts.map(a => a.id));
    const newResourceAlerts = resourceAlerts.filter(a => !existingIds.has(a.id) && !dismissedAlerts.has(a.id));
    if (newResourceAlerts.length) {
        currentAlerts = [...currentAlerts, ...newResourceAlerts];
        renderAlertPanel();
        updateAlertBadge();
    }

    tb.innerHTML = stats.map(s => {
        const cpu = s.cpu_percent || 0;
        const mem = s.mem_percent || 0;
        const projectLabel = s.project
            ? `<span class="c-tag">${esc(s.project)}</span>`
            : (s.resource_type === 'system' ? '<span class="c-dim">system</span>' : '<span class="c-dim">—</span>');
        const envBadge = s.env ? ` <span class="c-dim" style="font-size:0.75em">${esc(s.env)}</span>` : '';
        const alertClass = (cpu > 80 || mem > 80) ? ' row-alert' : '';
        return `<tr class="data-row${alertClass}" data-search="${esc((s.label || s.name || '') + ' ' + (s.project || '') + ' ' + (s.env || ''))}">
            <td class="c-name">${esc(s.label || s.name)}</td>
            <td>${projectLabel}${envBadge}</td>
            <td>
                <div class="cpu-bar-wrap">
                    <div class="cpu-bar-mini"><div class="cpu-bar-mini-fill ${barColor(cpu)}" style="width:${Math.min(cpu, 100)}%"></div></div>
                    <span class="c-dim">${cpu.toFixed(1)}%</span>
                </div>
            </td>
            <td>
                <div class="cpu-bar-wrap">
                    <div class="cpu-bar-mini"><div class="cpu-bar-mini-fill ${barColor(mem)}" style="width:${Math.min(mem, 100)}%"></div></div>
                    <span class="c-dim">${mem.toFixed(1)}% · ${esc(s.mem_used || '—')}</span>
                </div>
            </td>
            <td class="c-dim">${esc(s.net_in || '—')} ↓ / ${esc(s.net_out || '—')} ↑</td>
            <td class="c-dim">${esc(s.block_read || '—')} ↓ / ${esc(s.block_write || '—')} ↑</td>
            <td class="c-dim">${esc(s.pids || '—')}</td>
        </tr>`;
    }).join('');
}

function barColor(pct) {
    if (pct >= 80) return 'res-bar-high';
    if (pct >= 50) return 'res-bar-med';
    return 'res-bar-low';
}

// ─── Format Bytes ────────────────────────────────
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0, size = typeof bytes === 'string' ? parseFloat(bytes) : bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return size.toFixed(1) + ' ' + units[i];
}
