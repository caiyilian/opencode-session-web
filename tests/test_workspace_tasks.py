import app as webapp


def test_workspace_task_lifecycle(tmp_path):
    workspace_db = tmp_path / "workspace.db"
    app = webapp.create_app({
        "TESTING": True,
        "OPENCODE_WORKSPACE_DB_PATH": str(workspace_db),
    })

    with app.test_client() as client:
        empty = client.get("/api/workspace/tasks?project_path=C:/repo/alpha")
        assert empty.status_code == 200
        assert empty.get_json()["tasks"] == []

        created = client.post(
            "/api/workspace/tasks",
            json={
                "title": "Ship alpha workspace",
                "description": "Wire project tasks into the workbench.",
                "project_path": "C:/repo/alpha",
                "linked_session_ids": ["ses_alpha", "ses_alpha", ""],
            },
        )
        assert created.status_code == 201
        task = created.get_json()["task"]
        assert task["id"].startswith("task_")
        assert task["status"] == "todo"
        assert task["linked_session_ids"] == ["ses_alpha"]

        listed = client.get("/api/workspace/tasks?project_path=C:/repo/alpha")
        payload = listed.get_json()
        assert payload["total"] == 1
        assert payload["tasks"][0]["title"] == "Ship alpha workspace"
        assert "in_progress" in payload["statuses"]

        updated = client.patch(
            f"/api/workspace/tasks/{task['id']}",
            json={"status": "in_progress", "linked_session_ids": ["ses_alpha", "ses_beta"]},
        )
        assert updated.status_code == 200
        updated_task = updated.get_json()["task"]
        assert updated_task["status"] == "in_progress"
        assert updated_task["linked_session_ids"] == ["ses_alpha", "ses_beta"]

        filtered = client.get("/api/workspace/tasks?status=in_progress")
        assert filtered.status_code == 200
        assert filtered.get_json()["total"] == 1


def test_workspace_task_validation(tmp_path):
    app = webapp.create_app({
        "TESTING": True,
        "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
    })

    with app.test_client() as client:
        missing_title = client.post("/api/workspace/tasks", json={"title": ""})
        assert missing_title.status_code == 400
        assert "标题" in missing_title.get_json()["error"]

        invalid_status = client.get("/api/workspace/tasks?status=unknown")
        assert invalid_status.status_code == 400
        assert "状态" in invalid_status.get_json()["error"]

        missing_task = client.patch("/api/workspace/tasks/task_missing", json={"status": "done"})
        assert missing_task.status_code == 404
