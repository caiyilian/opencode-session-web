import json
import sqlite3

import app as webapp
from services.sync_watcher import SessionSnapshot


def test_api_events_emits_heartbeat_when_no_session_changes(tmp_path):
    db_path = tmp_path / "opencode.db"
    conn = _connect(db_path)
    _create_session_table(conn)
    _insert_session(conn, "ses_1", "One", "C:/repo/one", 100)
    conn.close()
    app = webapp.create_app({"TESTING": True, "OPENCODE_DB_PATH": str(db_path)})

    with app.test_client() as client:
        response = client.get("/api/events?max_polls=1&interval_ms=0", buffered=True)

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert "event: heartbeat" in body
    assert _event_payload(body) == {"sessions": 1}


def test_api_events_emits_session_change_when_snapshot_differs(monkeypatch, tmp_path):
    db_path = tmp_path / "opencode.db"
    conn = _connect(db_path)
    _create_session_table(conn)
    conn.close()

    snapshots = [
        {"ses_1": SessionSnapshot("ses_1", "Before", "C:/repo", 100)},
        {"ses_1": SessionSnapshot("ses_1", "After", "C:/repo", 200)},
    ]

    def fake_fetch_session_snapshots(_conn):
        return snapshots.pop(0)

    monkeypatch.setattr(webapp, "fetch_session_snapshots", fake_fetch_session_snapshots)
    app = webapp.create_app({"TESTING": True, "OPENCODE_DB_PATH": str(db_path)})

    with app.test_client() as client:
        response = client.get("/api/events?max_polls=1&interval_ms=0", buffered=True)

    body = response.get_data(as_text=True)
    payload = _event_payload(body)
    assert response.status_code == 200
    assert "event: session_change" in body
    assert payload["type"] == "updated"
    assert payload["session"]["id"] == "ses_1"
    assert payload["session"]["title"] == "After"
    assert payload["previous"]["title"] == "Before"


def _event_payload(body):
    data_lines = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
    return json.loads("\n".join(data_lines))


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _create_session_table(conn):
    conn.execute(
        """CREATE TABLE session (
            id TEXT PRIMARY KEY,
            title TEXT,
            directory TEXT,
            time_updated INTEGER
        )"""
    )
    conn.commit()


def _insert_session(conn, session_id, title, directory, time_updated):
    conn.execute(
        "INSERT INTO session (id, title, directory, time_updated) VALUES (?, ?, ?, ?)",
        (session_id, title, directory, time_updated),
    )
    conn.commit()
