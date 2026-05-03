/* ─────────────────────────────────────────────────────────
   EnterpriseRAG — Professional UI JavaScript
   Voyage AI · Qdrant · BM25 · Cross-Encoder
───────────────────────────────────────────────────────── */

const state = { repositories: [], lastQueryResponse: null };
const renderedEventKeys = new Set();

/* ── Helpers ──────────────────────────────────────────── */
function esc(v) {
  return String(v ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function now() { return new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' }); }

function anchor(url, label, cls = '') {
  if (!url) return `<span class="${esc(cls)}">${esc(label)}</span>`;
  return `<a href="${esc(url)}" target="_blank" rel="noreferrer" class="${esc(cls)}">${esc(label)}</a>`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || 'GET',
    headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) {
    const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    addEvent('failed', msg);
    throw new Error(msg);
  }
  return data;
}

/* ── Tabs ─────────────────────────────────────────────── */
const TAB_MAP = {
  search: { nav: 'navSearch', panel: 'tabSearch', title: 'Code Search', sub: 'Hybrid semantic + keyword retrieval across your codebase' },
  repos:  { nav: 'navRepos',  panel: 'tabRepos',  title: 'Repositories', sub: 'Register and manage your Git repositories' },
  ingest: { nav: 'navIngest', panel: 'tabIngest', title: 'Ingestion',     sub: 'Clone, parse, and index your codebase' },
  activity:{ nav: 'navActivity', panel: 'tabActivity', title: 'Activity Log', sub: 'Real-time pipeline events and assistant steps' },
};

function switchTab(key) {
  for (const [k, cfg] of Object.entries(TAB_MAP)) {
    const nav = document.getElementById(cfg.nav);
    const panel = document.getElementById(cfg.panel);
    const active = k === key;
    nav.classList.toggle('active', active);
    panel.classList.toggle('active', active);
    if (active) {
      document.getElementById('pageTitle').textContent = cfg.title;
      document.getElementById('pageSub').textContent   = cfg.sub;
    }
  }
}

for (const [key, cfg] of Object.entries(TAB_MAP)) {
  document.getElementById(cfg.nav).addEventListener('click', () => switchTab(key));
}

/* ── Health ───────────────────────────────────────────── */
async function checkHealth() {
  const chip = document.getElementById('healthChip');
  const txt  = document.getElementById('healthText');
  try {
    const h = await api('/health');
    txt.textContent = `${h.vector_store} · ${h.graph_store}`;
    chip.className = 'health-chip ok';
  } catch {
    txt.textContent = 'Offline';
    chip.className = 'health-chip err';
  }
}

/* ── Repositories ─────────────────────────────────────── */
async function loadRepositories() {
  state.repositories = await api('/repositories');
  renderRepoList();
  syncRepoSelects();
}

function renderRepoList() {
  const el = document.getElementById('repoList');
  if (!state.repositories.length) {
    el.innerHTML = `<div class="empty-state">
      <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1H8a3 3 0 00-3 3v1.5a1.5 1.5 0 01-3 0V6z" clip-rule="evenodd"/></svg>
      <p>No repositories yet. Add one above.</p></div>`;
    return;
  }
  el.innerHTML = state.repositories.map(repo => {
    const statusTag = {
      indexed: 'tag-indexed', indexing: 'tag-indexing', failed: 'tag-failed'
    }[repo.indexing_status] || 'tag-default';
    const err = repo.last_error ? `<div style="font-size:11px;color:var(--red);margin-top:6px">${esc(repo.last_error)}</div>` : '';
    return `<div class="repo-card">
      <div class="repo-card-left">
        <div class="repo-name">${esc(repo.name)}</div>
        <div class="repo-url">${esc(repo.git_url)}</div>
        <div class="repo-tags">
          <span class="repo-tag ${statusTag}">${esc(repo.indexing_status)}</span>
          <span class="repo-tag tag-default">${esc(repo.default_branch)}</span>
          <span class="repo-tag tag-chunks">${repo.chunk_count} chunks</span>
        </div>
        ${err}
      </div>
      <div class="repo-card-right">
        <button class="btn btn-danger btn-sm" data-delete-repo="${esc(repo.id)}">Remove</button>
      </div>
    </div>`;
  }).join('');
}

function syncRepoSelects() {
  const opts = '<option value="">All repositories</option>' +
    state.repositories.map(r =>
      `<option value="${esc(r.id)}">${esc(r.name)} (${esc(r.indexing_status)}, ${r.chunk_count} chunks)</option>`
    ).join('');
  document.getElementById('repoSelectSearch').innerHTML = opts;
  document.getElementById('repoSelectIngest').innerHTML =
    state.repositories.map(r =>
      `<option value="${esc(r.id)}">${esc(r.name)}</option>`
    ).join('') || '<option value="">No repositories</option>';
}

document.getElementById('refreshRepos').addEventListener('click', loadRepositories);

document.getElementById('repoList').addEventListener('click', async e => {
  const btn = e.target.closest('[data-delete-repo]');
  if (!btn) return;
  const id = btn.getAttribute('data-delete-repo');
  btn.disabled = true;
  await api(`/repositories/${id}`, { method: 'DELETE' });
  addEvent('completed', 'Repository removed.');
  await loadRepositories();
});

document.getElementById('repoForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = document.getElementById('registerBtn');
  btn.disabled = true;
  btn.textContent = 'Registering…';
  const fd = new FormData(e.currentTarget);
  const payload = {
    name: fd.get('name'),
    git_url: fd.get('git_url'),
    default_branch: fd.get('default_branch') || 'main',
    visibility: fd.get('visibility'),
    credential_env_var: fd.get('credential_env_var') || null,
  };
  try {
    const repo = await api('/repositories', { method: 'POST', body: payload });
    addEvent('completed', `Registered "${repo.name}". Confirm ingestion to index it.`);
    e.currentTarget.reset();
    await loadRepositories();
    // Auto-request permission
    const job = await api(`/repositories/${repo.id}/ingest`, { method: 'POST', body: { confirm: false } });
    renderEvents(job.assistant_events);
  } catch {}
  btn.disabled = false;
  btn.innerHTML = `<svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16"><path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd"/></svg> Register Repository`;
});

/* ── Ingestion ────────────────────────────────────────── */
function selectedIngestRepo() { return document.getElementById('repoSelectIngest').value; }

async function ingest(confirm) {
  const repoId = selectedIngestRepo();
  if (!repoId) { addEvent('failed', 'Select a repository first.'); return; }
  addEvent('planning', confirm ? 'Starting confirmed ingestion…' : 'Requesting permission…');
  const job = await api(`/repositories/${repoId}/ingest`, { method: 'POST', body: { confirm } });
  renderEvents(job.assistant_events);
  renderProgress(job);
  if (job.status === 'running') pollIngestion(job.id, repoId);
  await loadRepositories();
}

async function pollIngestion(jobId, repoId) {
  let done = false;
  while (!done) {
    await sleep(1200);
    const job = await api(`/ingestions/${jobId}`);
    renderProgress(job);
    renderEvents(job.assistant_events);
    done = job.status === 'completed' || job.status === 'failed';
    if (done) { await loadRepositories(); }
  }
}

function renderProgress(job) {
  const pct = Math.max(0, Math.min(100, job.progress_percent || 0));
  document.getElementById('ingestFill').style.width = `${pct}%`;
  document.getElementById('ingestPct').textContent = `${pct}%`;
  document.getElementById('ingestStatusLabel').textContent = `${job.status}: ${job.current_step || ''}`;
}

document.getElementById('requestIngest').addEventListener('click', () => ingest(false));
document.getElementById('confirmIngest').addEventListener('click', () => ingest(true));

document.getElementById('inspectGraph').addEventListener('click', async () => {
  const repoId = selectedIngestRepo();
  if (!repoId) { addEvent('failed', 'Select a repository first.'); return; }
  const graph = await api(`/repositories/${repoId}/graph`);
  const out = document.getElementById('graphOutput');
  out.style.display = 'block';
  if (!graph.symbols.length) {
    out.textContent = 'No graph symbols indexed yet. Confirm ingestion first.';
    return;
  }
  out.textContent = JSON.stringify(graph, null, 2);
});

/* ── Pipeline strip ───────────────────────────────────── */
const STEP_IDS = {
  planning: 'ps-planning', searching: 'ps-searching',
  expanding_graph: 'ps-searching', reranking: 'ps-reranking',
  validating_citations: 'ps-reranking', synthesizing: 'ps-synthesizing',
  completed: 'ps-completed',
};

function resetPipeline() {
  document.querySelectorAll('.pipeline-step').forEach(el => {
    el.classList.remove('active', 'done');
  });
}

function activateStep(type) {
  const id = STEP_IDS[type];
  if (!id) return;
  const order = ['ps-planning','ps-searching','ps-reranking','ps-synthesizing','ps-completed'];
  const idx = order.indexOf(id);
  order.forEach((sid, i) => {
    const el = document.getElementById(sid);
    if (!el) return;
    el.classList.remove('active','done');
    if (i < idx) el.classList.add('done');
    else if (i === idx) el.classList.add('active');
  });
}

/* ── Query / Search via SSE ───────────────────────────── */
document.getElementById('queryForm').addEventListener('submit', async e => {
  e.preventDefault();
  const question = document.getElementById('searchInput').value.trim();
  if (!question) return;

  const repoId = document.getElementById('repoSelectSearch').value;
  const topK   = parseInt(document.getElementById('topKSelect').value, 10);
  const btn = document.getElementById('searchBtn');

  // Reset UI
  btn.disabled = true;
  btn.querySelector('.search-btn-label').textContent = 'Searching…';
  document.getElementById('pipelineStrip').style.display = 'flex';
  document.getElementById('resultsArea').style.display = 'none';
  document.getElementById('citationsCard').style.display = 'none';
  document.getElementById('chunksCard').style.display   = 'none';
  document.getElementById('answerBody').innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  resetPipeline();

  const citations = [];
  const chunks    = [];

  try {
    const resp = await fetch('/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, repo_ids: repoId ? [repoId] : [], top_k: topK }),
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    document.getElementById('resultsArea').style.display = 'block';

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop(); // keep incomplete last chunk

      for (const part of parts) {
        if (!part.trim()) continue;
        const lines = part.split('\n');
        let eventType = 'message';
        let dataStr = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim();
          else if (line.startsWith('data: ')) dataStr = line.slice(6).trim();
        }
        if (!dataStr) continue;
        let payload;
        try { payload = JSON.parse(dataStr); } catch { continue; }

        if (eventType === 'step') {
          activateStep(payload.type);
          addEvent(payload.type, payload.message);
        } else if (eventType === 'citation') {
          citations.push(payload);
          renderCitations(citations);
        } else if (eventType === 'chunk') {
          chunks.push(payload);
          renderChunks(chunks);
        } else if (eventType === 'answer') {
          renderAnswer(payload.text);
        } else if (eventType === 'error') {
          addEvent('failed', payload.message);
          document.getElementById('answerBody').innerHTML = `<p style="color:var(--red)">${esc(payload.message)}</p>`;
        }
      }
    }
  } catch (err) {
    addEvent('failed', err.message);
    document.getElementById('answerBody').innerHTML = `<p style="color:var(--red)">${esc(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    btn.querySelector('.search-btn-label').textContent = 'Ask';
    // Mark pipeline done
    activateStep('completed');
    switchTab('activity');
    setTimeout(() => switchTab('search'), 80);
  }
});

/* ── Render helpers ───────────────────────────────────── */
function renderAnswer(text) {
  // Convert [N] citations to styled inline refs
  const formatted = esc(text).replace(/\[(\d+)\]/g,
    '<sup style="color:var(--accent2);font-weight:700;cursor:default" title="Citation $1">[$1]</sup>'
  );
  document.getElementById('answerBody').innerHTML = formatted;
}

function renderCitations(list) {
  const card = document.getElementById('citationsCard');
  const container = document.getElementById('citationsList');
  card.style.display = 'block';
  document.getElementById('citationCount').textContent = list.length;
  container.innerHTML = list.map((c, i) => {
    const label = c.url ? `${c.file}` : `${c.repo} / ${c.file}`;
    return `<div class="citation-item">
      <div class="citation-num">${i + 1}</div>
      <div class="citation-body">
        ${anchor(c.url, label, 'citation-link')}
        <div class="citation-meta">${esc(c.repo)} · lines ${c.start_line}–${c.end_line}</div>
      </div>
      ${c.url ? `<span class="citation-badge">View Source ↗</span>` : ''}
    </div>`;
  }).join('');
}

function renderChunks(list) {
  const card = document.getElementById('chunksCard');
  const container = document.getElementById('chunksList');
  card.style.display = 'block';
  document.getElementById('chunkCount').textContent = list.length;
  container.innerHTML = list.map(c => {
    const scorePct = Math.min(100, Math.abs(c.score) * 100).toFixed(0);
    const fileLabel = `${c.repo_name}/${c.file_path}:${c.start_line}-${c.end_line}`;
    const sources = (c.retrieval_sources || []).map(s =>
      `<span class="chunk-source-tag">${esc(s)}</span>`).join('');
    return `<div class="chunk-item">
      <div class="chunk-top">
        ${anchor(c.url, fileLabel, 'chunk-link') || `<span class="chunk-link-nourl">${esc(fileLabel)}</span>`}
        <div class="chunk-score-bar">
          <span class="score-value">${c.score.toFixed(3)}</span>
          <div class="score-pill"><div class="score-fill" style="width:${scorePct}%"></div></div>
        </div>
      </div>
      <div class="chunk-meta">${sources}<span>${esc(c.summary)}</span></div>
    </div>`;
  }).join('');
}

/* ── Events feed ──────────────────────────────────────── */
const EVENT_ICONS = {
  completed:   { cls: 'event-icon--completed', svg: '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>' },
  failed:      { cls: 'event-icon--failed',    svg: '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>' },
  planning:    { cls: 'event-icon--planning',  svg: '<path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z"/>' },
  searching:   { cls: 'event-icon--searching', svg: '<path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/>' },
  reranking:   { cls: 'event-icon--reranking', svg: '<path d="M5 4a1 1 0 00-2 0v7.268a2 2 0 000 3.464V16a1 1 0 102 0v-1.268a2 2 0 000-3.464V4zM11 4a1 1 0 10-2 0v1.268a2 2 0 000 3.464V16a1 1 0 102 0V8.732a2 2 0 000-3.464V4zM16 3a1 1 0 011 1v7.268a2 2 0 010 3.464V16a1 1 0 11-2 0v-1.268a2 2 0 010-3.464V4a1 1 0 011-1z"/>' },
  synthesizing:{ cls: 'event-icon--synthesizing', svg: '<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>' },
};

function addEvent(type, message) {
  const key = `${type}:${message}`;
  if (renderedEventKeys.has(key)) return;
  renderedEventKeys.add(key);

  const feed = document.getElementById('eventsFeed');
  const cfg = EVENT_ICONS[type] || { cls: 'event-icon--default', svg: '<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 000 16zm-.93-9.412l-1 4.705a.75.75 0 001.458.31l1-4.705A.75.75 0 0017.07.588z" clip-rule="evenodd"/>' };
  const item = document.createElement('div');
  item.className = 'event-item';
  item.innerHTML = `
    <div class="event-icon ${cfg.cls}"><svg viewBox="0 0 20 20" fill="currentColor">${cfg.svg}</svg></div>
    <div class="event-body">
      <div class="event-type">${esc(type)}</div>
      <div class="event-msg">${esc(message)}</div>
    </div>
    <div class="event-time">${now()}</div>`;
  feed.prepend(item);
}

function renderEvents(events) {
  for (const ev of events || []) addEvent(ev.type, ev.message);
}

document.getElementById('clearEvents').addEventListener('click', () => {
  document.getElementById('eventsFeed').innerHTML = '';
  renderedEventKeys.clear();
});

/* ── Auto-resize textarea ─────────────────────────────── */
const ta = document.getElementById('searchInput');
ta.addEventListener('input', () => {
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
});
ta.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('queryForm').requestSubmit();
  }
});

/* ── Boot ─────────────────────────────────────────────── */
async function boot() {
  await checkHealth();
  await loadRepositories();
}

boot().catch(err => addEvent('failed', err.message));
