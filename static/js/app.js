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
let compareMode = false;    // 对比模式
let compareIds = [];        // 选中的对比会话 ID 列表
const SESSION_CACHE = {};   // 会话详情缓存 { sessionId: data }

// ── API ──
async function api(path) {
  const res = await fetch(path);
  return res.json();
}

// ── Markdown rendering ──

// Render message parts into HTML
function renderParts(parts) {
  if (!parts || parts.length === 0) return '(空)';
  let html = '';
  for (const p of parts) {
    if (p.type === 'text') {
      html += renderMarkdown(p.text || '');
    } else if (p.type === 'reasoning') {
      if (p.text) {
        const id = 'reason_' + Math.random().toString(36).slice(2, 8);
        html += `<details class="thinking-block" id="${id}"><summary>💭 思考过程</summary><div class="thinking-text">${escHtml(p.text)}</div></details>`;
      }
    } else if (p.type === 'tool') {
      const cmd = (p.input || '').slice(0, 200);
      const desc = p.description || '';
      const output = p.output || '';
      const hidden = p.is_hidden;
      let toolHtml = `<div class="tool-call"><span class="tool-badge">🔧 ${escHtml(p.tool)}</span>`;
      if (desc) toolHtml += `<span class="tool-desc">${escHtml(desc)}</span>`;
      if (cmd) toolHtml += `<code class="tool-input">${escHtml(cmd)}</code>`;
      toolHtml += `</div>`;
      if (hidden) {
        toolHtml += `<div class="tool-result-hidden">📎 输出已隐藏</div>`;
      } else if (output) {
        const id = 'to_' + Math.random().toString(36).slice(2, 8);
        const isLong = output.length > 300;
        const preview = output.slice(0, 300);
        toolHtml += `<details class="tool-result-block" id="${id}"><summary>📦 输出${isLong ? ' (' + output.length + ' 字节)' : ''}</summary>
          <pre class="tool-result-content"><code>${escHtml(isLong ? preview + '\n...' : output)}</code></pre></details>`;
      }
      html += toolHtml;
    } else if (p.type === 'tool_result') {
      if (p.is_hidden) {
        html += `<div class="tool-result-hidden">📎 ${escHtml(p.tool_name)} — 输出已隐藏</div>`;
      } else if (p.content) {
        const id = 'tr_' + Math.random().toString(36).slice(2, 8);
        const content = typeof p.content === 'string' ? p.content : JSON.stringify(p.content, null, 2);
        const preview = content.slice(0, 300);
        const isLong = content.length > 300;
        html += `<details class="tool-result-block" id="${id}"><summary>📦 ${escHtml(p.tool_name)} 结果${isLong ? ' (' + content.length + ' 字节)' : ''}</summary>
          <pre class="tool-result-content"><code>${escHtml(isLong ? preview + '\n...' : content)}</code></pre></details>`;
      }
    } else if (p.type === 'step-finish') {
      const tokens = p.tokens || {};
      html += `<div class="step-meta">⚡ ${tokens.total || 0} tokens · $${(p.cost || 0).toFixed(6)}</div>`;
    }
  }
  return html || '(空)';
}

// Configure marked with highlight.js
if (typeof marked !== 'undefined' && typeof hljs !== 'undefined') {
  marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
      if (lang && hljs.getLanguage(lang)) {
        try { return hljs.highlight(code, { language: lang }).value; } catch (e) {}
      }
      return code;
    }
  });
}

function renderMarkdown(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') {
    try {
      return marked.parse(text);
    } catch (e) {
      return escHtml(text);
    }
  }
  // Fallback: escape HTML and preserve newlines
  return escHtml(text).replace(/\n/g, '<br>');
}

function populateModelSelectors() {
  const blocked = getBlockedProviders();
  const filterText = (document.getElementById('modelFilter')?.value || '').toLowerCase();
  const selects = document.querySelectorAll('.model-select');
  for (const sel of selects) {
    const current = sel.value;
    sel.innerHTML = '<option value="">\u9ed8\u8ba4\u6a21\u578b</option>';
    for (const m of allModels) {
      if (blocked.some(p => m.startsWith(p))) continue;
      if (filterText && !m.toLowerCase().includes(filterText)) continue;
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      if (m === current) opt.selected = true;
      sel.appendChild(opt);
    }
  }
}

function filterModels() { populateModelSelectors(); }

