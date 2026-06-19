content = open('static/js/app.js', 'r', encoding='utf-8').read()

# Find the exact init function boundaries
init_start = content.find('// ── Init ──')
after_header = content.find('async function init() {', init_start)
fn_body_start = content.find('{', after_header) + 1
# Find the closing brace of init() - search for the next "// ──" section marker
next_section = content.find('\n// ──', fn_body_start)
# The line before next_section should be the closing }
fn_end = content.rfind('}', next_section - 80, next_section) + 1

print(f'init body: chars {fn_body_start} to {fn_end}')

old_body = content[fn_body_start:fn_end]
new_body = """
  // 并行加载 stats、directories、sessions
  const [stats, dirsData, sessData] = await Promise.all([
    api('/api/stats'),
    api('/api/directories'),
    api('/api/sessions?limit=200'),
  ]);

  document.getElementById('statsBar').innerHTML = \`
    <span>&#128202; 会话 <span class="num">\${stats.total_sessions}</span></span>
    <span>&#128193; 项目 <span class="num">\${stats.total_projects}</span></span>
    <span>&#9889; Input <span class="num">\${fmtTokens(stats.total_tokens_input)}</span></span>
    <span>&#9889; Output <span class="num">\${fmtTokens(stats.total_tokens_output)}</span></span>
    <button class="stats-btn" id="statsBtn" onclick="toggleStatsPanel()">&#128202; 详细统计</button>
  \`;
  document.getElementById('statsFooter').innerHTML = \`
    <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">
      <span>共 \${stats.total_sessions} 个会话</span>
      <button class="compare-btn" id="compareBtn" onclick="toggleCompareMode()">&#128196; 对比</button>
    </div>
  \`;

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
"""

content = content[:fn_body_start] + new_body + content[fn_end:]
open('static/js/app.js', 'w', encoding='utf-8').write(content)
print(f'OK: replaced {len(old_body)} bytes with {len(new_body)} bytes')
