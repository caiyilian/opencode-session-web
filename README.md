# OpenCode 会话 Web 管理器

OpenCode 会话 Web 管理器是一个 Flask 应用，用于在浏览器中浏览和管理本地 OpenCode 对话历史。它读取本机 OpenCode SQLite 数据库，提供 REST/SSE API，可按需服务旧版静态界面或 React 构建产物，并包含一个用于会话完成通知的微信 iLink 监控脚本。

## 功能

- 按项目目录分组浏览会话，并支持标题、目录、模型搜索。
- 查看完整消息时间线，包括 reasoning、工具调用、工具输出、耗时、token 和成本信息。
- 继续已有会话、新建会话、Fork 会话、撤销最后一轮、删除会话和对比会话。
- 使用 Workspace 项目面板查看项目级会话摘要、创建和推进本地任务，并查看只读 Git snapshot。
- 查看用量统计、最近项目、模型/Provider 可用状态，以及加载、空状态、错误状态和移动端布局。
- 使用临时 SQLite fixture 运行可重复的后端、前端和 Playwright E2E 测试。
- 监控 OpenCode 数据库更新，并在助手回复完成后发送微信 iLink 通知。

## 环境要求

- Python 3.12 或更高版本。
- Node.js 和 npm，用于 React 前端、Vitest 和 Playwright E2E 测试。
- OpenCode CLI 已安装并可在 `PATH` 中访问，实时继续/新建/Fork 会话需要它：

```bash
opencode --version
```

只浏览 fixture 或已有数据库时不需要启动 CLI；但流式会话操作和模型发现要求启动 Flask 的同一个 shell 环境可以正常执行 OpenCode CLI。

## 安装

在仓库根目录创建虚拟环境：

```bash
python -m venv .venv
```

PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cd frontend
npm install
```

Bash：

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
cd frontend
npm install
```

也可以使用 `uv`：

```bash
uv venv
uv pip install -e ".[dev]"
```

## 运行

### 旧版静态界面

默认入口会服务 `templates/index.html`、`static/css/main.css` 和 `static/js/app.js`。

```bash
python app.py 8765
```

然后打开 http://127.0.0.1:8765。

### React 构建界面

先构建前端：

```bash
cd frontend
npm run build
cd ..
```

PowerShell：

```powershell
$env:OPENCODE_USE_FRONTEND_DIST = "1"
python app.py 8765
```

Bash：

```bash
OPENCODE_USE_FRONTEND_DIST=1 python app.py 8765
```