function showProviderManager() {
  const providers = getUniqueProviders();
  const blocked = getBlockedProviders();
  let html = '<div class="modal-overlay" id="providerModal" onclick="if(event.target===this)closeProviderManager()" style="display:flex"><div class="modal"><h2>&#128220; 管理提供者</h2><p style="font-size:12px;color:var(--text-dim);margin-bottom:12px">勾选的提供者将被隐藏</p>';
  for (const p of providers) {
    const checked = blocked.includes(p) ? 'checked' : '';
    html += '<label class="provider-item"><input type="checkbox" class="provider-cb" ' + checked + ' onchange="toggleBlockProvider(\'' + p + '\')"><span class="provider-text">' + p + '</span></label>';
  }
  html += '<div class="modal-actions" style="margin-top:12px"><button class="btn-cancel" onclick="closeProviderManager()">关闭</button></div></div></div>';
  const existing = document.getElementById('providerModal');
  if (existing) existing.remove();
  document.body.insertAdjacentHTML('beforeend', html);
}

function closeProviderManager() {
  const el = document.getElementById('providerModal');
  if (el) el.remove();
}

function getBlockedProviders() {
  try { return JSON.parse(localStorage.getItem('blockedProviders') || '[]'); }
  catch (e) { return []; }
}

function toggleBlockProvider(provider) {
  let b = getBlockedProviders();
  const i = b.indexOf(provider);
  i >= 0 ? b.splice(i, 1) : b.push(provider);
  localStorage.setItem('blockedProviders', JSON.stringify(b));
  populateModelSelectors();
}

