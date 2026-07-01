# OpenCode Workspace 最终验收记录

日期：2026-06-30

目标：把 OpenCode Session Web 从会话浏览器扩展为本地项目工作台，让用户围绕项目创建任务、关联 OpenCode 执行、查看 Git 变更、运行验证命令，并沉淀可追踪的交付记录。

## 验收矩阵

| 要求 | 当前证据 |
| --- | --- |
| 保留原有会话浏览、搜索、继续、新建、Fork、Undo、Delete、Compare、Provider 管理和实时同步 | `tests/test_final_compat_contract.py` 锁定公共路由；`frontend/e2e/session-workflow.spec.ts` 覆盖浏览、搜索、打开、对比、Fork 校验和移动端；`tests/test_api_events.py`、`tests/test_sync_watcher.py`、`tests/test_frontend_session_sync.py` 覆盖实时同步。 |
| 项目工作台聚合项目会话、消息、token、成本、模型和最近会话 | `/api/workspace/projects` 由 `repositories/session_queries.py::fetch_project_workspaces` 提供；React `WorkspacePanel` 展示项目摘要；`tests/test_schema_compat.py` 和 E2E 覆盖入口。 |
| 任务模型支持创建、状态推进、项目绑定、关联会话和详情回看 | `repositories/workspace_tasks.py` 持久化 `workspace_task`；`/api/workspace/tasks`、`/api/workspace/tasks/<task_id>/detail` 提供任务列表和详情；`TaskDetailPanel` 聚合任务、关联会话、Git、验证历史和 timeline；`tests/test_workspace_tasks.py`、`tests/test_workspace_reports.py` 覆盖。 |
| Git 变更面板显示分支、dirty files、最近 commits，并处理非 Git 项目 | `services/git_status.py` 和 `/api/workspace/git` 读取只读 snapshot；React `GitSnapshotPanel` 展示状态；`tests/test_workspace_git.py` 覆盖 Git 和非 Git 路径。 |
| 受控命令运行具备白名单、非 shell argv、项目 cwd 约束、实时输出、失败记录和进程清理 | `services/workspace_commands.py` 解析 JSON 白名单并约束相对 cwd；`/api/workspace/command-runs` 和 `/api/workspace/command-runs/stream` 持久化运行记录；`ValidationRunsPanel` 展示实时日志和历史；`tests/test_workspace_commands.py`、`tests/test_process_manager.py` 覆盖。 |
| 危险命令需要确认并有权限/安全提示 | 命令配置支持 `requires_confirmation` 和 `safety_note`；后端 `require_workspace_command_confirmation` 强制校验普通和流式执行入口；React 显示 `validation-safety-note` 和确认 checkbox；`tests/test_workspace_commands.py`、`frontend/src/api/client.test.ts` 覆盖。 |
| OpenCode 执行能从任务上下文发起 Continue/New/Fork，并在完成后自动关联会话和记录事件 | 任务行和详情均提供 Continue/New/Fork 动作；流式路由接收 `task_id`；`_link_workspace_task_session` 更新 `linked_session_ids` 并记录 `opencode_session_linked` 事件；`tests/test_workspace_opencode_linking.py` 覆盖 Continue/New/Fork。 |
| 一个任务可以从描述、OpenCode 执行、Git 变更、测试结果到验收记录形成闭环 | 任务详情聚合关联会话、Git snapshot、验证运行和事件 timeline；报告生成包含 Delivery Summary、PR Description Draft、Acceptance Notes、Linked Sessions、Git Snapshot、Validation Runs、Task Timeline；`tests/test_workspace_reports.py` 和 E2E 覆盖详情与报告主流程。 |
| 出错时能看到模型错误、命令错误和剩余动作 | 模型/Provider 错误由 `services/opencode_errors.py` 和 stream tests 覆盖；验证命令失败保留 `status`、`exit_code`、`output`；React `ValidationRunsPanel` 和 task detail 保留失败历史。 |
| README 和 Workspace 方案记录当前能力与配置 | `README.md` 记录 Workspace 面板、任务详情、命令白名单、确认字段、运行和测试方式；`docs/opencode-workspace-plan.md` 记录阶段完成状态。 |

## 本阶段验证命令

```bash
python scripts/run_all_tests.py
```

最近结果：

- Python：94 passed。
- Frontend unit：12 passed。
- Playwright E2E：3 passed, 1 skipped。

补充检查：

- `git diff --check`：通过，仅有当前 Windows 环境下的 LF/CRLF 提示。

## 已知边界

- Workspace 命令仍然只执行配置白名单中的 argv，不提供任意命令输入。
- `requires_confirmation` 是显式配置项；未标记的白名单命令默认按普通验证命令处理。
- 真机 Provider 限流和微信扫码发送不在 Workspace 验收中强行触发，沿用 #12 既有自动化覆盖和手工验收边界。
