"""
Local Dashboard — lightweight HTML dashboard served from the agent's HTTP server.

Serves a single-page app at /dashboard that polls /api/state every 2 seconds.
All rendering is vanilla HTML/CSS/JS — no frameworks.
"""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SKY Local Agent — Control Tower</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #242736;
    --border: #2e3148;
    --text: #e4e6f0;
    --text-dim: #8b8fa3;
    --green: #22c55e;
    --blue: #3b82f6;
    --yellow: #eab308;
    --red: #ef4444;
    --gray: #6b7280;
    --radius: 10px;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }

  /* ── Header ─────────────────────────────────────────────────── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 28px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.3px;
  }
  .logo-dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    background: var(--gray);
    transition: background 0.3s;
  }
  .version {
    color: var(--text-dim);
    font-size: 12px;
    font-weight: 400;
    background: var(--surface2);
    padding: 3px 8px;
    border-radius: 6px;
  }
  .header-right { display: flex; align-items: center; gap: 12px; }
  .btn {
    padding: 7px 14px;
    border-radius: 7px;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--text);
    font-size: 13px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn:hover { background: var(--border); }
  .btn-primary {
    background: var(--blue);
    border-color: var(--blue);
    color: #fff;
  }
  .btn-primary:hover { background: #2563eb; }

  /* ── Layout ──────────────────────────────────────────────────── */
  main {
    max-width: 960px;
    margin: 0 auto;
    padding: 28px 20px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  /* ── Cards ──────────────────────────────────────────────────── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .card-header {
    padding: 14px 18px;
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
  }
  .card-body { padding: 18px; }

  /* ── Status Row ─────────────────────────────────────────────── */
  .status-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
  }
  .stat-item {
    background: var(--surface2);
    border-radius: 8px;
    padding: 14px 16px;
  }
  .stat-label {
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin-bottom: 6px;
  }
  .stat-value {
    font-size: 18px;
    font-weight: 700;
  }
  .stat-value.green { color: var(--green); }
  .stat-value.blue  { color: var(--blue); }
  .stat-value.yellow { color: var(--yellow); }
  .stat-value.red   { color: var(--red); }
  .stat-value.gray  { color: var(--gray); }

  /* ── Active Job ─────────────────────────────────────────────── */
  .job-panel { display:flex; flex-direction:column; gap:12px; }
  .job-name { font-size: 16px; font-weight: 600; }
  .progress-bar {
    height: 8px;
    background: var(--surface2);
    border-radius: 4px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: var(--blue);
    border-radius: 4px;
    transition: width 0.4s ease;
  }
  .job-meta {
    display: flex;
    gap: 24px;
    font-size: 13px;
    color: var(--text-dim);
  }
  .job-meta span strong { color: var(--text); }
  .no-job {
    color: var(--text-dim);
    font-style: italic;
    padding: 8px 0;
  }

  /* ── History Table ──────────────────────────────────────────── */
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left;
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 10px 12px;
    font-size: 13px;
    border-bottom: 1px solid var(--border);
  }
  tr:last-child td { border-bottom: none; }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge-success { background: #052e16; color: var(--green); }
  .badge-failed  { background: #2a0a0a; color: var(--red); }

  /* ── Logs ───────────────────────────────────────────────────── */
  #logs-content {
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 12px;
    line-height: 1.7;
    color: var(--text-dim);
    max-height: 260px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    padding: 4px 0;
  }
  #logs-content .log-time { color: #4b5563; }
  #logs-content .log-info { color: var(--blue); }
  #logs-content .log-error { color: var(--red); }
  #logs-content .log-warn { color: var(--yellow); }

  /* ── Health ─────────────────────────────────────────────────── */
  .health-grid {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
  }
  .health-item {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--surface2);
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
  }
  .health-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
  }
  .health-dot.ok { background: var(--green); }
  .health-dot.warn { background: var(--yellow); }
  .health-dot.err { background: var(--red); }
  .health-dot.unknown { background: var(--gray); }

  /* ── Bonus Buttons ──────────────────────────────────────────── */
  .actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  /* ── Scrollbar ──────────────────────────────────────────────── */
  ::-webkit-scrollbar { width:6px; }
  ::-webkit-scrollbar-track { background: var(--surface); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius:3px; }

  /* ── Pulse animation ────────────────────────────────────────── */
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .pulse { animation: pulse 2s ease-in-out infinite; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-dot" id="hdr-dot"></div>
    <span>SKY Local Agent</span>
    <span class="version" id="hdr-version">v—</span>
  </div>
  <div class="header-right">
    <span id="hdr-status" style="font-size:13px;color:var(--text-dim)">Connecting…</span>
    <button class="btn" onclick="window.open('https://skydatamigration.com','_blank')">Open Workspace</button>
  </div>
</header>

<main>

  <!-- Agent Info -->
  <div class="card">
    <div class="card-header">Agent Info</div>
    <div class="card-body">
      <div class="status-grid">
        <div class="stat-item">
          <div class="stat-label">Status</div>
          <div class="stat-value" id="agent-status">—</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Connected User</div>
          <div class="stat-value" id="agent-user" style="font-size:14px">—</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Project</div>
          <div class="stat-value" id="agent-project" style="font-size:14px">—</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Last Heartbeat</div>
          <div class="stat-value" id="agent-heartbeat" style="font-size:14px">—</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Active Job -->
  <div class="card">
    <div class="card-header">Active Job</div>
    <div class="card-body">
      <div class="job-panel" id="active-job">
        <div class="no-job">No active job</div>
      </div>
    </div>
  </div>

  <!-- Job History -->
  <div class="card">
    <div class="card-header">Job History</div>
    <div class="card-body" style="padding:0">
      <table>
        <thead>
          <tr>
            <th>Job</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Timestamp</th>
          </tr>
        </thead>
        <tbody id="history-body">
          <tr><td colspan="4" style="color:var(--text-dim);font-style:italic;padding:18px 12px">No jobs yet</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Health + Actions -->
  <div class="card">
    <div class="card-header">Health & Actions</div>
    <div class="card-body" style="display:flex;flex-direction:column;gap:16px">
      <div class="health-grid" id="health-grid">
        <div class="health-item"><div class="health-dot unknown"></div>HTTP API</div>
        <div class="health-item"><div class="health-dot unknown"></div>SAP Connection</div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" id="btn-test-sap" onclick="testSapConnection()">Test SAP Connection</button>
        <button class="btn" id="btn-sample" onclick="runSampleExtraction()">Run Sample Extraction</button>
      </div>
    </div>
  </div>

  <!-- Logs -->
  <div class="card" id="logs-section">
    <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
      <span>Logs</span>
      <button class="btn" style="font-size:11px;padding:4px 10px" onclick="clearLogs()">Clear</button>
    </div>
    <div class="card-body">
      <div id="logs-content">Waiting for data…</div>
    </div>
  </div>

</main>

<script>
const API = '';  // same origin
let logs = [];
const MAX_LOGS = 200;

const stateColorMap = {
  starting: 'gray', online: 'green', idle: 'yellow',
  running_job: 'blue', error: 'red', offline: 'gray',
};
const stateLabel = {
  starting: 'Starting…', online: 'Online', idle: 'Idle',
  running_job: 'Running Job', error: 'Error', offline: 'Offline',
};

function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

function formatTimestamp(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
}

function updateUI(data) {
  const s = data.state || {};
  const j = data.jobs || {};
  const state = s.state || 'offline';
  const color = stateColorMap[state] || 'gray';

  // Header
  document.getElementById('hdr-dot').style.background = `var(--${color})`;
  document.getElementById('hdr-dot').classList.toggle('pulse', state === 'running_job');
  document.getElementById('hdr-version').textContent = 'v' + (data.version || '—');
  document.getElementById('hdr-status').textContent = stateLabel[state] || state;

  // Agent Info
  const statusEl = document.getElementById('agent-status');
  statusEl.textContent = stateLabel[state] || state;
  statusEl.className = 'stat-value ' + color;
  if (state === 'error' && s.error_message) {
    statusEl.textContent = s.error_message;
  }

  document.getElementById('agent-user').textContent = s.connected_user || '—';
  document.getElementById('agent-project').textContent = s.connected_project || '—';
  document.getElementById('agent-heartbeat').textContent = formatTime(s.last_heartbeat);

  // Active Job
  const jobPanel = document.getElementById('active-job');
  const job = j.active_job;
  if (job) {
    jobPanel.innerHTML = `
      <div class="job-name">${esc(job.name)}</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${job.progress}%"></div></div>
      <div class="job-meta">
        <span>Progress: <strong>${job.progress}%</strong></span>
        <span>Records: <strong>${(job.records_processed || 0).toLocaleString()}</strong></span>
        <span>Errors: <strong>${job.errors_count || 0}</strong></span>
        <span>Duration: <strong>${job.duration || '—'}</strong></span>
      </div>`;
  } else {
    jobPanel.innerHTML = '<div class="no-job">No active job</div>';
  }

  // History
  const hist = j.history || [];
  const tbody = document.getElementById('history-body');
  if (hist.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-dim);font-style:italic;padding:18px 12px">No jobs yet</td></tr>';
  } else {
    tbody.innerHTML = hist.map(h => `<tr>
      <td>${esc(h.name)}</td>
      <td><span class="badge badge-${h.status === 'success' ? 'success' : 'failed'}">${h.status}</span></td>
      <td>${h.duration || '—'}</td>
      <td>${formatTimestamp(h.finished_at)}</td>
    </tr>`).join('');
  }

  // Health
  const health = data.health || {};
  const hgrid = document.getElementById('health-grid');
  hgrid.innerHTML = `
    <div class="health-item"><div class="health-dot ${health.http_api ? 'ok' : 'err'}"></div>HTTP API</div>
    <div class="health-item"><div class="health-dot ${health.sap_connection === true ? 'ok' : health.sap_connection === false ? 'err' : 'unknown'}"></div>SAP Connection</div>
  `;

  // Logs
  if (data.logs && data.logs.length) {
    data.logs.forEach(l => addLog(l));
  }
}