function getUniqueProviders() {
  const s = new Set();
  for (const m of allModels) {
    const p = m.split('/')[0];
    if (p) s.add(p + '/');
  }
  return [...s].sort();
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
  // 并行加载 stats、directories、sessions
  const [stats, dirsData, sessData] = await Promise.all([
    api('/api/stats'),
    api('/api/directories'),
    api('/api/sessions?limit=200'),
  ]);

  document.getElementById('statsBar').innerHTML = `
    <span>&#128202; 会话 <span class="num">${stats.total_sessions}</span></span>
    <span>&#128193; 项目 <span class="num">${stats.total_projects}</span></span>
    <span>&#9889; Input <span class="num">${fmtTokens(stats.total_tokens_input)}</span></span>
    <span>&#9889; Output <span class="num">${fmtTokens(stats.total_tokens_output)}</span></span>
    <button class="stats-btn" id="statsBtn" onclick="toggleStatsPanel()">&#128202; 详细统计</button>
  `;
  document.getElementById('statsFooter').innerHTML = `
    <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">
      <span>共 ${stats.total_sessions} 个会话</span>
      <button class="compare-btn" id="compareBtn" onclick="toggleCompareMode()">&#128196; 对比</button>
    </div>
  `;

  allDirectories = dirsData.directories;
  allSessions = sessData.sessions;
  sessions = allSessions;

  // 先渲染侧栏，让用户尽快看到内容
  renderSidebar();

  // 延后加载可用模型（调用 opencode models 子进程较慢）
  try {
    const modelsData = await api('/api/available-models');
    if (modelsData.models) {
      allModels = modelsData.models;
      populateModelSelectors();
    }
  } catch (e) {
    // 静默失败，模型切换功能不可用
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
    // 查找目录是否近期活跃
    const dirInfo = allDirectories.find(d => d.path === g.path);
    const isRecent = dirInfo ? dirInfo.recently_active : false;
    // Sort sessions within group by time
    g.sessions.sort((a, b) => (b.time_updated_raw || 0) - (a.time_updated_raw || 0));
    html += `<div class="dir-group">
      <div class="dir-header" onclick="toggleGroup('${gid}')">
        <span class="arrow ${isRecent ? 'open' : ''}" id="arr_${gid}">&#9654;</span>
        ${g.name} <span style="font-weight:400;color:var(--text-dim)">(${g.sessions.length})</span>
      </div>
      <div id="${gid}"${isRecent ? '' : ' style="display:none"'}>`;
    for (const s of g.sessions) {
      const active = s.id === currentSessionId ? 'active' : '';
      const checked = compareIds.includes(s.id) ? 'checked' : '';
      const cb = compareMode ? `<input type="checkbox" class="compare-cb" ${checked} onchange="toggleCompareSelect('${s.id}', this)" onclick="event.stopPropagation()"> ` : '';
      html += `<div class="session-item ${active}" onclick="${compareMode ? 'toggleCompareSelect(\'' + s.id + '\', this.querySelector(\'.compare-cb\'))' : 'openSession(\'' + s.id + '\')'}">
        ${cb}<div class="title">${escHtml(s.title)}</div>
        <span class="del-session" onclick="event.stopPropagation();deleteSession('${s.id}')" title="删除会话">&#10005;</span>
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
  if (eventSource) { eventSource.close(); eventSource = null; }
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

  // Add undo button to header immediately (before API call)
  let undoBtn = document.getElementById('undoHeaderBtn');
  if (!undoBtn) {
    undoBtn = document.createElement('span');
    undoBtn.id = 'undoHeaderBtn';
    undoBtn.className = 'undo-link';
    undoBtn.textContent = ' ↩ 撤销上一条';
    undoBtn.style.marginLeft = '12px';
    undoBtn.onclick = undoLastAction;
    // Insert after mainInfo
    if (mainInfo && mainInfo.parentNode) {
      mainInfo.parentNode.insertBefore(undoBtn, mainInfo.nextSibling);
    }
  }

  // 懒加载：先查缓存，没有再请求
  let data = SESSION_CACHE[id];
  if (!data) {
    data = await api(`/api/sessions/${id}`);
    if (data.error) {
      messagesArea.innerHTML = `<div class="empty-state"><p>${data.error}</p></div>`;
      return;
    }
    SESSION_CACHE[id] = data;
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

    let contentHtml;
    try {
      contentHtml = renderParts(m.parts);
    } catch (_) {
      contentHtml = '(渲染失败)';
    }

    html += `<div class="msg ${role}">
      <div class="msg-avatar">${avatar}</div>
      <div class="msg-body">
        <div class="role-label">${label} · ${m.time_created}</div>
        <div class="content">${contentHtml}</div>
        ${metaLine}
        <div class="undo-link" onclick="undoLastAction()">↩ 撤销</div>
      </div>
    </div>`;
  }

  messagesArea.innerHTML = html;
  messagesArea.scrollTop = messagesArea.scrollHeight;

  // Show input area (Phase 2)
  inputArea.classList.add('show');

  // Show file button
  document.getElementById('fileBtn').style.display = 'block';
  document.getElementById('forkBtn').style.display = 'block';

  // Refresh file panel if open
  if (filePanelOpen && currentDirectory) {
    loadFileTree(currentDirectory);
  }

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
  document.getElementById('forkBtn').style.display = 'none';
  document.getElementById('filePanel').classList.remove('show');
  document.getElementById('fileBtn').classList.remove('active');
  const undoHdr = document.getElementById('undoHeaderBtn');
  if (undoHdr) undoHdr.remove();
  filePanelOpen = false;
  renderSidebar();
}

// ── Phase 2: Send message ──
let streamAbortController = null;

async function sendMessage() {
  const textarea = document.getElementById('msgInput');
  const sendBtn = document.getElementById('sendBtn');
  const text = textarea.value.trim();
  if (!text || !currentSessionId) return;

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
      <div class="content md-content">${renderMarkdown(text)}</div>
    </div>
  </div>`;

  // Add streaming placeholder
  const streamId = 'stream_' + Date.now();
  messagesArea.innerHTML += `<div class="msg assistant streaming" id="${streamId}">
    <div class="msg-avatar">AI</div>
    <div class="msg-body">
      <div class="role-label" id="${streamId}_label">AI · 思考中...</div>
      <div class="tools-inline" id="${streamId}_tools"></div>
      <div class="thinking-content" id="${streamId}_thinking"></div>
      <div class="content" id="${streamId}_text"></div>
      <div class="loading" id="${streamId}_loading" style="padding:10px"><div class="spinner"></div></div>
    </div>
  </div>`;
  messagesArea.scrollTop = messagesArea.scrollHeight;

  // Change send button to stop button
  textarea.value = '';
  textarea.disabled = true;
  sendBtn.textContent = '⏹ 停止';
  sendBtn.disabled = false;
  sendBtn.onclick = stopGeneration;

  // 30s timeout: if no output received, show error
  let receivedAny = false;
  const timeoutTimer = setTimeout(() => {
    if (!receivedAny) {
      const labelEl = document.getElementById(streamId + '_label');
      const loading = document.getElementById(streamId + '_loading');
      if (labelEl) labelEl.textContent = 'AI · 无响应 (模型可能受限)';
      if (loading) {
        loading.innerHTML = '<span style="color:var(--accent3);font-size:12px">⏱ 30 秒无响应，可点击停止后切换模型重试</span>';
      }
    }
  }, 30000);
  // Clear timeout on any event
  const clearTimeoutFn = () => { receivedAny = true; clearTimeout(timeoutTimer); };

  // Start SSE stream
  const modelParam = currentModel ? '&model=' + encodeURIComponent(currentModel) : '';
  eventSource = new EventSource(`/api/sessions/${currentSessionId}/stream?message=${encodeURIComponent(text)}${modelParam}`);

  eventSource.addEventListener('thinking', (e) => {
    clearTimeoutFn();
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
    clearTimeoutFn();
    const el = document.getElementById(streamId + '_text');
    if (el) {
      el.textContent += e.data.replace(/\\n/g, '\n');
      messagesArea.scrollTop = messagesArea.scrollHeight;
    }
  });

  // Real-time tool use display
  eventSource.addEventListener('tool_use', (e) => {
    clearTimeoutFn();
    const toolsEl = document.getElementById(streamId + '_tools');
    const labelEl = document.getElementById(streamId + '_label');
    if (toolsEl) {
      try {
        const info = JSON.parse(e.data);
        const toolSpan = document.createElement('span');
        toolSpan.className = 'tool-chip';
        toolSpan.textContent = '🔧 ' + info.tool + (info.input ? ': ' + info.input.slice(0, 60) : '');
        toolsEl.appendChild(toolSpan);
        messagesArea.scrollTop = messagesArea.scrollHeight;
      } catch (_) {}
    }
    if (labelEl) labelEl.textContent = 'AI · 使用工具...';
  });

  eventSource.addEventListener('tool_result', (e) => {
    clearTimeoutFn();
    const labelEl = document.getElementById(streamId + '_label');
    if (labelEl) labelEl.textContent = 'AI · 处理工具结果...';
  });

  eventSource.addEventListener('status', (e) => {
    clearTimeoutFn();
    const labelEl = document.getElementById(streamId + '_label');
    if (labelEl) {
      if (e.data === 'step_start') labelEl.textContent = 'AI · 思考中...';
      else if (e.data === 'waiting') labelEl.textContent = 'AI · 等待响应...';
    }
  });

  function generationDone() {
    if (!eventSource) return; // Already done
    clearTimeoutFn();
    eventSource.close();
    // 清除缓存，确保下次打开时看到最新数据
    if (currentSessionId) delete SESSION_CACHE[currentSessionId];
    eventSource = null;
    textarea.disabled = false;
    sendBtn.textContent = '发送';
    sendBtn.onclick = sendMessage;
    sendBtn.disabled = false;
    textarea.focus();
  }

  eventSource.addEventListener('done', (e) => {
    const loading = document.getElementById(streamId + '_loading');
    const msgEl = document.getElementById(streamId);
    const textEl = document.getElementById(streamId + '_text');
    if (loading) loading.remove();
    if (msgEl) msgEl.classList.remove('streaming');
    if (textEl) {
      const fullText = textEl.textContent;
      textEl.innerHTML = renderMarkdown(fullText);
      textEl.classList.add('md-content');
    }
    // Add undo link
    if (msgEl) {
      const undoLink = document.createElement('div');
      undoLink.className = 'undo-link';
      undoLink.innerHTML = '↩ 撤销';
      undoLink.onclick = undoLastAction;
      msgEl.querySelector('.msg-body').appendChild(undoLink);
    }
    generationDone();
  });

  eventSource.addEventListener('stream_error', (e) => {
    console.log('[DEBUG] stream_error received:', e.data);
    const loading = document.getElementById(streamId + '_loading');
    const msgEl = document.getElementById(streamId);
    if (loading) loading.remove();
    if (msgEl) msgEl.classList.remove('streaming');
    const textEl = document.getElementById(streamId + '_text');
    if (textEl) {
      textEl.innerHTML = renderStreamError(e.data);
    }
    generationDone();
  });

  // Also listen for connection-level errors (debug + fallback)
  eventSource.onerror = (e) => {
    if (!eventSource) return; // Already cleaned up
    console.log('[DEBUG] EventSource onerror, readyState:', eventSource.readyState);
    // If the stream_error event didn't show an error message, show a fallback
    const textEl = document.getElementById(streamId + '_text');
    const loadingEl = document.getElementById(streamId + '_loading');
    if (textEl && !textEl.querySelector('.error-msg') && !textEl.textContent.trim()) {
      // No error message displayed and no text content - show fallback
      const msgEl = document.getElementById(streamId);
      if (loadingEl) loadingEl.remove();
      if (msgEl) msgEl.classList.remove('streaming');
      textEl.innerHTML = renderStreamError('连接中断，模型可能受限。请切换模型后重试。');
      generationDone();
    }
  };
}

function stopGeneration() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  const sendBtn = document.getElementById('sendBtn');
  const textarea = document.getElementById('msgInput');
  sendBtn.textContent = '发送';
  sendBtn.onclick = sendMessage;
  sendBtn.disabled = false;
  textarea.disabled = false;
  textarea.focus();
}

async function undoLastAction() {
  if (!currentSessionId) return;
  try {
    const res = await fetch(`/api/sessions/${currentSessionId}/undo`, { method: 'POST' });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    delete SESSION_CACHE[currentSessionId];
    openSession(currentSessionId);
  } catch (e) {
    alert('撤销失败: ' + e.message);
  }
}

async function deleteSession(id) {
  if (!confirm('确定删除此会话？')) return;
  try {
    const res = await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    // 刷新侧栏
    const sessData = await api('/api/sessions?limit=200');
    allSessions = sessData.sessions;
    sessions = allSessions;
    if (currentSessionId === id) showList();
    else renderSidebar();
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
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

function parseStreamError(raw) {
  let message = (raw || '未知错误').trim();
  try {
    const parsed = JSON.parse(message);
    if (parsed.message) message = streamErrorTextFromValue(parsed.message);
    else if (parsed.error) message = streamErrorTextFromValue(parsed.error);
    else if (parsed.name) message = parsed.name + (parsed.data?.message ? ': ' + parsed.data.message : '');
  } catch (_) {}
  message = streamErrorTextFromValue(message) || '未知错误';

  const detailMarker = '\n\n技术细节：';
  const markerIndex = message.indexOf(detailMarker);
  if (markerIndex >= 0) {
    return {
      summary: message.slice(0, markerIndex).trim() || 'OpenCode 返回错误',
      details: message.slice(markerIndex + detailMarker.length).trim(),
    };
  }

  const inlineMarker = '技术细节：';
  const inlineIndex = message.indexOf(inlineMarker);
  if (inlineIndex > 0) {
    return {
      summary: message.slice(0, inlineIndex).trim() || 'OpenCode 返回错误',
      details: message.slice(inlineIndex + inlineMarker.length).trim(),
    };
  }

  return { summary: message, details: '' };
}

function streamErrorTextFromValue(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'object') {
    if (value.message) return streamErrorTextFromValue(value.message);
    if (value.error) return streamErrorTextFromValue(value.error);
    if (value.name) return streamErrorTextFromValue(value.name);
    try {
      return JSON.stringify(value);
    } catch (_) {
      return String(value);
    }
  }
  return String(value);
}

function renderStreamError(raw) {
  const parsed = parseStreamError(raw);
  const detailHtml = parsed.details
    ? `<details class="error-details"><summary>技术细节</summary><pre>${escHtml(parsed.details)}</pre></details>`
    : '';
  return `<div class="error-msg"><div class="error-title">${escHtml(parsed.summary)}</div>${detailHtml}</div>`;
}
window.renderStreamError = renderStreamError;

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
  // Populate model dropdown
  const modelSel = document.getElementById('newSessionModel');
  if (modelSel && allModels.length > 0) {
    modelSel.innerHTML = '<option value="">默认模型</option>';
    for (const m of allModels) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      if (m === currentModel) opt.selected = true;
      modelSel.appendChild(opt);
    }
  }
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
  const modelSelect = document.getElementById('newSessionModel');
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
        <div class="content md-content">${renderMarkdown(message)}</div>
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
    body: JSON.stringify({ directory, message, model: modelSelect.value || undefined }),
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
        } else if (eventType === 'tool_use') {
          const toolsEl = document.getElementById(streamId + '_tools');
          const labelEl = document.getElementById(streamId + '_label');
          if (toolsEl) {
            try {
              const info = JSON.parse(data);
              const chip = document.createElement('span');
              chip.className = 'tool-chip';
              chip.textContent = '🔧 ' + info.tool + (info.input ? ': ' + info.input.slice(0, 60) : '');
              toolsEl.appendChild(chip);
            } catch (_) {}
          }
          if (labelEl) labelEl.textContent = 'AI · 使用工具...';
        } else if (eventType === 'tool_result') {
          const labelEl = document.getElementById(streamId + '_label');
          if (labelEl) labelEl.textContent = 'AI · 处理工具结果...';
        } else if (eventType === 'status') {
          const labelEl = document.getElementById(streamId + '_label');
          if (labelEl && data === 'step_start') labelEl.textContent = 'AI · 思考中...';
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
        } else if (eventType === 'stream_error') {
          const loading = document.getElementById(streamId + '_loading');
          const msgEl = document.getElementById(streamId);
          if (loading) loading.remove();
          if (msgEl) msgEl.classList.remove('streaming');
          messagesArea.innerHTML += `<div class="empty-state">${renderStreamError(data)}</div>`;
          submitBtn.disabled = false;
        }
      }
    }
  }).catch((err) => {
    const loading = document.getElementById(streamId + '_loading');
    if (loading) loading.remove();
    messagesArea.innerHTML += `<div class="empty-state">${renderStreamError(err.message)}</div>`;
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
    zip: '📦', tar: '📦', gz: '📦', '7z': '📦',
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

// ── Phase 3: Charts ──

let statsOpen = false;
let chartInstances = {};

function toggleStatsPanel() {
  statsOpen = !statsOpen;
  const panel = document.getElementById('statsPanel');
  const btn = document.getElementById('statsBtn');
  panel.classList.toggle('show', statsOpen);
  btn.classList.toggle('active', statsOpen);
  if (statsOpen) {
    loadStatsData();
  }
}

async function loadStatsData() {
  try {
    const data = await api('/api/stats/tokens');
    renderCharts(data);
    renderOverview(data);
  } catch (e) {
    document.getElementById('statsContent').innerHTML =
      `<div class="file-entry loading">加载失败: ${escHtml(e.message)}</div>`;
  }
}

function renderCharts(data) {
  // Destroy old charts
  for (const key in chartInstances) {
    chartInstances[key].destroy();
  }
  chartInstances = {};

  const chartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: '#8899aa', font: { size: 11 } } },
    },
  };

  // 1. Daily token chart
  if (data.daily && data.daily.length > 0) {
    const ctx = document.getElementById('chartDaily').getContext('2d');
    chartInstances.daily = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.daily.map(d => d.day.slice(5)),
        datasets: [
          { label: 'Input', data: data.daily.map(d => Math.round(d.input / 1000)),
            backgroundColor: '#4fc3f780', borderRadius: 3 },
          { label: 'Output', data: data.daily.map(d => Math.round(d.output / 1000)),
            backgroundColor: '#81c78480', borderRadius: 3 },
        ],
      },
      options: {
        ...chartOpts,
        scales: {
          x: { ticks: { color: '#8899aa', font: { size: 10 } }, grid: { color: '#2a3a5a' } },
          y: { ticks: { color: '#8899aa', font: { size: 10 } }, grid: { color: '#2a3a5a' },
               title: { display: true, text: 'K tokens', color: '#8899aa', font: { size: 10 } } },
        },
      },
    });
  }

  // 2. Model chart
  if (data.by_model && data.by_model.length > 0) {
    const ctx2 = document.getElementById('chartModels').getContext('2d');
    const labels = data.by_model.map(m => m.model.split('/').pop());
    chartInstances.models = new Chart(ctx2, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: data.by_model.map(m => Math.round((m.input + m.output) / 1000)),
          backgroundColor: ['#4fc3f7', '#81c784', '#ffb74d', '#e57373', '#ba68c8',
                            '#4db6ac', '#ff8a65', '#90a4ae', '#a1887f', '#7986cb'],
          borderWidth: 0,
        }],
      },
      options: {
        ...chartOpts,
        plugins: {
          ...chartOpts.plugins,
          legend: { position: 'right', labels: { color: '#8899aa', font: { size: 10 } } },
        },
      },
    });
  }

  // 3. Project chart
  if (data.by_project && data.by_project.length > 0) {
    const ctx3 = document.getElementById('chartProjects').getContext('2d');
    chartInstances.projects = new Chart(ctx3, {
      type: 'bar',
      data: {
        labels: data.by_project.map(p => p.project),
        datasets: [{
          label: 'Total tokens',
          data: data.by_project.map(p => Math.round((p.input + p.output) / 1000)),
          backgroundColor: '#4fc3f780', borderRadius: 3,
        }],
      },
      options: {
        ...chartOpts,
        indexAxis: 'y',
        scales: {
          x: { ticks: { color: '#8899aa', font: { size: 10 } }, grid: { color: '#2a3a5a' },
               title: { display: true, text: 'K tokens', color: '#8899aa', font: { size: 10 } } },
          y: { ticks: { color: '#8899aa', font: { size: 10 } }, grid: { display: false } },
        },
      },
    });
  }
}

