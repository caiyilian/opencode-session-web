// ── OpenCode 会话查看器 — 前端逻辑 ──

// ── State ──
let sessions = [];
let currentSessionId = null;
let allDirectories = [];
let allSessions = [];
let allModels = [];       // 可用模型列表
let currentModel = '';    // 当前选中模型
let eventSource = null;
let currentDirectory = '';  // 当前会话的工作目录

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

  // Load available models
  try {
    const modelsData = await api('/api/available-models');
    if (modelsData.models) {
      allModels = modelsData.models;
      populateModelSelectors();
    }
  } catch (e) {
    // 静默失败，模型切换功能不可用
  }

  renderSidebar();
}

function populateModelSelectors() {
  // Populate all model <select> elements
  const selects = document.querySelectorAll('.model-select');
  for (const sel of selects) {
    const current = sel.value;
    sel.innerHTML = '<option value="">默认模型</option>';
    for (const m of allModels) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      if (m === current) opt.selected = true;
      sel.appendChild(opt);
    }
  }
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
  currentDirectory = s.directory || '';
  mainTitle.textContent = s.title || '未命名会话';
  mainInfo.textContent = `${s.model} · ${data.message_count} 条消息`;

  // 设置模型选择器
  currentModel = s.model;
  const modelSelect = document.getElementById('modelSelect');
  if (modelSelect) {
    // 看当前模型在不在列表中
    let found = false;
    for (const opt of modelSelect.options) {
      if (opt.value === s.model) { opt.selected = true; found = true; break; }
    }
    if (!found) {
      // 不在列表中则添加一个选项
      const opt = document.createElement('option');
      opt.value = s.model;
      opt.textContent = s.model + ' (当前)';
      opt.selected = true;
      modelSelect.appendChild(opt);
    }
  }

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

  // Show file button
  document.getElementById('fileBtn').style.display = 'block';

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
  document.getElementById('fileBtn').style.display = 'none';
  document.getElementById('filePanel').classList.remove('show');
  document.getElementById('fileBtn').classList.remove('active');
  filePanelOpen = false;
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
  const modelParam = currentModel ? '&model=' + encodeURIComponent(currentModel) : '';
  eventSource = new EventSource(`/api/sessions/${currentSessionId}/stream?message=${encodeURIComponent(text)}${modelParam}`);

  eventSource.addEventListener('thinking', (e) => {
    const el = document.getElementById(streamId + '_thinking');
    if (el) {
      let text = el.textContent;
      if (text.length < 2000) {
        el.textContent = text + e.data.replace(/\\n/g, '\n');
      }
      messagesArea.scrollTop = messagesArea.scrollHeight;
    }
  });

  eventSource.addEventListener('text', (e) => {
    const el = document.getElementById(streamId + '_text');
    if (el) {
      el.textContent += e.data.replace(/\\n/g, '\n');
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

// ── Phase 2: New Session Modal ──

function showNewSessionModal() {
  const modal = document.getElementById('newSessionModal');
  const dirSelect = document.getElementById('newSessionDir');
  // Populate directory list
  dirSelect.innerHTML = '';
  for (const d of allDirectories) {
    const opt = document.createElement('option');
    opt.value = d.path;
    opt.textContent = d.name + ' (' + d.session_count + ' 会话)';
    dirSelect.appendChild(opt);
  }
  // Also allow custom path
  const customOpt = document.createElement('option');
  customOpt.value = '__custom__';
  customOpt.textContent = '—— 输入自定义路径 ——';
  dirSelect.appendChild(customOpt);

  document.getElementById('newSessionMsg').value = '';
  document.getElementById('newSessionSubmit').disabled = false;
  modal.classList.add('show');
  setTimeout(() => document.getElementById('newSessionMsg').focus(), 100);
}

function closeNewSessionModal() {
  document.getElementById('newSessionModal').classList.remove('show');
}

function startNewSession() {
  const dirSelect = document.getElementById('newSessionDir');
  const msgInput = document.getElementById('newSessionMsg');
  const submitBtn = document.getElementById('newSessionSubmit');

  let directory = dirSelect.value;
  if (directory === '__custom__') {
    directory = prompt('请输入工作目录路径：');
    if (!directory) return;
  }
  const message = msgInput.value.trim();
  if (!message) { alert('请输入消息'); return; }

  submitBtn.disabled = true;
  closeNewSessionModal();

  // Switch to main area, show loading
  const messagesArea = document.getElementById('messagesArea');
  const mainTitle = document.getElementById('mainTitle');
  const mainInfo = document.getElementById('mainInfo');
  const inputArea = document.getElementById('inputArea');

  // Abort any existing stream
  if (eventSource) { eventSource.close(); eventSource = null; }

  currentSessionId = null;
  mainTitle.textContent = '新建会话...';
  mainInfo.textContent = directory;

  const streamId = 'stream_' + Date.now();
  messagesArea.innerHTML = `
    <div class="msg user">
      <div class="msg-avatar">U</div>
      <div class="msg-body">
        <div class="role-label">你 · 刚刚</div>
        <div class="content">${escHtml(message)}</div>
      </div>
    </div>
    <div class="msg assistant streaming" id="${streamId}">
      <div class="msg-avatar">AI</div>
      <div class="msg-body">
        <div class="role-label">AI · 思考中...</div>
        <div class="thinking-content" id="${streamId}_thinking"></div>
        <div class="content" id="${streamId}_text"></div>
        <div class="loading" id="${streamId}_loading" style="padding:10px"><div class="spinner"></div></div>
      </div>
    </div>`;
  messagesArea.scrollTop = messagesArea.scrollHeight;

  // Send POST via fetch + EventSource doesn't support POST, so use fetch with streaming
  const modelParam = currentModel ? '&model=' + encodeURIComponent(currentModel) : '';
  fetch('/api/sessions/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directory, message, model: currentModel || undefined }),
  }).then(async (response) => {
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || '请求失败');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const events = buffer.split('\n\n');
      buffer = events.pop() || ''; // keep incomplete event

      for (const block of events) {
        const lines = block.split('\n');
        let eventType = '';
        let data = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          else if (line.startsWith('data: ')) data = line.slice(6);
        }

        if (eventType === 'thinking') {
          const el = document.getElementById(streamId + '_thinking');
          if (el && el.textContent.length < 2000) {
            el.textContent += data.replace(/\\n/g, '\n');
            messagesArea.scrollTop = messagesArea.scrollHeight;
          }
        } else if (eventType === 'text') {
          const el = document.getElementById(streamId + '_text');
          if (el) {
            el.textContent += data.replace(/\\n/g, '\n');
            messagesArea.scrollTop = messagesArea.scrollHeight;
          }
        } else if (eventType === 'done') {
          const info = JSON.parse(data || '{}');
          const newId = info.session_id;

          // Remove loading, end streaming
          const loading = document.getElementById(streamId + '_loading');
          const msgEl = document.getElementById(streamId);
          if (loading) loading.remove();
          if (msgEl) msgEl.classList.remove('streaming');

          if (newId) {
            currentSessionId = newId;
            // Refresh session list and switch to new session
            const sessData = await api('/api/sessions?limit=200');
            allSessions = sessData.sessions;
            sessions = allSessions;
            renderSidebar();
            // Load the full session
            openSession(newId);
          } else {
            mainTitle.textContent = '新建会话';
            inputArea.classList.add('show');
          }
        } else if (eventType === 'error') {
          const loading = document.getElementById(streamId + '_loading');
          const msgEl = document.getElementById(streamId);
          if (loading) loading.remove();
          if (msgEl) msgEl.classList.remove('streaming');
          messagesArea.innerHTML += `<div class="empty-state"><p style="color:var(--accent3)">错误: ${escHtml(data)}</p></div>`;
          submitBtn.disabled = false;
        }
      }
    }
  }).catch((err) => {
    const loading = document.getElementById(streamId + '_loading');
    if (loading) loading.remove();
    messagesArea.innerHTML += `<div class="empty-state"><p style="color:var(--accent3)">错误: ${escHtml(err.message)}</p></div>`;
    submitBtn.disabled = false;
  });
}

