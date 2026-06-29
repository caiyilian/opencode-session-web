import json
import sqlite3
import subprocess

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
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls += 1
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


def create_session_db(path, directory):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE session (
            id TEXT PRIMARY KEY,
            directory TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO session (id, directory) VALUES (?, ?)",
        ("ses_1", str(directory)),
    )
    conn.commit()
    conn.close()


def test_run_opencode_stream_uses_process_manager_for_normal_exit(monkeypatch):
    process = FakeStreamProcess([
        json.dumps({
            "type": "step_finish",
            "part": {"reason": "stop", "tokens": {"total": 3}, "cost": 0.01},
        }) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)

    events = list(webapp.run_opencode_stream(["opencode", "run"], "ses_1", timeout=1))

    assert manager.started[0][0] == ["opencode", "run"]
    assert manager.started[0][1]["stdout"] == subprocess.PIPE
    assert any("event: done" in event for event in events)
    assert manager.terminated == []
    assert manager.unregistered == [process]


def test_run_opencode_stream_terminates_process_manager_on_error(monkeypatch):
    process = FakeStreamProcess([
        json.dumps({"type": "error", "error": {"message": "rate limited"}}) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)

    events = list(webapp.run_opencode_stream(["opencode", "run"], "ses_1", timeout=1))

    assert any("event: stream_error" in event and "rate limited" in event for event in events)
    assert manager.terminated == [(process, 2)]
    assert manager.unregistered == [process]


def test_run_opencode_stream_formats_non_json_known_error(monkeypatch):
    process = FakeStreamProcess(["quota exceeded\n"])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)

    events = list(webapp.run_opencode_stream(["opencode", "run"], "ses_1", timeout=1))

    assert any(
        "event: stream_error" in event
        and "模型额度或速率已受限" in event
        and "quota exceeded" in event
        for event in events
    )
    assert manager.terminated == [(process, 2)]
    assert manager.unregistered == [process]


def test_run_opencode_stream_ignores_tool_calls_step_finish(monkeypatch):
    process = FakeStreamProcess([
        json.dumps({
            "type": "step_finish",
            "part": {"reason": "tool-calls", "tokens": {"total": 3}, "cost": 0.01},
        }) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)

    events = list(webapp.run_opencode_stream(["opencode", "run"], "ses_1", timeout=1))

    assert not any("event: done" in event for event in events)
    assert manager.terminated == []
    assert manager.unregistered == [process]


def test_new_session_stream_uses_process_manager_for_normal_exit(monkeypatch, tmp_path):
    process = FakeStreamProcess([
        json.dumps({
            "sessionID": "ses_new",
            "type": "step_finish",
            "part": {"tokens": {"total": 3}, "cost": 0.01},
        }) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app({"TESTING": True})

    with app.test_client() as client:
        response = client.post(
            "/api/sessions/new",
            json={"directory": str(tmp_path), "message": "hello"},
            buffered=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert manager.started[0][0][:4] == ["opencode", "run", "--dir", str(tmp_path)]
    assert "event: done" in body
    assert "ses_new" in body
    assert manager.terminated == []
    assert manager.unregistered == [process]


def test_new_session_stream_terminates_process_manager_on_error(monkeypatch, tmp_path):
    process = FakeStreamProcess([
        json.dumps({"type": "error", "error": {"message": "quota exceeded"}}) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app({"TESTING": True})

    with app.test_client() as client:
        response = client.post(
            "/api/sessions/new",
            json={"directory": str(tmp_path), "message": "hello"},
            buffered=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "event: stream_error" in body
    assert "quota exceeded" in body
    assert manager.terminated == [(process, 2)]
    assert manager.unregistered == [process]


def test_new_session_stream_formats_non_json_known_error(monkeypatch, tmp_path):
    process = FakeStreamProcess(["quota exceeded\n"])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app({"TESTING": True})

    with app.test_client() as client:
        response = client.post(
            "/api/sessions/new",
            json={"directory": str(tmp_path), "message": "hello"},
            buffered=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "event: stream_error" in body
    assert "模型额度或速率已受限" in body
    assert "quota exceeded" in body
    assert manager.terminated == [(process, 2)]
    assert manager.unregistered == [process]


def test_fork_session_stream_uses_process_manager_for_normal_exit(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    create_session_db(db_path, tmp_path)
    process = FakeStreamProcess([
        json.dumps({
            "sessionID": "ses_fork",
            "type": "step_finish",
            "part": {"tokens": {"total": 3}, "cost": 0.01},
        }) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app({"TESTING": True, "OPENCODE_DB_PATH": str(db_path)})

    with app.test_client() as client:
        response = client.post(
            "/api/sessions/ses_1/fork",
            json={"message": "hello"},
            buffered=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert manager.started[0][0][:6] == ["opencode", "run", "--dir", str(tmp_path), "--fork", "-s"]
    assert "event: done" in body
    assert "ses_fork" in body
    assert manager.terminated == []
    assert manager.unregistered == [process]


def test_fork_session_stream_terminates_process_manager_on_json_error(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    create_session_db(db_path, tmp_path)
    process = FakeStreamProcess([
        json.dumps({"error": {"message": "rate limited"}}) + "\n"
    ])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app({"TESTING": True, "OPENCODE_DB_PATH": str(db_path)})

    with app.test_client() as client:
        response = client.post(
            "/api/sessions/ses_1/fork",
            json={"message": "hello"},
            buffered=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "event: stream_error" in body
    assert "rate limited" in body
    assert manager.terminated == [(process, 2)]
    assert manager.unregistered == [process]


def test_fork_session_stream_terminates_process_manager_on_non_json_rate_limit(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    create_session_db(db_path, tmp_path)
    process = FakeStreamProcess(["quota exceeded\n"])
    manager = FakeStreamProcessManager(process)
    monkeypatch.setattr(webapp, "process_manager", manager)
    app = webapp.create_app({"TESTING": True, "OPENCODE_DB_PATH": str(db_path)})

    with app.test_client() as client:
        response = client.post(
            "/api/sessions/ses_1/fork",
            json={"message": "hello"},
            buffered=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "event: stream_error" in body
    assert "quota exceeded" in body
    assert manager.terminated == [(process, 2)]
    assert manager.unregistered == [process]