function renderOverview(data) {
  const totalInput = data.by_model ? data.by_model.reduce((s, m) => s + m.input, 0) : 0;
  const totalOutput = data.by_model ? data.by_model.reduce((s, m) => s + m.output, 0) : 0;
  const totalCost = data.total_cost || 0;

  document.getElementById('statsOverview').innerHTML = `
    <div class="stat-card">
      <div class="stat-label">总 Input</div>
      <div class="stat-value">${fmtTokens(totalInput)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">总 Output</div>
      <div class="stat-value">${fmtTokens(totalOutput)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">总消耗</div>
      <div class="stat-value">$${totalCost.toFixed(4)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">模型数</div>
      <div class="stat-value">${data.by_model ? data.by_model.length : 0}</div>
      <div class="stat-sub">30 天内</div>
    </div>
  `;
}

// ── Phase 3: Fork session ──

async function forkSession() {
  if (!currentSessionId) return;
  const message = prompt('输入分叉后的第一条消息（Fork 后将创建新会话）：');
  if (!message) return;

  const submitBtn = document.getElementById('sendBtn');
  const textarea = document.getElementById('msgInput');
  submitBtn.disabled = true;

  const streamId = 'fork_' + Date.now();
  const messagesArea = document.getElementById('messagesArea');
  const inputArea = document.getElementById('inputArea');
  const mainTitle = document.getElementById('mainTitle');
  const mainInfo = document.getElementById('mainInfo');

  mainTitle.textContent = '分叉中...';
  inputArea.classList.remove('show');

  messagesArea.innerHTML += `<div class="msg user">
    <div class="msg-avatar">U</div>
    <div class="msg-body">
      <div class="role-label">你 · 分叉点</div>
      <div class="content md-content">${renderMarkdown(message)}</div>
    </div>
  </div>
  <div class="msg assistant streaming" id="${streamId}">
    <div class="msg-avatar">AI</div>
    <div class="msg-body">
      <div class="role-label">AI · 分叉中...</div>
      <div class="thinking-content" id="${streamId}_thinking"></div>
      <div class="content" id="${streamId}_text"></div>
      <div class="loading" id="${streamId}_loading" style="padding:10px"><div class="spinner"></div></div>
    </div>
  </div>`;
  messagesArea.scrollTop = messagesArea.scrollHeight;

  try {
    const response = await fetch(`/api/sessions/${currentSessionId}/fork`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, model: currentModel || undefined }),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || '分叉失败');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let newId = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';
      for (const block of events) {
        const lines = block.split('\n');
        let eventType = '', data = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          else if (line.startsWith('data: ')) data = line.slice(6);
        }
        if (eventType === 'thinking') {
          const el = document.getElementById(streamId + '_thinking');
          if (el && el.textContent.length < 2000) el.textContent += data.replace(/\\n/g, '\n');
        } else if (eventType === 'text') {
          const el = document.getElementById(streamId + '_text');
          if (el) el.textContent += data.replace(/\\n/g, '\n');
        } else if (eventType === 'tool_use') {
          const toolsEl = document.getElementById(streamId + '_tools');
          const labelEl = document.getElementById(streamId + '_label');
          if (toolsEl) {
            try {
              const info = JSON.parse(data);
              const chip = document.createElement('span');
              chip.className = 'tool-chip';
              chip.textContent = '🔧 ' + info.tool + (info.input ? ': ' + info.input.slice(0, 60) : '');
              toolsEl.appendChild(chip);
            } catch (_) {}
          }
          if (labelEl) labelEl.textContent = 'AI · 使用工具...';
        } else if (eventType === 'tool_result') {
          const labelEl = document.getElementById(streamId + '_label');
          if (labelEl) labelEl.textContent = 'AI · 处理工具结果...';
        } else if (eventType === 'status') {
          const labelEl = document.getElementById(streamId + '_label');
          if (labelEl && data === 'step_start') labelEl.textContent = 'AI · 思考中...';
        } else if (eventType === 'done') {
          const info = JSON.parse(data || '{}');
          newId = info.session_id;
        } else if (eventType === 'stream_error') {
          throw new Error(data);
        }
      }
    }

    // End streaming
    const loading = document.getElementById(streamId + '_loading');
    const msgEl = document.getElementById(streamId);
    if (loading) loading.remove();
    if (msgEl) msgEl.classList.remove('streaming');

    if (newId) {
      // Refresh and navigate to new session
      currentSessionId = newId;
      const sessData = await api('/api/sessions?limit=200');
      allSessions = sessData.sessions;
      sessions = allSessions;
      renderSidebar();
      openSession(newId);
    } else {
      inputArea.classList.add('show');
      mainTitle.textContent = '分叉完成';
    }
  } catch (e) {
    const loading = document.getElementById(streamId + '_loading');
    if (loading) loading.remove();
    messagesArea.innerHTML += `<div class="empty-state">${renderStreamError(e.message)}</div>`;
  } finally {
    submitBtn.disabled = false;
  }
}

