import json
import sqlite3

import app as webapp


class FakePipe:
    def __init__(self, lines):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


class FakeStreamProcess:
    def __init__(self, stdout_lines, stderr_lines=None):
        self.pid = 4242
        self.stdout = FakePipe(stdout_lines)
        self.stderr = FakePipe(stderr_lines or [])
        self.returncode = None

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class FakeStreamProcessManager:
    def __init__(self, process):
        self.process = process
        self.started = []
        self.terminated = []
        self.unregistered = []

    def start(self, command, **kwargs):
        self.started.append((command, kwargs))
        return self.process

    def terminate(self, process, timeout=None):
        self.terminated.append((process, timeout))
        process.returncode = -15
        return True

    def unregister(self, process):
        self.unregistered.append(process)
        return True


def test_continue_session_stream_links_workspace_task(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    _create_session_db(db_path, tmp_path)
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_DB_PATH": str(db_path),
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
        }
    )
    monkeypatch.setattr(
        webapp,
        "run_opencode_stream",
        lambda cmd, session_id: iter(["event: text\ndata: linked\n\n"]),
    )

    with app.test_client() as client:
        task = _create_task(client, str(tmp_path))
        response = client.get(
            f"/api/sessions/ses_1/stream?message=hello&task_id={task['id']}",
            buffered=True,
        )
        linked_task = client.get(f"/api/workspace/tasks?project_path={tmp_path}").get_json()["tasks"][0]

    assert response.status_code == 200
    assert "event: done" in response.get_data(as_text=True)
    assert "ses_1" in linked_task["linked_session_ids"]


def test_new_session_stream_links_workspace_task(monkeypatch, tmp_path):
    process = FakeStreamProcess([
        json.dumps({"sessionID": "ses_new", "type": "step_finish", "part": {"reason": "stop"}}) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
        }
    )

    with app.test_client() as client:
        task = _create_task(client, str(tmp_path))
        response = client.post(
            "/api/sessions/new",
            json={"directory": str(tmp_path), "message": "hello", "task_id": task["id"]},
            buffered=True,
        )
        linked_task = client.get(f"/api/workspace/tasks?project_path={tmp_path}").get_json()["tasks"][0]

    assert response.status_code == 200
    assert "ses_new" in response.get_data(as_text=True)
    assert "ses_new" in linked_task["linked_session_ids"]
    assert manager.terminated == []
    assert manager.unregistered == [process]


def test_fork_session_stream_links_workspace_task(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    _create_session_db(db_path, tmp_path)
    process = FakeStreamProcess([
        json.dumps({"sessionID": "ses_fork", "type": "step_finish", "part": {"reason": "stop"}}) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_DB_PATH": str(db_path),
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
        }
    )

    with app.test_client() as client:
        task = _create_task(client, str(tmp_path))
        response = client.post(
            "/api/sessions/ses_1/fork",
            json={"message": "hello", "task_id": task["id"]},
            buffered=True,
        )
        linked_task = client.get(f"/api/workspace/tasks?project_path={tmp_path}").get_json()["tasks"][0]

    assert response.status_code == 200
    assert "ses_fork" in response.get_data(as_text=True)
    assert "ses_fork" in linked_task["linked_session_ids"]
    assert manager.terminated == []
    assert manager.unregistered == [process]


def test_invalid_workspace_task_id_does_not_start_session_stream(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    _create_session_db(db_path, tmp_path)
    called = False

    def fake_run(cmd, session_id):
        nonlocal called
        called = True
        return iter([])

    monkeypatch.setattr(webapp, "run_opencode_stream", fake_run)
    app = webapp.create_app(
        {
            "TESTING": True,
            "OPENCODE_DB_PATH": str(db_path),
            "OPENCODE_WORKSPACE_DB_PATH": str(tmp_path / "workspace.db"),
        }
    )

    with app.test_client() as client:
        response = client.get("/api/sessions/ses_1/stream?message=hello&task_id=task_missing")

    assert response.status_code == 404
    assert response.get_json()["error"] == "任务不存在"
    assert called is False


def _create_task(client, project_path):
    response = client.post(
        "/api/workspace/tasks",
        json={"title": "OpenCode linked task", "project_path": project_path},
    )
    assert response.status_code == 201
    return response.get_json()["task"]


def _create_session_db(path, directory):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE session (
            id TEXT PRIMARY KEY,
            directory TEXT
        )"""
    )
    conn.execute("INSERT INTO session (id, directory) VALUES ('ses_1', ?)", (str(directory),))
    conn.commit()
    conn.close()
