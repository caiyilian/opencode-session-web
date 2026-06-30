import json
from pathlib import Path


def test_frontend_package_exposes_vite_build_script():
    package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["build"] == (
        "tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json && vite build"
    )
    assert package["scripts"]["test"] == "vitest run"
    assert package["scripts"]["test:e2e"] == "npm run build && playwright test"
    assert "react" in package["dependencies"]
    assert "react-dom" in package["dependencies"]
    assert "vite" in package["dependencies"]
    assert "typescript" in package["dependencies"]
    assert "react-markdown" in package["dependencies"]
    assert "remark-gfm" in package["dependencies"]
    assert "prismjs" in package["dependencies"]
    assert "@types/prismjs" in package["devDependencies"]
    assert "@playwright/test" in package["devDependencies"]
    assert "vitest" in package["devDependencies"]


def test_local_test_runner_covers_backend_frontend_and_e2e():
    runner = Path("scripts/run_all_tests.py").read_text(encoding="utf-8")

    assert "pytest" in runner
    assert '"test"' in runner
    assert "test:e2e" in runner


def test_frontend_api_client_scaffold_exports_core_helpers():
    client_source = Path("frontend/src/api/client.ts").read_text(encoding="utf-8")
    types_source = Path("frontend/src/api/types.ts").read_text(encoding="utf-8")
    index_source = Path("frontend/src/api/index.ts").read_text(encoding="utf-8")

    for helper in [
        "apiRequest",
        "getStats",
        "getDirectories",
        "getSessions",
        "getSession",
        "getAvailableModels",
        "getWorkspaceProjects",
        "getWorkspaceTasks",
        "createWorkspaceTask",
        "updateWorkspaceTask",
        "getWorkspaceTaskEvents",
        "getWorkspaceTaskReport",
        "getWorkspaceGit",
        "getWorkspaceCommands",
        "getWorkspaceCommandRuns",
        "runWorkspaceCommand",
    ]:
        assert f"function {helper}" in client_source

    for type_name in [
        "StatsResponse",
        "SessionSummary",
        "SessionDetailResponse",
        "MessagePart",
        "ProjectWorkspace",
        "WorkspaceTask",
        "WorkspaceTaskEvent",
        "WorkspaceTaskReport",
        "WorkspaceGitSnapshot",
        "WorkspaceCommand",
        "WorkspaceCommandRun",
    ]:
        assert f"interface {type_name}" in types_source or f"type {type_name}" in types_source

    assert 'export * from "./client"' in index_source
    assert 'export * from "./types"' in index_source


def test_react_app_loads_core_api_data():
    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    for helper in ["getStats", "getDirectories", "getSessions", "getAvailableModels", "getSession"]:
        assert helper in app_source

    for state_marker in ["useReducer", "selectedDirectory", "selectedModel", "blockedProviders"]:
        assert state_marker in app_source

    assert 'status: "loading"' in app_source
    assert 'status: "ready"' in app_source
    assert 'status: "error"' in app_source
    assert "OpenCode Sessions" in app_source
    assert "Collapse sidebar" in app_source
    assert "WorkspacePanel" in app_source
    assert "Project workspace" in app_source
    assert "ProjectTasksPanel" in app_source
    assert "Project Tasks" in app_source
    assert "Task Report" in app_source
    assert "Execution Timeline" in app_source
    assert "task-event-list" in app_source
    assert "task-report-preview" in app_source
    assert "task-opencode-actions" in app_source
    assert "buildWorkspaceTaskMessage" in app_source
    assert "GitSnapshotPanel" in app_source
    assert "Git Snapshot" in app_source
    assert "ValidationRunsPanel" in app_source
    assert "Validation Runs" in app_source
    assert "MessageTimeline" in app_source
    assert "SessionComposer" in app_source
    assert "NewSessionPanel" in app_source
    assert "createNewSessionStream" in app_source
    assert "StatsPanel" in app_source
    assert "StatsRankList" in app_source
    assert "ComparePanel" in app_source
    assert "compareSessions" in app_source
    assert "SessionActions" in app_source
    assert "deleteSession" in app_source
    assert "undoSession" in app_source
    assert "ForkSessionPanel" in app_source
    assert "createForkSessionStream" in app_source
    assert "ToolCard" in app_source
    assert "ToolSection" in app_source
    assert "Prism.highlight" in app_source
    assert "toolStatusMeta" in app_source
    assert "formatDurationMs" in app_source
    assert "tool-status-icon" in app_source
    assert "EventSource" in app_source
    assert "ReactMarkdown" in app_source
    assert "remarkGfm" in app_source
    assert "step-finish" in app_source
