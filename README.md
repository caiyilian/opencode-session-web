# OpenCode 会话 Web 管理器

OpenCode 会话 Web 查看器 —— 在浏览器中浏览和管理本地的 OpenCode 对话历史。

---

## 功能

- 📋 **浏览会话**：左侧栏按项目分组显示所有会话
- 🔍 **搜索会话**：按标题、目录、模型快速定位
- 💬 **查看对话**：阅读完整的历史消息（含思考过程、工具调用）
- 📊 **统计概览**：会话数、项目数、Token 消耗一目了然
- 📱 **移动端适配**：手机浏览器也能正常使用
- ✏️ **继续对话**（Phase 2）：在 Web 上继续已有会话或新建会话

## 快速开始

### 1. 安装依赖

```bash
pip install flask
```

或者用 uv（推荐，自动使用 Python 3.13）：

```bash
uv venv
uv pip install flask
```

### 2. 启动服务

```bash
cd opencode-session-web

# 直接用系统 Python
python app.py 8765

# 或用 uv 环境
uv run python app.py 8765
```

### 3. 打开浏览器

访问 http://127.0.0.1:8765

### 4. （可选）公网访问

用 Cloudflare Tunnel 暴露到公网，手机即可访问：

```bash
cloudflared tunnel --url http://localhost:8765
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python Flask |
| 前端 | 原生 HTML + CSS + JS（单页应用） |
| 数据库 | SQLite（直读 OpenCode 的 `opencode.db`） |
| 数据源 | `~/.local/share/opencode/opencode.db` |

## API 接口

| 端点 | 说明 |
|------|------|
| `GET /api/stats` | 统计信息 |
| `GET /api/sessions?q=&dir=&model=&limit=&offset=` | 会话列表（支持搜索/筛选） |
| `GET /api/sessions/:id` | 会话详情（含消息历史） |
| `GET /api/directories` | 所有工作目录 |
| `GET /api/models` | 所有用过的模型 |
| `POST /api/sessions/new` | 新建会话（Phase 2） |
| `POST /api/sessions/:id/resume` | 继续会话（Phase 2） |
| `GET /api/sessions/:id/stream` | SSE 流式输出（Phase 2） |
| `GET /api/directories/:path/files` | 浏览工作目录文件（Phase 2） |

## 项目结构

```
opencode-session-web/
├── app.py                   # Flask 后端入口
├── templates/
│   └── index.html           # HTML 模板
├── static/
│   ├── css/
│   │   └── main.css         # 样式
│   └── js/
│       └── app.js           # 前端逻辑
├── docs/
│   └── 方案.md              # 方案设计文档
├── scripts/                 # 辅助脚本（Node.js 桥接等）
├── README.md
└── .gitignore
```

## 开发计划

- [x] 第一阶段：只读模式 — 浏览和搜索会话历史（已完成）
- [x] 第二阶段：交互模式 — SSE 流式继续/新建会话、模型切换、文件浏览（已完成）
- [x] 第三阶段：增强功能 — 统计图表、Fork、会话对比（已完成）
