import sys

import app as webapp
from services.workspace_commands import parse_workspace_commands


def test_workspace_command_run_records_success(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    workspace_db = tmp_path / "workspace.db"
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_WORKSPACE_DB_PATH": str(workspace_db),
            "OPENCODE_WORKSPACE_COMMANDS": [
                {
                    "key": "check",
                    "label": "Check project",
                    "argv": [sys.executable, "-c", "print('workspace ok')"],
                    "cwd": ".",
                }
            ],
        }
    )

    with app.test_client() as client:
        commands = client.get("/api/workspace/commands")
        assert commands.status_code == 200
        assert commands.get_json()["commands"][0]["key"] == "check"

        created = client.post(
            "/api/workspace/command-runs",
            json={
                "project_path": str(project),
                "command_key": "check",
                "task_id": "task_1",
            },
        )
        assert created.status_code == 201
        run = created.get_json()["run"]
        assert run["status"] == "success"
        assert run["exit_code"] == 0
        assert "workspace ok" in run["output"]
        assert run["task_id"] == "task_1"

        history = client.get("/api/workspace/command-runs", query_string={"project_path": str(project)})
        assert history.status_code == 200
        assert history.get_json()["runs"][0]["id"] == run["id"]


def test_workspace_command_run_stream_records_success_and_events(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    workspace_db = tmp_path / "workspace.db"
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_WORKSPACE_DB_PATH": str(workspace_db),
            "OPENCODE_WORKSPACE_COMMANDS": [
                {
                    "key": "check",
                    "label": "Check project",
                    "argv": [sys.executable, "-c", "print('stream workspace ok')"],
                    "cwd": ".",
                }
            ],
        }
    )

    with app.test_client() as client:
        task = client.post(
            "/api/workspace/tasks",
            json={"title": "Stream validation task", "project_path": str(project)},
        ).get_json()["task"]
        streamed = client.post(
            "/api/workspace/command-runs/stream",
            json={
                "project_path": str(project),
                "command_key": "check",
                "task_id": task["id"],
            },
            buffered=True,
        )
        history = client.get("/api/workspace/command-runs", query_string={"task_id": task["id"]})
        events = client.get(f"/api/workspace/tasks/{task['id']}/events")

    body = streamed.get_data(as_text=True)
    assert streamed.status_code == 200
    assert "event: started" in body
    assert "event: output" in body
    assert "stream workspace ok" in body
    assert "event: done" in body
    run = history.get_json()["runs"][0]
    assert run["status"] == "success"
    assert run["task_id"] == task["id"]
    assert "stream workspace ok" in run["output"]
    assert events.get_json()["events"][0]["event_type"] == "validation_run_completed"


def test_workspace_command_run_rejects_unknown_command(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
            "OPENCODE_WORKSPACE_COMMANDS": [],
        }
    )

    with app.test_client() as client:
        response = client.post(
            "/api/workspace/command-runs",
            json={"project_path": str(project), "command_key": "missing"},
        )

    assert response.status_code == 400
    assert "白名单" in response.get_json()["error"]


def test_workspace_command_config_rejects_unsafe_cwd():
    try:
        parse_workspace_commands([{"key": "bad", "label": "Bad", "argv": ["echo", "no"], "cwd": ".."}])
    except ValueError as exc:
        assert "cwd" in str(exc)
    else:
        raise AssertionError("unsafe cwd was accepted")


def test_workspace_command_run_rejects_cwd_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
            "OPENCODE_WORKSPACE_COMMANDS": [
                {"key": "bad", "label": "Bad", "argv": [sys.executable, "-c", "print('no')"], "cwd": ".."}
            ],
        }
    )

    with app.test_client() as client:
        response = client.get("/api/workspace/commands")

    assert response.status_code == 500
    assert "cwd" in response.get_json()["error"]
