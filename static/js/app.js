// ── OpenCode 会话查看器 — 前端逻辑 ──

// ── State ──
let sessions = [];
let currentSessionId = null;
let allDirectories = [];
let allSessions = [];
let eventSource = null;

// ── API ──
async function api(path) {
  const res = await fetch(path);
  return res.json();
}

// ── Sidebar ──
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('show');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('show');
}

// ── Init ──
async function init() {
  // Load stats
  const stats = await api('/api/stats');
  document.getElementById('statsBar').innerHTML = `
    <span>&#128202; 会话 <span class="num">${stats.total_sessions}</span></span>
    <span>&#128193; 项目 <span class="num">${stats.total_projects}</span></span>
    <span>&#9889; Input <span class="num">${fmtTokens(stats.total_tokens_input)}</span></span>
    <span>&#9889; Output <span class="num">${fmtTokens(stats.total_tokens_output)}</span></span>
  `;
  document.getElementById('statsFooter').textContent = `共 ${stats.total_sessions} 个会话 · ${stats.total_projects} 个项目`;

  // Load directories
  const dirsData = await api('/api/directories');
  allDirectories = dirsData.directories;

  // Load all sessions
  const sessData = await api('/api/sessions?limit=200');
  allSessions = sessData.sessions;
  sessions = allSessions;

  renderSidebar();
}

// ── Render sidebar ──
function renderSidebar() {
  const container = document.getElementById('sessionList');
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  let filtered = sessions;
  if (q) {
    filtered = sessions.filter(s =>
      s.title.toLowerCase().includes(q) ||
      s.directory.toLowerCase().includes(q) ||
      s.model.toLowerCase().includes(q) ||
      s.project.toLowerCase().includes(q)
    );
  }

  // Group by directory
  const groups = {};
  for (const s of filtered) {
    if (!groups[s.directory]) groups[s.directory] = { path: s.directory, name: s.project, sessions: [] };
    groups[s.directory].sessions.push(s);
  }

  // Sort groups
  const sortedGroups = Object.values(groups).sort((a, b) => {
    const ma = Math.max(...a.sessions.map(s => s.time_updated_raw || 0));
    const mb = Math.max(...b.sessions.map(s => s.time_updated_raw || 0));
    return mb - ma;
  });

  let html = '';
  for (const g of sortedGroups) {
    const gid = 'grp_' + g.path.replace(/[^a-zA-Z0-9]/g, '_');
    // Sort sessions within group by time
    g.sessions.sort((a, b) => (b.time_updated_raw || 0) - (a.time_updated_raw || 0));
    html += `<div class="dir-group">
      <div class="dir-header" onclick="toggleGroup('${gid}')">
        <span class="arrow open" id="arr_${gid}">&#9654;</span>
        ${g.name} <span style="font-weight:400;color:var(--text-dim)">(${g.sessions.length})</span>
      </div>
      <div id="${gid}">`;
    for (const s of g.sessions) {
      const active = s.id === currentSessionId ? 'active' : '';
      html += `<div class="session-item ${active}" onclick="openSession('${s.id}')">
        <div class="title">${escHtml(s.title)}</div>
        <div class="meta">
          <span class="model">${s.model}</span>
          <span class="time">${s.time_updated}</span>
        </div>
      </div>`;
    }
    html += `</div></div>`;
  }

  if (!html) {
    html = '<div class="loading" style="padding:30px;text-align:center;color:var(--text-dim)">没有匹配的会话</div>';
  }

  container.innerHTML = html;
}

function toggleGroup(id) {
  const el = document.getElementById(id);
  const arrow = document.getElementById('arr_' + id);
  if (el.style.display === 'none') {
    el.style.display = '';
    arrow.classList.add('open');
  } else {
    el.style.display = 'none';
    arrow.classList.remove('open');
  }
}

// ── Search ──
let searchTimer;
function onSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(renderSidebar, 200);
}