function addLog(line) {
  logs.push(line);
  if (logs.length > MAX_LOGS) logs.shift();
  renderLogs();
}

function renderLogs() {
  const el = document.getElementById('logs-content');
  el.innerHTML = logs.map(l => {
    let cls = '';
    if (l.includes('ERROR')) cls = 'log-error';
    else if (l.includes('WARN')) cls = 'log-warn';
    else if (l.includes('INFO') || l.includes('JOB') || l.includes('NOTIFY')) cls = 'log-info';
    const timePart = l.substring(0, 8);
    const rest = l.substring(8);
    return `<span class="log-time">${esc(timePart)}</span><span class="${cls}">${esc(rest)}</span>`;
  }).join('\n');
  el.scrollTop = el.scrollHeight;
}

function clearLogs() {
  logs = [];
  document.getElementById('logs-content').textContent = 'Logs cleared';
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── API Calls ───────────────────────────────────────────────

async function poll() {
  try {
    const res = await fetch(API + '/api/state');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    updateUI(data);
  } catch (e) {
    document.getElementById('hdr-status').textContent = 'Disconnected';
    document.getElementById('hdr-dot').style.background = 'var(--red)';
    document.getElementById('agent-status').textContent = 'Unreachable';
    document.getElementById('agent-status').className = 'stat-value red';
  }
}

async function testSapConnection() {
  const btn = document.getElementById('btn-test-sap');
  btn.textContent = 'Testing…';
  btn.disabled = true;
  try {
    const res = await fetch(API + '/api/test-sap');
    const data = await res.json();
    addLog(`${new Date().toLocaleTimeString().substring(0,8)}  [HEALTH]  SAP Connection: ${data.status} — ${data.systems_found || 0} systems found`);
  } catch (e) {
    addLog(`${new Date().toLocaleTimeString().substring(0,8)}  [ERROR]   SAP test failed: ${e.message}`);
  } finally {
    btn.textContent = 'Test SAP Connection';
    btn.disabled = false;
  }
}

async function runSampleExtraction() {
  const btn = document.getElementById('btn-sample');
  btn.textContent = 'Starting…';
  btn.disabled = true;
  try {
    const res = await fetch(API + '/api/sample-extraction', { method: 'POST' });
    const data = await res.json();
    addLog(`${new Date().toLocaleTimeString().substring(0,8)}  [INFO]    Sample extraction queued: ${data.job_id || '?'}`);
  } catch (e) {
    addLog(`${new Date().toLocaleTimeString().substring(0,8)}  [ERROR]   Sample extraction failed: ${e.message}`);
  } finally {
    btn.textContent = 'Run Sample Extraction';
    btn.disabled = false;
  }
}

// Boot
poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""