// ── Phase 2: File tree ──

let filePanelOpen = false;

function toggleFilePanel() {
  filePanelOpen = !filePanelOpen;
  const panel = document.getElementById('filePanel');
  const btn = document.getElementById('fileBtn');
  panel.classList.toggle('show', filePanelOpen);
  btn.classList.toggle('active', filePanelOpen);
  if (filePanelOpen && currentDirectory) {
    loadFileTree(currentDirectory);
  }
}

async function loadFileTree(dirPath) {
  const tree = document.getElementById('fileTree');
  const pathLabel = document.getElementById('filePanelPath');
  pathLabel.textContent = dirPath;
  tree.innerHTML = '<div class="file-entry loading">加载中...</div>';

  try {
    const data = await api('/api/files?path=' + encodeURIComponent(dirPath));
    if (data.error) {
      tree.innerHTML = `<div class="file-entry loading">${escHtml(data.error)}</div>`;
      return;
    }
    renderFileEntries(tree, data.entries, dirPath);
  } catch (e) {
    tree.innerHTML = `<div class="file-entry loading">加载失败: ${escHtml(e.message)}</div>`;
  }
}

function renderFileEntries(container, entries, basePath) {
  let html = '';
  for (const e of entries) {
    const icon = e.type === 'dir' ? '📁' : getFileIcon(e.name);
    const sizeStr = e.type === 'file' ? fmtFileSize(e.size) : '';
    if (e.type === 'dir') {
      const childId = 'fl_' + basePath.replace(/[^a-zA-Z0-9]/g, '_') + '_' + e.name.replace(/[^a-zA-Z0-9]/g, '_');
      html += `<div class="file-entry dir" onclick="toggleDir(this, '${childId}', '${escHtmlAttr(basePath + '/' + e.name)}')">
        <span class="arrow" id="arr_${childId}">▶</span>
        <span class="icon">${icon}</span>
        <span class="name">${escHtml(e.name)}</span>
      </div>
      <div class="file-children" id="${childId}"></div>`;
    } else {
      html += `<div class="file-entry" title="${escHtmlAttr(basePath + '/' + e.name)}">
        <span class="icon">${icon}</span>
        <span class="name">${escHtml(e.name)}</span>
        <span class="file-size">${sizeStr}</span>
      </div>`;
    }
  }
  container.innerHTML = html;
}