// ── Phase 3: Compare sessions ──

function toggleCompareMode() {
  compareMode = !compareMode;
  compareIds = [];
  document.getElementById('compareBtn').classList.toggle('active', compareMode);
  renderSidebar();
  if (compareMode) {
    document.getElementById('mainTitle').textContent = '选择两个会话进行对比';
    document.getElementById('messagesArea').innerHTML = `<div class="empty-state"><p>在左侧勾选两个会话，然后点击「开始对比」</p></div>`;
    document.getElementById('inputArea').classList.remove('show');
    document.getElementById('fileBtn').style.display = 'none';
    document.getElementById('forkBtn').style.display = 'none';
    document.getElementById('backBtn').style.display = 'block';
  } else {
    showList();
  }
}

function toggleCompareSelect(id, cb) {
  if (cb && cb.checked !== undefined) {
    if (cb.checked) {
      if (compareIds.length >= 2) {
        cb.checked = false;
        return;
      }
      compareIds.push(id);
    } else {
      compareIds = compareIds.filter(i => i !== id);
    }
  }
  renderSidebar();
  if (compareIds.length === 2) {
    doCompare();
  }
}

async function doCompare() {
  const id1 = compareIds[0], id2 = compareIds[1];
  const messagesArea = document.getElementById('messagesArea');
  messagesArea.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  try {
    const data = await api(`/api/sessions/compare?id1=${encodeURIComponent(id1)}&id2=${encodeURIComponent(id2)}`);
    if (data.error) {
      messagesArea.innerHTML = `<div class="empty-state"><p>${escHtml(data.error)}</p></div>`;
      return;
    }
    renderCompareView(data.session1, data.session2);
  } catch (e) {
    messagesArea.innerHTML = `<div class="empty-state"><p>对比失败: ${escHtml(e.message)}</p></div>`;
  }
}