React 应用会由 Flask 从 `frontend/dist` 服务，API 请求保持同源。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENCODE_DB_PATH` | `~/.local/share/opencode/opencode.db` | 要读取的 SQLite 数据库。使用自定义 OpenCode 数据目录或 fixture 数据库时设置它。 |
| `OPENCODE_WORKSPACE_DB_PATH` | `~/.opencode-session-web/workspace.db` | OpenCode Session Web 自己的 Workspace 数据库，用于保存任务等本地工作台状态。 |
| `OPENCODE_USE_FRONTEND_DIST` | 未设置/false | 设置为 `1`、`true`、`yes` 或 `on` 时服务 React 构建产物，而不是旧版静态界面。 |
| `OPENCODE_FRONTEND_DIST_DIR` | `frontend/dist` | Flask 服务的 React 构建目录。 |
| `OPENCODE_STREAM_TIMEOUT` | `600` | 流式进程最长运行时间，单位秒。 |
| `OPENCODE_IDLE_TIMEOUT` | `25` | 等待 OpenCode stream 事件的空闲超时，单位秒。 |
| `OPENCODE_WEB_LOG_DIR` | `~/.opencode-session-web/logs` | 轮转日志 `app.log` 的目录。 |
| `OPENCODE_WEB_LOG_LEVEL` | `INFO` | Python 日志级别。 |
| `OPENCODE_WEB_LOG_MAX_BYTES` | `5242880` | 单个日志文件触发轮转前的最大字节数。 |
| `OPENCODE_WEB_LOG_BACKUPS` | `5` | 保留的轮转日志文件数量。 |

自定义数据库示例：

PowerShell：

```powershell
$env:OPENCODE_DB_PATH = "C:\path\to\opencode.db"
python app.py 8765
```

Bash：

```bash
OPENCODE_DB_PATH=/path/to/opencode.db python app.py 8765
```

## 测试

后端测试：

```bash
python -m pytest
```

前端单元测试：

```bash
cd frontend
npm test
```

前端生产构建：

```bash
cd frontend
npm run build
```

Playwright E2E 测试：

```bash
cd frontend
npm run test:e2e
```

`test:e2e` 会构建 React dist，通过 `tests/e2e_server.py` 启动带临时 SQLite fixture 的 Flask 服务，并运行桌面端与 390px 移动端浏览器覆盖。默认使用本机 Chrome channel；如果环境需要其它已安装浏览器 channel，可设置 `PLAYWRIGHT_CHANNEL`。

从仓库根目录运行主要本地验证套件：

```bash
python scripts/run_all_tests.py
```

该脚本会依次运行后端 pytest、前端单元测试和前端 E2E 测试。

## 微信监控

`opencode_monitor.py` 独立于 Flask 应用。它轮询 OpenCode SQLite 数据库，使用共享监控状态逻辑识别已完成的助手回复，并发送微信 iLink 通知。

```bash
python opencode_monitor.py
```

首次运行需要扫描微信登录二维码。登录后需要给 bot 发送任意一条消息，以便脚本获取用于发送通知的 `context_token`。凭据保存在 `~/.opencode-monitor-cred.json`。

常用监控环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `POLL_INTERVAL` | `3` | 轮询间隔，单位秒。 |
| `MONITOR_STABLE_WINDOW_MS` | `1500` | 判定回复已稳定完成前等待的窗口，单位毫秒。 |

## 公网访问

如果需要临时用手机访问，可先在本机启动 Flask，再通过 Cloudflare Tunnel 暴露：

```bash
cloudflared tunnel --url http://localhost:8765
```

会话历史可能包含私密信息。暴露到公网前请确保网络可信，或自行增加访问控制。

## 项目结构

```text
opencode-session-web/
├── app.py                         # Flask 路由和 app factory
├── config.py                      # 基于环境变量的配置
├── db.py                          # SQLite 兼容读取工具
├── logging_config.py              # 轮转日志配置
├── opencode_monitor.py            # 微信 iLink 监控
├── repositories/                  # 查询辅助模块
├── services/                      # SSE、OpenCode 事件、runner、进程管理
├── frontend/                      # React、Vite、Vitest、Playwright
│   ├── src/
│   ├── e2e/
│   └── playwright.config.ts
├── static/                        # 旧版 CSS/JS 界面
├── templates/                     # 旧版 Flask 模板
├── tests/                         # Pytest 套件和 E2E Flask fixture 服务
├── scripts/run_all_tests.py       # 本地验证入口
└── 优化修改重构方案.md
```

## 排障

### 数据库不存在或为空

如果 `OPENCODE_DB_PATH` 没有指向存在的 SQLite 数据库，Flask 日志会记录错误。请先在本机至少运行一次 OpenCode，或把 `OPENCODE_DB_PATH` 设置为正确的数据库文件。

### OpenCode CLI 找不到

如果 React UI 显示模型可用性告警，或流式会话操作立即失败，先确认启动 Flask 的同一个 shell 可以执行：

```bash
opencode --version
opencode models
```

修复 `PATH`、OpenCode 安装、登录状态或 Provider 配置后再重试。

### 速率限制、配额、鉴权或模型错误

Web stream 会尽快暴露常见的 OpenCode/Provider 错误。可以切换模型、刷新 Provider 凭据，或等待配额和速率限制恢复。后端细节可查看 `OPENCODE_WEB_LOG_DIR` 下的 `app.log`。

### React 界面没有出现

确认 `frontend/dist/index.html` 存在，并且 Flask 进程环境中设置了 `OPENCODE_USE_FRONTEND_DIST=1`。否则 Flask 会按设计服务旧版静态界面。

### Playwright 无法启动浏览器

默认 E2E 配置使用已安装的 Chrome channel。请安装 Chrome，或把 `PLAYWRIGHT_CHANNEL` 设置为其它可用 channel。如果你把 Playwright 配置改为使用 bundled browsers，需要在对应环境运行 Playwright 浏览器安装命令。

### 端口已被占用

换一个端口启动 Flask：

```bash
python app.py 8766
```

E2E 测试可覆盖测试服务端口：

```bash
cd frontend
E2E_PORT=18766 npm run test:e2e
```

PowerShell：

```powershell
cd frontend
$env:E2E_PORT = "18766"
npm run test:e2e
```

### 微信登录或通知异常

删除 `~/.opencode-monitor-cred.json` 可以强制重新扫码登录。扫码后给 bot 发送任意消息，确保脚本可以获取 `context_token` 并发送后续通知。
