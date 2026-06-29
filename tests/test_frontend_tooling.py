import json
from pathlib import Path


def test_frontend_package_exposes_vite_build_script():
    package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["build"] == (
        "tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json && vite build"
    )
    assert package["scripts"]["test"] == "vitest run"
    assert "react" in package["dependencies"]
    assert "react-dom" in package["dependencies"]
    assert "vite" in package["dependencies"]
    assert "typescript" in package["dependencies"]
    assert "react-markdown" in package["dependencies"]
    assert "remark-gfm" in package["dependencies"]
    assert "vitest" in package["devDependencies"]


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
    ]:
        assert f"function {helper}" in client_source

    for type_name in ["StatsResponse", "SessionSummary", "SessionDetailResponse", "MessagePart"]:
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
    assert "MessageTimeline" in app_source
    assert "SessionComposer" in app_source
    assert "NewSessionPanel" in app_source
    assert "createNewSessionStream" in app_source
    assert "ToolCard" in app_source
    assert "ToolSection" in app_source
    assert "EventSource" in app_source
    assert "ReactMarkdown" in app_source
    assert "remarkGfm" in app_source
    assert "step-finish" in app_source