async function toggleDir(el, childId, fullPath) {
  const arrow = document.getElementById('arr_' + childId);
  const children = document.getElementById(childId);
  if (children.classList.contains('show')) {
    children.classList.remove('show');
    arrow.classList.remove('open');
    return;
  }
  arrow.classList.add('open');
  if (children.children.length === 0) {
    children.innerHTML = '<div class="file-entry loading">加载中...</div>';
    try {
      const data = await api('/api/files?path=' + encodeURIComponent(fullPath));
      if (data.error) {
        children.innerHTML = `<div class="file-entry loading">${escHtml(data.error)}</div>`;
        return;
      }
      renderFileEntries(children, data.entries, fullPath);
    } catch (e) {
      children.innerHTML = `<div class="file-entry loading">加载失败</div>`;
    }
  }
  children.classList.add('show');
}

function getFileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const icons = {
    js: '📜', ts: '📘', py: '🐍', rs: '🦀', go: '🔵',
    java: '☕', cpp: '⚙️', c: '⚙️', h: '⚙️', hpp: '⚙️',
    html: '🌐', css: '🎨', scss: '🎨', json: '📋', yml: '📋', yaml: '📋',
    md: '📝', txt: '📄', xml: '📋', toml: '📋',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🖼️',
    zip: '📦', tar: '📦', gz: '📦', 7z: '📦',
    gitignore: '🙈', dockerfile: '🐳',
  };
  return icons[ext] || '📄';
}

function escHtmlAttr(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtFileSize(bytes) {
  if (!bytes) return '';
  if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB';
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
  if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return bytes + ' B';
}