function renderCompareView(s1, s2) {
  const messagesArea = document.getElementById('messagesArea');
  document.getElementById('mainTitle').textContent = '会话对比';
  document.getElementById('mainInfo').textContent = '';

  // Prepare messages aligned
  const maxLen = Math.max(s1.messages.length, s2.messages.length);

  let html = `<div class="compare-header">
    <div class="compare-col">
      <div class="compare-title">${escHtml(s1.title)}</div>
      <div class="compare-meta">${s1.model} · ${s1.message_count} 条 · ${fmtTokens(s1.tokens_input + s1.tokens_output)} tokens</div>
    </div>
    <div class="compare-col">
      <div class="compare-title">${escHtml(s2.title)}</div>
      <div class="compare-meta">${s2.model} · ${s2.message_count} 条 · ${fmtTokens(s2.tokens_input + s2.tokens_output)} tokens</div>
    </div>
  </div>`;

  for (let i = 0; i < maxLen; i++) {
    const msg1 = i < s1.messages.length ? s1.messages[i] : null;
    const msg2 = i < s2.messages.length ? s2.messages[i] : null;
    html += `<div class="compare-row">`;
    for (const msg of [msg1, msg2]) {
      if (msg) {
        const roleLabel = msg.role === 'user' ? '你' : msg.role === 'assistant' ? 'AI' : '工具';
        html += `<div class="compare-msg ${msg.role}">
          <div class="role-label">${roleLabel}</div>
          <div class="content">${renderParts(msg.parts) || '(空)'}</div>
        </div>`;
      } else {
        html += `<div class="compare-msg empty"></div>`;
      }
    }
    html += `</div>`;
  }

  html += `<div style="padding:12px;text-align:center;color:var(--text-dim);font-size:12px">
    Token 消耗: S1=${fmtTokens(s1.tokens_input + s1.tokens_output)} | S2=${fmtTokens(s2.tokens_input + s2.tokens_output)} | 费用: $${s1.cost?.toFixed(4) || '0'} / $${s2.cost?.toFixed(4) || '0'}
  </div>`;

  messagesArea.innerHTML = html;
}
