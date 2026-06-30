import sqlite3
import sys

import app as webapp


def test_workspace_task_report_includes_sessions_and_validation_runs(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    opencode_db = tmp_path / "opencode.db"
    _create_session_db(opencode_db, str(project))
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_DB_PATH": str(opencode_db),
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
            "OPENCODE_WORKSPACE_COMMANDS": [
                {
                    "key": "check",
                    "label": "Check project",
                    "argv": [sys.executable, "-c", "print('report output')"],
                }
            ],
        }
    )

    with app.test_client() as client:
        created = client.post(
            "/api/workspace/tasks",
            json={
                "title": "Reportable task",
                "project_path": str(project),
                "linked_session_ids": ["ses_report"],
            },
        )
        task = created.get_json()["task"]

        run = client.post(
            "/api/workspace/command-runs",
            json={
                "project_path": str(project),
                "command_key": "check",
                "task_id": task["id"],
            },
        )
        assert run.status_code == 201

        report = client.get(f"/api/workspace/tasks/{task['id']}/report")
        events = client.get(f"/api/workspace/tasks/{task['id']}/events")

    assert report.status_code == 200
    payload = report.get_json()["report"]
    markdown = payload["markdown"]
    assert payload["linked_sessions"][0]["id"] == "ses_report"
    assert payload["command_runs"][0]["command_key"] == "check"
    assert any(event["event_type"] == "validation_run_completed" for event in payload["events"])
    assert any(event["event_type"] == "task_report_generated" for event in payload["events"])
    assert "# Reportable task" in markdown
    assert "`ses_report` Linked session" in markdown
    assert "report output" in markdown
    assert "## Task Timeline" in markdown
    assert events.status_code == 200
    assert events.get_json()["total"] >= 2


def test_workspace_task_detail_is_read_only_execution_summary(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    opencode_db = tmp_path / "opencode.db"
    _create_session_db(opencode_db, str(project))
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_DB_PATH": str(opencode_db),
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
            "OPENCODE_WORKSPACE_COMMANDS": [
                {
                    "key": "check",
                    "label": "Check project",
                    "argv": [sys.executable, "-c", "print('detail output')"],
                }
            ],
        }
    )

    with app.test_client() as client:
        created = client.post(
            "/api/workspace/tasks",
            json={
                "title": "Detailed task",
                "project_path": str(project),
                "linked_session_ids": ["ses_report"],
            },
        )
        task = created.get_json()["task"]

        run = client.post(
            "/api/workspace/command-runs",
            json={
                "project_path": str(project),
                "command_key": "check",
                "task_id": task["id"],
            },
        )
        assert run.status_code == 201

        detail = client.get(f"/api/workspace/tasks/{task['id']}/detail")

    assert detail.status_code == 200
    payload = detail.get_json()["detail"]
    assert payload["task"]["title"] == "Detailed task"
    assert payload["linked_sessions"][0]["id"] == "ses_report"
    assert payload["linked_sessions"][0]["title"] == "Linked session"
    assert payload["command_runs"][0]["command_key"] == "check"
    assert "detail output" in payload["command_runs"][0]["output"]
    assert any(event["event_type"] == "validation_run_completed" for event in payload["events"])
    assert not any(event["event_type"] == "task_report_generated" for event in payload["events"])
    assert payload["git"] is None or "is_git_repo" in payload["git"]


def _create_session_db(path, directory):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE session (
            id TEXT PRIMARY KEY,
            title TEXT,
            directory TEXT,
            model TEXT,
            time_created INTEGER,
            time_updated INTEGER
        )"""
    )
    conn.execute(
        """INSERT INTO session
           (id, title, directory, model, time_created, time_updated)
           VALUES ('ses_report', 'Linked session', ?, 'provider/model', 1, 2)""",
        (directory,),
    )
    conn.commit()
    conn.close()