// ── Open session ──
async function openSession(id) {
  currentSessionId = id;
  closeSidebar();
  renderSidebar();

  const mainTitle = document.getElementById('mainTitle');
  const mainInfo = document.getElementById('mainInfo');
  const messagesArea = document.getElementById('messagesArea');
  const backBtn = document.getElementById('backBtn');
  const inputArea = document.getElementById('inputArea');

  messagesArea.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  mainTitle.textContent = '加载中...';

  const data = await api(`/api/sessions/${id}`);

  if (data.error) {
    messagesArea.innerHTML = `<div class="empty-state"><p>${data.error}</p></div>`;
    return;
  }

  const s = data.session;
  mainTitle.textContent = s.title || '未命名会话';
  mainInfo.textContent = `${s.model} · ${s.message_count} 条消息`;

  let html = '';
  for (const m of data.messages) {
    const role = m.role === 'user' ? 'user' : m.role === 'assistant' ? 'assistant' : 'tool';
    const avatar = role === 'user' ? 'U' : role === 'assistant' ? 'AI' : 'T';
    const label = role === 'user' ? '你' : role === 'assistant' ? 'AI' : '工具';
    let metaLine = '';
    if (m.tokens && m.tokens.output) {
      metaLine = `<div class="meta-line">&#9889; ${fmtTokens(m.tokens.output)} output</div>`;
    }

    html += `<div class="msg ${role}">
      <div class="msg-avatar">${avatar}</div>
      <div class="msg-body">
        <div class="role-label">${label} · ${m.time_created}</div>
        <div class="content">${escHtml(m.content) || '(空)'}</div>
        ${metaLine}
      </div>
    </div>`;
  }

  messagesArea.innerHTML = html;
  messagesArea.scrollTop = messagesArea.scrollHeight;

  // Show input area (Phase 2)
  inputArea.classList.add('show');

  // Show back button on mobile
  if (window.innerWidth <= 768) {
    backBtn.style.display = 'block';
  }
}

function showList() {
  currentSessionId = null;
  document.getElementById('mainTitle').textContent = '选择一个会话';
  document.getElementById('mainInfo').textContent = '';
  document.getElementById('messagesArea').innerHTML = `
    <div class="empty-state">
      <div class="big-icon">&#9670;</div>
      <h2>OpenCode 会话查看器</h2>
      <p>从左侧选择一个会话查看对话历史。</p>
    </div>`;
  document.getElementById('backBtn').style.display = 'none';
  document.getElementById('sessionList').innerHTML = '';
  document.getElementById('inputArea').classList.remove('show');
  renderSidebar();
}

// ── Phase 2: Send message ──
async function sendMessage() {
  const textarea = document.getElementById('msgInput');
  const sendBtn = document.getElementById('sendBtn');
  const text = textarea.value.trim();
  if (!text || !currentSessionId) return;

  // Disable input
  textarea.value = '';
  textarea.disabled = true;
  sendBtn.disabled = true;

  // Abort any existing stream
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  // Add user message to chat
  const messagesArea = document.getElementById('messagesArea');
  messagesArea.innerHTML += `<div class="msg user">
    <div class="msg-avatar">U</div>
    <div class="msg-body">
      <div class="role-label">你 · 刚刚</div>
      <div class="content">${escHtml(text)}</div>
    </div>
  </div>`;

  // Add streaming placeholder
  const streamId = 'stream_' + Date.now();
  messagesArea.innerHTML += `<div class="msg assistant streaming" id="${streamId}">
    <div class="msg-avatar">AI</div>
    <div class="msg-body">
      <div class="role-label">AI · 思考中...</div>
      <div class="thinking-content" id="${streamId}_thinking"></div>
      <div class="content" id="${streamId}_text"></div>
      <div class="loading" id="${streamId}_loading" style="padding:10px"><div class="spinner"></div></div>
    </div>
  </div>`;
  messagesArea.scrollTop = messagesArea.scrollHeight;

  // Start SSE stream
  eventSource = new EventSource(`/api/sessions/${currentSessionId}/stream?message=${encodeURIComponent(text)}`);

  eventSource.addEventListener('thinking', (e) => {
    const el = document.getElementById(streamId + '_thinking');
    if (el) {
      // Keep growing the thinking content
      let text = el.textContent;
      if (text.length < 2000) {
        el.textContent = text + e.data;
      }
      messagesArea.scrollTop = messagesArea.scrollHeight;
    }
  });

  eventSource.addEventListener('text', (e) => {
    const el = document.getElementById(streamId + '_text');
    if (el) {
      el.textContent += e.data;
      messagesArea.scrollTop = messagesArea.scrollHeight;
    }
  });

  eventSource.addEventListener('done', (e) => {
    const loading = document.getElementById(streamId + '_loading');
    const msgEl = document.getElementById(streamId);
    if (loading) loading.remove();
    if (msgEl) msgEl.classList.remove('streaming');
    eventSource.close();
    eventSource = null;
    // Re-enable input
    textarea.disabled = false;
    sendBtn.disabled = false;
    textarea.focus();
  });

  eventSource.addEventListener('error', (e) => {
    const loading = document.getElementById(streamId + '_loading');
    const msgEl = document.getElementById(streamId);
    if (loading) loading.remove();
    if (msgEl) msgEl.classList.remove('streaming');
    eventSource.close();
    eventSource = null;
    textarea.disabled = false;
    sendBtn.disabled = false;
  });
}

// Handle Enter key in textarea
function onInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// ── Utils ──
function escHtml(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function fmtTokens(n) {
  if (!n) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toString();
}

// ── Start ──
init();
